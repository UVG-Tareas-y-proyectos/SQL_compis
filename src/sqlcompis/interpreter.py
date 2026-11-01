"""Ejecución de acciones sobre el AST y archivos propios."""

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date
import operator

from .model import SQLError, Node
from .types import convert, literal_value
from .indexes import IndexManager, has_outer_references


@dataclass
class QueryResult:
    columns: list = field(default_factory=list)
    rows: list = field(default_factory=list)
    affected: int = 0
    message: str = ''
    plan: list = field(default_factory=list)


class Interpreter:
    def __init__(self, storage):
        self.storage = storage
        self.plan = []
        self.indexes = IndexManager(storage)
        self.query_cache = {}

    def execute(self, node):
        metadata = deepcopy(self.storage.metadata)
        kind = node.kind
        if kind == 'create_table':
            metadata['tables'][node['table']] = deepcopy(node.meta['schema'])
            self.storage.save_rows(node['table'], [], metadata)
            return QueryResult(message=f"Tabla '{node['table']}' creada.")
        if kind == 'drop_table':
            name = node['name']
            del metadata['tables'][name]
            updates = {f'tables/{name}.csv': None, f'offsets/{name}.json': None}
            for index, definition in list(metadata['indexes'].items()):
                if definition['table'] == name:
                    updates[f'indexes/{index}.json'] = None
                    del metadata['indexes'][index]
            self.storage.commit(metadata, updates)
            return QueryResult(message=f"Tabla '{name}' eliminada.")
        if kind == 'insert':
            name = node['table']
            schema = metadata['tables'][name]
            rows = self.storage.rows(name)
            for values in node['rows']:
                supplied = dict(zip(node.meta['columns'], [self.eval(e, [{}]) for e in values['expressions']]))
                row = {'__rid': schema['next_id']}
                schema['next_id'] += 1
                for column in schema['columns']:
                    value = supplied.get(column['name'], column['default'] if column['has_default'] else None)
                    row[column['name']] = convert(value, column, values)
                rows.append(row)
            self.check_constraints(schema, rows, node)
            self.write_rows(name, rows, metadata)
            return QueryResult(affected=len(node['rows']), message=f"{len(node['rows'])} registro(s) insertado(s).")
        if kind == 'create_index':
            definition = {'table': node['table'], 'column': node['column']}
            metadata['indexes'][node['name']] = definition
            rows = self.storage.rows(node['table'])
            self.storage.commit(metadata, {f"indexes/{node['name']}.json": self.indexes.build(definition, rows)})
            return QueryResult(message=f"Índice '{node['name']}' creado.")
        if kind == 'drop_index':
            del metadata['indexes'][node['name']]
            self.storage.commit(metadata, {f"indexes/{node['name']}.json": None})
            return QueryResult(message=f"Índice '{node['name']}' eliminado.")
        if kind == 'select':
            return self.select(node, [])
        if kind in {'update', 'delete'}:
            name = node['table']
            schema = metadata['tables'][name]
            source = Node('source', {'table': name, 'alias': name}, node.line, node.column)
            candidates = self.read_source(source, node['where'], [])
            selected = [r for r in candidates if node['where'] is None or self.eval(node['where'], [{name: r}]) is True]
            replacements = {}
            for row in selected:
                if kind == 'delete':
                    replacements[row['__rid']] = None
                else:
                    replacement = dict(row)
                    for assignment in node['assignments']:
                        col = next(c for c in schema['columns'] if c['name'] == assignment['column'])
                        replacement[col['name']] = convert(self.eval(assignment['expression'], [{name: row}]), col, assignment)
                    replacements[row['__rid']] = replacement
            if replacements:
                # Reescribir el archivo no vuelve a evaluar WHERE sobre otras filas.
                all_rows = self.storage.rows(name)
                rows = [replacements.get(r['__rid'], r) for r in all_rows]
                rows = [r for r in rows if r is not None]
                self.check_constraints(schema, rows, node)
                self.write_rows(name, rows, metadata)
            return QueryResult(affected=len(selected), message=f'{len(selected)} registro(s) {"actualizado(s)" if kind == "update" else "eliminado(s)"}.', plan=self.plan)
        raise SQLError(f'sentencia aún no implementada: {kind}', node, 'ejecución')

    def write_rows(self, name, rows, metadata):
        self.storage.save_rows(name, rows, metadata, self.indexes.updates(name, rows, metadata))

    def read_source(self, source, where, outer):
        candidates = self.indexes.candidates(where, source,
            lambda e: self.eval(e, [{}, *outer]), lambda q: self.subquery(q, [{}, *outer]))
        rows = self.storage.rows(source['table'], candidates[0] if candidates is not None else None)
        self.plan.append({'table': source['table'], 'alias': source['alias'],
                          'access': 'índice' if candidates is not None else 'recorrido completo',
                          'indexes': sorted(candidates[1]) if candidates is not None else [],
                          'rows_read': len(rows), 'total_rows': self.storage.metadata['tables'][source['table']]['count']})
        return rows

    def select(self, query, outer):
        source = query['source']
        contexts = ([{source['alias']: r} for r in self.read_source(source, query['where'], outer)] if source else [{}])
        for join in query['joins']:
            source = join['source']
            right = self.read_source(source, query['where'], outer)
            combined = []
            for left in contexts:
                for row in right:
                    context = {**left, source['alias']: row}
                    if self.eval(join['on'], [context, *outer]) is True:
                        combined.append(context)
            contexts = combined
        contexts = [c for c in contexts if query['where'] is None or self.eval(query['where'], [c, *outer]) is True]
        if query['group']:
            groups = {}
            for context in contexts:
                key = tuple(self.eval(e, [context, *outer]) for e in query['group'])
                groups.setdefault(key, []).append(context)
            units = [(rows[0], rows) for rows in groups.values()]
        elif query.meta['aggregate']:
            units = [(contexts[0] if contexts else {}, contexts)]
        else:
            units = [(context, None) for context in contexts]
        records = []
        for context, group in units:
            frames = [context, *outer]
            if query['having'] and self.eval(query['having'], frames, group) is not True:
                continue
            values = [self.eval(e, frames, group) for _, e in query.meta['projections']]
            keys = [self.eval(o['expression'], frames, group) for o in query['order']]
            records.append((values, keys))
        return self.finish_select(query, records)

    def finish_select(self, query, records):
        if query['distinct']:
            seen, unique = set(), []
            for values, keys in records:
                key = tuple(values)
                if key not in seen:
                    seen.add(key)
                    unique.append((values, keys))
            records = unique
        for i in reversed(range(len(query['order']))):
            records.sort(key=lambda r: (r[1][i] is not None, r[1][i]), reverse=query['order'][i]['descending'])
        rows = [values for values, _ in records]
        return QueryResult([name for name, _ in query.meta['projections']], rows, len(rows),
                           f'{len(rows)} fila(s) consultada(s).', self.plan)

    def check_constraints(self, schema, rows, node):
        groups = ([schema['primary']] if schema['primary'] else []) + schema['unique']
        for columns in groups:
            seen = set()
            for row in rows:
                key = tuple(row[c] for c in columns)
                if any(v is None for v in key):
                    continue
                if key in seen:
                    raise SQLError(f"restricción de unicidad incumplida en {', '.join(columns)}", node)
                seen.add(key)

    def subquery(self, query, frames):
        # Una consulta independiente de la fila exterior se evalúa una vez
        # por sentencia. Las correlacionadas conservan su evaluación por fila.
        if has_outer_references(query):
            return self.select(query, frames)
        key = id(query)
        if key not in self.query_cache:
            self.query_cache[key] = self.select(query, frames)
        return self.query_cache[key]

    def eval(self, expr, frames, group=None):
        if 'alias_expr' in expr.meta:
            return self.eval(expr.meta['alias_expr'], frames, group)
        kind = expr.kind
        if kind == 'literal':
            return literal_value(expr)
        if kind == 'column':
            depth, alias, column = expr.meta['binding']
            return frames[depth][alias][column]
        if kind == 'aggregate':
            if group is None:
                raise SQLError('agregación sin grupo de ejecución', expr, 'ejecución')
            if expr['argument'].kind == 'star':
                return len(group)
            values = [self.eval(expr['argument'], [row, *frames[1:]]) for row in group]
            values = [value for value in values if value is not None]
            name = expr['name']
            if name == 'COUNT':
                return len(values)
            if not values:
                return None
            if name == 'SUM':
                return sum(values)
            if name == 'AVG':
                return sum(values)/len(values)
            return min(values) if name == 'MIN' else max(values)
        if kind == 'unary':
            value = self.eval(expr['operand'], frames, group)
            if value is None:
                return None
            return not value if expr['op'] == 'NOT' else -value if expr['op'] == '-' else value
        if kind == 'is_null':
            result = self.eval(expr['left'], frames, group) is None
            return not result if expr['negated'] else result
        if kind == 'binary':
            left = self.eval(expr['left'], frames, group)
            op = expr['op']
            if (op == 'AND' and left is False) or (op == 'OR' and left is True):
                return left
            right = self.eval(expr['right'], frames, group)
            if op == 'AND':
                return False if right is False else None if left is None or right is None else True
            if op == 'OR':
                return True if right is True else None if left is None or right is None else False
            if left is None or right is None:
                return None
            if isinstance(left, date) and isinstance(right, str):
                right = convert(right, {'name': 'comparación', 'type': 'DATE'}, expr)
            if isinstance(right, date) and isinstance(left, str):
                left = convert(left, {'name': 'comparación', 'type': 'DATE'}, expr)
            functions = {'+': operator.add, '-': operator.sub, '*': operator.mul, '/': operator.truediv,
                         '%': operator.mod, '=': operator.eq, '<>': operator.ne, '!=': operator.ne,
                         '<': operator.lt, '<=': operator.le, '>': operator.gt, '>=': operator.ge}
            try:
                return functions[op](left, right)
            except (ArithmeticError, TypeError) as exc:
                raise SQLError(f'operación inválida: {exc}', expr, 'ejecución') from exc
        if kind in {'scalar', 'exists'}:
            result = self.subquery(expr['query'], frames)
            if kind == 'exists':
                return bool(result.rows)
            if len(result.rows) > 1:
                raise SQLError('subconsulta escalar retorna más de un registro', expr)
            return result.rows[0][0] if result.rows else None
        if kind == 'in':
            left = self.eval(expr['left'], frames, group)
            values = expr['values']
            values = ([r[0] for r in self.subquery(values, frames).rows] if isinstance(values, Node)
                      else [self.eval(v, frames, group) for v in values])
            if not values:
                result = False
            elif left is None:
                result = None
            else:
                if isinstance(left, date):
                    values = [convert(v, {'name': 'IN', 'type': 'DATE'}, expr) if v is not None else None for v in values]
                result = True if left in [v for v in values if v is not None] else None if None in values else False
            return not result if expr['negated'] and result is not None else result
        raise SQLError(f'expresión aún no implementada: {kind}', expr, 'ejecución')
