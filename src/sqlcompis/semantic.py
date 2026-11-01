"""Visitor semántico SQL: catálogo, ámbitos de tablas y subconsultas anidadas."""

from copy import deepcopy
from dataclasses import dataclass, field
import json

from .model import Node, SQLError
from .types import NUMERIC, assignable, comparable, convert, literal_value, valid_name


@dataclass
class Scope:
    sources: dict = field(default_factory=dict)
    parent: object = None

    def resolve(self, column):
        env, depth = self, 0
        while env is not None:
            matches = []
            qualifier = column['table']
            for alias, schema in env.sources.items():
                if qualifier is not None and qualifier != alias:
                    continue
                matches.extend((depth, alias, c) for c in schema['columns'] if c['name'] == column['name'])
            if len(matches) > 1:
                raise SQLError(f"referencia ambigua a la columna '{column['name']}'", column)
            if matches:
                return matches[0]
            if qualifier in env.sources:
                break
            env, depth = env.parent, depth+1
        name = (column['table']+'.' if column['table'] else '') + column['name']
        raise SQLError(f"columna inexistente o referencia inválida: '{name}'", column)


def contains_aggregate(value):
    if isinstance(value, Node):
        if value.kind == 'aggregate':
            return True
        if value.kind in {'select', 'scalar', 'exists'}:
            return False
        return any(contains_aggregate(v) for v in value.data.values())
    return isinstance(value, list) and any(contains_aggregate(v) for v in value)


def expression_key(node):
    if isinstance(node, Node):
        if node.kind == 'column' and 'binding' in node.meta:
            return ('column', *node.meta['binding'])
        return (node.kind, tuple((k, expression_key(v)) for k, v in node.data.items()))
    if isinstance(node, list):
        return tuple(map(expression_key, node))
    return node


