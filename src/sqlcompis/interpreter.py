"""Ejecución de acciones sobre el AST y archivos propios."""

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date
import operator

from .model import SQLError, Node
from .types import convert, literal_value


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
        self.storage.save_rows(name, rows, metadata)

    def read_source(self, source, where, outer):
        rows = self.storage.rows(source['table'])
        self.plan.append({'table': source['table'], 'alias': source['alias'], 'access': 'recorrido completo',
                          'indexes': [], 'rows_read': len(rows), 'total_rows': len(rows)})
        return rows

    def select(self, query, outer):
        if query['joins'] or query.meta['aggregate']:
            raise SQLError('JOIN y agrupación requieren su regla de ejecución', query, 'ejecución')
        source = query['source']
        contexts = ([{source['alias']: r} for r in self.read_source(source, query['where'], outer)] if source else [{}])
        contexts = [c for c in contexts if query['where'] is None or self.eval(query['where'], [c, *outer]) is True]
        records = []
        for context in contexts:
            frames = [context, *outer]
            values = [self.eval(e, frames) for _, e in query.meta['projections']]
            keys = [self.eval(o['expression'], frames) for o in query['order']]
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

    def eval(self, expr, frames, group=None):
        if 'alias_expr' in expr.meta:
            return self.eval(expr.meta['alias_expr'], frames, group)
        kind = expr.kind
        if kind == 'literal':
            return literal_value(expr)
        if kind == 'column':
            depth, alias, column = expr.meta['binding']
            return frames[depth][alias][column]
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
            result = self.select(expr['query'], frames)
            if kind == 'exists':
                return bool(result.rows)
            if len(result.rows) > 1:
                raise SQLError('subconsulta escalar retorna más de un registro', expr)
            return result.rows[0][0] if result.rows else None
        if kind == 'in':
            left = self.eval(expr['left'], frames, group)
            values = expr['values']
            values = ([r[0] for r in self.select(values, frames).rows] if isinstance(values, Node)
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
