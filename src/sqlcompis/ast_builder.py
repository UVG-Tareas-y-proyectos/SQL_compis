"""Segunda pasada sobre el árbol concreto: elimina puntuación y reglas auxiliares."""

from .model import Node


def identifier(token):
    return token.value.strip('"').lower()


class ASTBuilder:
    LISTS = {'statements', 'table_elements', 'value_rows', 'assignments',
             'select_items', 'joins', 'order_items', 'expressions', 'column_constraints'}
    WRAPPERS = {'statement', 'table_element', 'expression', 'primary', 'in_values', 'aggregate_arg'}

    def make(self, origin, tag, **data):
        return Node(tag, data, origin.line, origin.column)

    def visit(self, p):
        h, trees, tokens = p.rule, p.trees, p.tokens
        values = lambda: [self.visit(c) for c in trees]
        ids = [identifier(t) for t in tokens if t.type == 'ID']
        if h in self.LISTS:
            result = []
            for child in trees:
                value = self.visit(child)
                result.extend(value if isinstance(value, list) else [value])
            return result
        if h == 'identifiers':
            return (self.visit(trees[0]) if trees else []) + ids
        if h in self.WRAPPERS:
            if tokens and tokens[0].type == 'STAR':
                return self.make(p, 'star', table=None)
            return self.visit(trees[0])
        if h == 'script':
            return self.make(p, 'script', statements=self.visit(trees[0]))
        if h == 'create_table':
            return self.make(p, h, table=ids[0], elements=self.visit(trees[0]))
        if h in {'drop_table', 'drop_index'}:
            return self.make(p, h, name=ids[0])
        if h == 'create_index':
            return self.make(p, h, name=ids[0], table=ids[1], column=ids[2])
        if h == 'column_def':
            return self.make(p, h, name=ids[0], type=self.visit(trees[0]), constraints=self.visit(trees[1]))
        if h == 'data_type':
            length = next((int(t.value) for t in tokens if t.type == 'NUMBER'), None)
            return self.make(p, 'type', name=tokens[0].type, length=length)
        if h == 'column_constraint':
            kind = {'NOT': 'not_null', 'PRIMARY': 'primary', 'UNIQUE': 'unique', 'DEFAULT': 'default'}[tokens[0].type]
            return self.make(p, kind, value=self.visit(trees[0]) if trees else None)
        if h == 'table_constraint':
            return self.make(p, 'constraint', kind='primary' if tokens[0].type == 'PRIMARY' else 'unique', columns=self.visit(trees[0]))
        if h == 'insert_stmt':
            return self.make(p, 'insert', table=ids[0], columns=self.visit(trees[0]), rows=self.visit(trees[1]))
        if h == 'insert_columns':
            return self.visit(trees[0]) if trees else None
        if h == 'value_row':
            return self.make(p, 'values', expressions=self.visit(trees[0]))
        if h == 'assignment':
            return self.make(p, h, column=ids[0], expression=self.visit(trees[0]))
        if h == 'update_stmt':
            return self.make(p, 'update', table=ids[0], assignments=self.visit(trees[0]), where=self.visit(trees[1]))
        if h == 'delete_stmt':
            return self.make(p, 'delete', table=ids[0], where=self.visit(trees[0]))
        if h == 'select_stmt':
            distinct, items, source, where, group, having, order = values()
            return self.make(p, 'select', distinct=distinct, items=items, source=source[0], joins=source[1],
                             where=where, group=group, having=having, order=order)
        if h == 'distinct_clause':
            return bool(tokens)
        if h == 'select_item':
            expr = self.make(p, 'star', table=ids[0] if ids else None) if tokens else self.visit(trees[0])
            return self.make(p, 'item', expression=expr, alias=self.visit(trees[1]) if trees else None)
        if h in {'select_alias', 'table_alias'}:
            return ids[0] if ids else None
        if h == 'table_ref':
            return self.make(p, 'source', table=ids[0], alias=self.visit(trees[0]) or ids[0])
        if h == 'from_clause':
            return (self.visit(trees[0]), self.visit(trees[1])) if trees else (None, [])
        if h == 'join_clause':
            return self.make(p, 'join', source=self.visit(trees[0]), on=self.visit(trees[1]))
        if h in {'where_clause', 'having_clause'}:
            return self.visit(trees[0]) if trees else None
        if h in {'group_clause', 'order_clause'}:
            return self.visit(trees[0]) if trees else []
        if h == 'order_item':
            return self.make(p, h, expression=self.visit(trees[0]), descending=self.visit(trees[1]))
        if h == 'direction':
            return bool(tokens and tokens[0].type == 'DESC')
        if h in {'or_expr', 'and_expr', 'additive', 'multiplicative'}:
            if len(trees) == 1:
                return self.visit(trees[0])
            return self.make(p, 'binary', op=tokens[0].value.upper(), left=self.visit(trees[0]), right=self.visit(trees[1]))
        if h in {'unary', 'not_expr'}:
            return (self.make(p, 'unary', op=tokens[0].value.upper(), operand=self.visit(trees[0]))
                    if tokens else self.visit(trees[0]))
        if h == 'predicate':
            left, tail = values()
            return self.make(p, tail.pop('kind'), left=left, **tail) if tail else left
        if h == 'predicate_tail':
            if not tokens and not trees:
                return None
            if trees and trees[0].rule == 'comparison':
                return {'kind': 'binary', 'op': self.visit(trees[0]), 'right': self.visit(trees[1])}
            if tokens[0].type == 'IS':
                return {'kind': 'is_null', 'negated': any(t.type == 'NOT' for t in tokens)}
            return {'kind': 'in', 'negated': tokens[0].type == 'NOT', 'values': self.visit(trees[0])}
        if h == 'comparison':
            return tokens[0].value
        if h == 'column_ref':
            return self.make(p, 'column', table=ids[0] if len(ids) == 2 else None, name=ids[-1])
        if h == 'aggregate':
            return self.make(p, h, name=self.visit(trees[0]), argument=self.visit(trees[1]))
        if h == 'aggregate_name':
            return tokens[0].type
        if h in {'scalar_query', 'exists_expr'}:
            return self.make(p, 'scalar' if h == 'scalar_query' else 'exists', query=self.visit(trees[0]))
        if h == 'signed_literal':
            if trees:
                return self.visit(trees[0])
            value = float(tokens[-1].value) if tokens[-1].type == 'REAL' else int(tokens[-1].value)
            return self.make(p, 'literal', value=-value, type='FLOAT' if isinstance(value, float) else 'INT')
        if h == 'literal':
            kind = tokens[0].type
            raw = tokens[-1].value
            value = (int(raw) if kind == 'NUMBER' else float(raw) if kind == 'REAL'
                     else kind == 'TRUE' if kind in {'TRUE', 'FALSE'} else None if kind == 'NULL'
                     else raw[1:-1].replace("''", "'"))
            type_name = {'NUMBER': 'INT', 'REAL': 'FLOAT', 'STRING': 'VARCHAR', 'TRUE': 'BOOLEAN', 'FALSE': 'BOOLEAN'}.get(kind, kind)
            return self.make(p, 'literal', value=value, type=type_name)
        raise RuntimeError(f'Regla AST sin implementar: {h}')
