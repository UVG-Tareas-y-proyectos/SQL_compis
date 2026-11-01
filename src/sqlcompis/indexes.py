"""Índices persistentes valor -> identificadores estables de filas.

Los candidatos se buscan en el archivo del índice. El lector de la tabla
utiliza offsets para hacer seek de esas filas y no recorrer todos los registros.
"""

from datetime import date
import json
import operator

from .model import Node, SQLError
from .storage import encode_json
from .types import convert


def has_outer_references(query):
    return any(n.kind == 'column' and n.meta.get('binding', (0,))[0] > 0 for n in query.walk())


class IndexManager:
    def __init__(self, storage):
        self.storage = storage

    def build(self, definition, rows):
        entries = {}
        for row in rows:
            key = json.dumps(row[definition['column']], ensure_ascii=False, default=str)
            entries.setdefault(key, []).append(row['__rid'])
        return encode_json({'version': 1, **definition, 'entries': entries})

    def updates(self, table, rows, metadata):
        return {f'indexes/{name}.json': self.build(definition, rows)
                for name, definition in metadata['indexes'].items() if definition['table'] == table}

    def constant(self, node):
        if node.kind == 'scalar':
            return not has_outer_references(node['query'])
        if node.kind in {'select', 'exists', 'aggregate'}:
            return False
        if node.kind == 'column':
            return node.meta.get('binding', (0,))[0] > 0
        return all(self.constant(child) for value in node.data.values()
                   for child in (value if isinstance(value, list) else [value]) if isinstance(child, Node))

    def candidates(self, expr, source, evaluate, subquery):
        if expr is None:
            return None
        if expr.kind == 'binary' and expr['op'] in {'AND', 'OR'}:
            left = self.candidates(expr['left'], source, evaluate, subquery)
            right = self.candidates(expr['right'], source, evaluate, subquery)
            if expr['op'] == 'AND':
                if left is None:
                    return right
                if right is None:
                    return left
                return left[0] & right[0], left[1] | right[1]
            if left is None or right is None:
                return None  # OR no puede descartar filas de una rama sin índice.
            return left[0] | right[0], left[1] | right[1]
        if expr.kind == 'unary' and expr['op'] == 'NOT':
            inner = expr['operand']
            if inner.kind == 'binary' and inner['op'] in {'=', '!=', '<>', '<', '<=', '>', '>='}:
                inverse = {'=': '<>', '<>': '=', '!=': '=', '<': '>=', '>=': '<', '>': '<=', '<=': '>'}
                inner = Node('binary', {**inner.data, 'op': inverse[inner['op']]}, inner.line, inner.column)
            elif inner.kind in {'is_null', 'in'}:
                inner = Node(inner.kind, {**inner.data, 'negated': not inner['negated']}, inner.line, inner.column)
            else:
                return None
            return self.candidates(inner, source, evaluate, subquery)
        column, predicate = None, None
        if expr.kind == 'binary' and expr['op'] in {'=', '!=', '<>', '<', '<=', '>', '>='}:
            left, right, op = expr['left'], expr['right'], expr['op']
            if left.kind != 'column' and right.kind == 'column':
                left, right = right, left
                op = {'<': '>', '<=': '>=', '>': '<', '>=': '<='}.get(op, op)
            if left.kind != 'column' or not self.constant(right):
                return None
            column = left
            value = evaluate(right)
            if column.meta['type'] == 'DATE' and isinstance(value, str):
                value = convert(value, {'name': column['name'], 'type': 'DATE'}, expr)
            compare = {'=': operator.eq, '<>': operator.ne, '!=': operator.ne,
                       '<': operator.lt, '<=': operator.le, '>': operator.gt, '>=': operator.ge}[op]
            predicate = lambda key: key is not None and value is not None and compare(key, value)
        elif expr.kind == 'is_null' and expr['left'].kind == 'column':
            column = expr['left']
            predicate = lambda key: (key is not None) if expr['negated'] else key is None
        elif expr.kind == 'in' and expr['left'].kind == 'column':
            column = expr['left']
            values = expr['values']
            if isinstance(values, Node):
                if has_outer_references(values):
                    return None
                values = [r[0] for r in subquery(values).rows]
            else:
                if not all(self.constant(v) for v in values):
                    return None
                values = [evaluate(v) for v in values]
            if column.meta['type'] == 'DATE':
                values = [convert(v, {'name': column['name'], 'type': 'DATE'}, expr) for v in values]
            def predicate(key):
                if not values:
                    return expr['negated']
                if key is None:
                    return False
                matched = key in [v for v in values if v is not None]
                return (not matched and None not in values) if expr['negated'] else matched
        if column is None:
            return None
        depth, alias, name = column.meta['binding']
        if depth != 0 or alias != source['alias']:
            return None
        index = next(((n, d) for n, d in self.storage.metadata['indexes'].items()
                      if d['table'] == source['table'] and d['column'] == name), None)
        if index is None:
            return None
        index_name, _ = index
        try:
            entries = json.loads(self.storage.path(f'indexes/{index_name}.json').read_text(encoding='utf-8'))['entries']
            ids = set()
            for key, positions in entries.items():
                indexed_value = json.loads(key)
                if column.meta['type'] == 'DATE' and indexed_value is not None:
                    indexed_value = date.fromisoformat(indexed_value)
                if predicate(indexed_value):
                    ids.update(positions)
            return ids, {index_name}
        except (OSError, ValueError, KeyError) as exc:
            raise SQLError(f"índice '{index_name}' inválido: {exc}", expr, 'almacenamiento') from exc