class SemanticAnalyzer:
    def __init__(self, metadata=None):
        self.catalog = deepcopy(metadata or {'version': 1, 'tables': {}, 'indexes': {}})

    def table(self, name, node):
        if name not in self.catalog['tables']:
            raise SQLError(f"tabla inexistente: '{name}'", node)
        return self.catalog['tables'][name]

    def analyze(self, script):
        for statement in script['statements']:
            self.statement(statement)
        return self.catalog

    def statement(self, node):
        kind = node.kind
        if kind == 'create_table':
            name = node['table']
            valid_name(name, node)
            if name in self.catalog['tables']:
                raise SQLError(f"tabla duplicada: '{name}'", node)
            columns, unique, primary = [], [], []
            for element in node['elements']:
                if element.kind != 'column_def':
                    continue
                valid_name(element['name'], element)
                if any(c['name'] == element['name'] for c in columns):
                    raise SQLError(f"columna duplicada: '{element['name']}'", element)
                dtype = element['type']
                if dtype['name'] == 'VARCHAR' and dtype['length'] <= 0:
                    raise SQLError('VARCHAR requiere longitud positiva', dtype)
                column = {'name': element['name'], 'type': dtype['name'], 'length': dtype['length'],
                          'nullable': True, 'has_default': False, 'default': None}
                seen = set()
                for constraint in element['constraints']:
                    if constraint.kind in seen:
                        raise SQLError('restricción duplicada', constraint)
                    seen.add(constraint.kind)
                    if constraint.kind in {'not_null', 'primary'}:
                        column['nullable'] = False
                    if constraint.kind == 'primary':
                        if primary:
                            raise SQLError('la tabla sólo admite una PRIMARY KEY', constraint)
                        primary = [column['name']]
                    elif constraint.kind == 'unique':
                        unique.append([column['name']])
                    elif constraint.kind == 'default':
                        column['has_default'] = True
                        column['default'] = literal_value(constraint['value'])
                if column['has_default']:
                    value = convert(column['default'], column, element)
                    column['default'] = value.isoformat() if hasattr(value, 'isoformat') else value
                columns.append(column)
            for constraint in node['elements']:
                if constraint.kind != 'constraint':
                    continue
                names = constraint['columns']
                if len(set(names)) != len(names) or not set(names) <= {c['name'] for c in columns}:
                    raise SQLError('columnas inválidas en restricción de tabla', constraint)
                if constraint['kind'] == 'primary':
                    if primary:
                        raise SQLError('la tabla sólo admite una PRIMARY KEY', constraint)
                    primary = names
                else:
                    unique.append(names)
            if not columns:
                raise SQLError('una tabla necesita al menos una columna', node)
            for c in columns:
                if c['name'] in primary:
                    c['nullable'] = False
            schema = {'columns': columns, 'primary': primary, 'unique': unique, 'next_id': 1, 'count': 0}
            self.catalog['tables'][name] = schema
            node.meta['schema'] = schema
        elif kind == 'drop_table':
            self.table(node['name'], node)
            del self.catalog['tables'][node['name']]
            self.catalog['indexes'] = {k: v for k, v in self.catalog['indexes'].items() if v['table'] != node['name']}
        elif kind == 'create_index':
            valid_name(node['name'], node)
            schema = self.table(node['table'], node)
            if node['name'] in self.catalog['indexes']:
                raise SQLError(f"índice duplicado: '{node['name']}'", node)
            if node['column'] not in {c['name'] for c in schema['columns']}:
                raise SQLError(f"columna inexistente: '{node['column']}'", node)
            self.catalog['indexes'][node['name']] = {'table': node['table'], 'column': node['column']}
        elif kind == 'drop_index':
            if node['name'] not in self.catalog['indexes']:
                raise SQLError(f"índice inexistente: '{node['name']}'", node)
            del self.catalog['indexes'][node['name']]
        elif kind == 'select':
            self.select(node, None)
        else:
            schema = self.table(node['table'], node)
            scope = Scope({node['table']: schema})
            if kind == 'insert':
                names = node['columns'] or [c['name'] for c in schema['columns']]
                by_name = {c['name']: c for c in schema['columns']}
                if len(set(names)) != len(names) or not set(names) <= by_name.keys():
                    raise SQLError('columnas duplicadas o inexistentes en INSERT', node)
                node.meta['columns'] = names
                for row in node['rows']:
                    if len(row['expressions']) != len(names):
                        raise SQLError('cantidad de valores incorrecta en INSERT', row)
                    for name, value in zip(names, row['expressions']):
                        self.assignment_type(by_name[name], value, Scope())
                for c in schema['columns']:
                    if c['name'] not in names and not c['nullable'] and not c['has_default']:
                        raise SQLError(f"INSERT requiere la columna '{c['name']}'", node)
            elif kind == 'update':
                assigned = set()
                for assignment in node['assignments']:
                    column = next((c for c in schema['columns'] if c['name'] == assignment['column']), None)
                    if column is None or assignment['column'] in assigned:
                        raise SQLError('columna inexistente o repetida en UPDATE', assignment)
                    assigned.add(assignment['column'])
                    self.assignment_type(column, assignment['expression'], scope)
            if kind in {'update', 'delete'} and node['where']:
                self.require_boolean(node['where'], scope)

    def assignment_type(self, column, value, scope):
        actual = self.expression(value, scope, aggregate=False)
        if not assignable(column['type'], actual):
            raise SQLError(f"tipos incompatibles para '{column['name']}': {column['type']} y {actual}", value)
        if value.kind == 'literal' or (value.kind == 'unary' and value['operand'].kind == 'literal'):
            convert(literal_value(value), column, value)

    def require_boolean(self, expr, scope, aggregate=False, aliases=None):
        dtype = self.expression(expr, scope, aggregate=aggregate, aliases=aliases)
        if dtype not in {'BOOLEAN', 'NULL'}:
            raise SQLError('la condición debe ser BOOLEAN', expr)

    def select(self, query, parent):
        scope = Scope(parent=parent)
        sources = ([query['source']] if query['source'] else []) + [j['source'] for j in query['joins']]
        for source in sources:
            alias = source['alias']
            if alias in scope.sources:
                raise SQLError(f"alias de tabla duplicado: '{alias}'", source)
            scope.sources[alias] = self.table(source['table'], source)
            source.meta['schema'] = scope.sources[alias]
        # Cada ON sólo puede referirse a las fuentes ya introducidas.
        join_scope = Scope(parent=parent)
        if query['source']:
            join_scope.sources[query['source']['alias']] = scope.sources[query['source']['alias']]
        for join in query['joins']:
            alias = join['source']['alias']
            join_scope.sources[alias] = scope.sources[alias]
            self.require_boolean(join['on'], join_scope)
        if query['where']:
            self.require_boolean(query['where'], scope)
        projections, aliases = [], {}
        for item in query['items']:
            expr = item['expression']
            if expr.kind == 'star':
                matching = [(a, s) for a, s in scope.sources.items() if expr['table'] is None or a == expr['table']]
                if not matching:
                    raise SQLError('comodín sin tabla válida', expr)
                for alias, schema in matching:
                    for column in schema['columns']:
                        value = Node('column', {'table': alias, 'name': column['name']}, expr.line, expr.column)
                        self.expression(value, scope)
                        projections.append((column['name'], value))
            else:
                self.expression(expr, scope, aggregate=True)
                label = item['alias'] or self.label(expr)
                projections.append((label, expr))
                if item['alias']:
                    if label in aliases:
                        aliases[label] = None
                    else:
                        aliases[label] = expr
        for expr in query['group']:
            self.expression(expr, scope)
        if query['having']:
            self.require_boolean(query['having'], scope, aggregate=True, aliases=aliases)
        for item in query['order']:
            expr = item['expression']
            if expr.kind == 'literal' and expr['type'] == 'INT':
                index = expr['value']-1
                if index < 0 or index >= len(projections):
                    raise SQLError('posición ORDER BY fuera de la proyección', expr)
                expr.meta['alias_expr'] = projections[index][1]
            self.expression(expr, scope, aggregate=True, aliases=aliases)
        aggregate = bool(query['group']) or any(contains_aggregate(e) for _, e in projections) or contains_aggregate(query['having'])
        aggregate = aggregate or any(contains_aggregate(i['expression'].meta.get('alias_expr', i['expression'])) for i in query['order'])
        if query['having'] and not aggregate:
            raise SQLError('HAVING requiere GROUP BY o una agregación', query['having'])
        if aggregate:
            keys = {expression_key(e) for e in query['group']}
            for _, expr in projections:
                self.check_group(expr, keys)
            if query['having']:
                self.check_group(query['having'], keys)
            for order in query['order']:
                self.check_group(order['expression'], keys)
        query.meta.update(projections=projections, types=[e.meta['type'] for _, e in projections], aggregate=aggregate)
        return query.meta['types']

    def check_group(self, expr, keys):
        if 'alias_expr' in expr.meta:
            return self.check_group(expr.meta['alias_expr'], keys)
        if expression_key(expr) in keys or expr.kind in {'aggregate', 'scalar', 'exists'}:
            return
        if expr.kind == 'column' and expr.meta['binding'][0] == 0:
            raise SQLError(f"columna '{expr['name']}' debe aparecer en GROUP BY o una agregación", expr)
        for value in expr.data.values():
            for child in value if isinstance(value, list) else [value]:
                if isinstance(child, Node) and child.kind != 'select':
                    self.check_group(child, keys)

    def expression(self, expr, scope, aggregate=False, aliases=None):
        if 'alias_expr' in expr.meta:
            dtype = self.expression(expr.meta['alias_expr'], scope, aggregate=aggregate)
        elif expr.kind == 'literal':
            if expr['type'] == 'DATE':
                literal_value(expr)
            dtype = expr['type']
        elif expr.kind == 'column':
            if aliases is not None and expr['table'] is None and expr['name'] in aliases:
                target = aliases[expr['name']]
                if target is None:
                    raise SQLError('alias de proyección ambiguo', expr)
                expr.meta['alias_expr'] = target
                dtype = self.expression(target, scope, aggregate=aggregate)
            else:
                depth, alias, col = scope.resolve(expr)
                expr.meta['binding'] = (depth, alias, col['name'])
                dtype = col['type']
        elif expr.kind == 'aggregate':
            if not aggregate:
                raise SQLError('agregación no permitida en esta cláusula o agregaciones anidadas', expr)
            argument = expr['argument']
            if argument.kind == 'star':
                if expr['name'] != 'COUNT':
                    raise SQLError('solamente COUNT admite *', expr)
                source_type = 'INT'
            else:
                source_type = self.expression(argument, scope, aggregate=False)
            if expr['name'] in {'SUM', 'AVG'} and source_type not in NUMERIC | {'NULL'}:
                raise SQLError(f"{expr['name']} requiere un argumento numérico", expr)
            dtype = 'INT' if expr['name'] == 'COUNT' else 'FLOAT' if expr['name'] == 'AVG' else source_type
        elif expr.kind in {'scalar', 'exists'}:
            types = self.select(expr['query'], scope)
            if expr.kind == 'scalar' and len(types) != 1:
                raise SQLError('subconsulta escalar debe retornar una sola columna', expr)
            dtype = 'BOOLEAN' if expr.kind == 'exists' else types[0]
        elif expr.kind == 'in':
            left = self.expression(expr['left'], scope, aggregate, aliases)
            values = expr['values']
            if isinstance(values, Node):
                types = self.select(values, scope)
                if len(types) != 1:
                    raise SQLError('subconsulta IN debe retornar una sola columna', expr)
            else:
                types = [self.expression(v, scope, aggregate, aliases) for v in values]
            if not all(comparable(left, t) for t in types):
                raise SQLError('tipos incompatibles en IN', expr)
            dtype = 'BOOLEAN'
        elif expr.kind == 'is_null':
            self.expression(expr['left'], scope, aggregate, aliases)
            dtype = 'BOOLEAN'
        elif expr.kind == 'unary':
            operand = self.expression(expr['operand'], scope, aggregate, aliases)
            if expr['op'] == 'NOT':
                if operand not in {'BOOLEAN', 'NULL'}:
                    raise SQLError('NOT requiere BOOLEAN', expr)
                dtype = 'BOOLEAN'
            else:
                if operand not in NUMERIC | {'NULL'}:
                    raise SQLError('el signo requiere un número', expr)
                dtype = operand
        elif expr.kind == 'binary':
            left = self.expression(expr['left'], scope, aggregate, aliases)
            right = self.expression(expr['right'], scope, aggregate, aliases)
            op = expr['op']
            if op in {'AND', 'OR'}:
                if not {left, right} <= {'BOOLEAN', 'NULL'}:
                    raise SQLError(f'{op} requiere operandos BOOLEAN', expr)
                dtype = 'BOOLEAN'
            elif op in {'=', '!=', '<>', '<', '<=', '>', '>='}:
                if not comparable(left, right):
                    raise SQLError('tipos incompatibles en comparación', expr)
                for expected, other in [(left, expr['right']), (right, expr['left'])]:
                    if expected == 'DATE' and other.kind == 'literal' and other['type'] == 'VARCHAR':
                        convert(other['value'], {'name': 'comparación', 'type': 'DATE'}, other)
                dtype = 'BOOLEAN'
            else:
                if not {left, right} <= NUMERIC | {'NULL'}:
                    raise SQLError('operación aritmética requiere números', expr)
                dtype = 'FLOAT' if op == '/' or 'FLOAT' in {left, right} else 'INT'
        else:
            raise SQLError(f'expresión no soportada: {expr.kind}', expr)
        expr.meta['type'] = dtype
        return dtype

    def label(self, expr):
        if expr.kind == 'column':
            return expr['name']
        if expr.kind == 'aggregate':
            return f"{expr['name']}({self.label(expr['argument'])})"
        return '*' if expr.kind == 'star' else 'expresion'
