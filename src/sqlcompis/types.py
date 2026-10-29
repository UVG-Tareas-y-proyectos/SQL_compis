"""Tipos SQL y conversiones comprobadas, sin delegar a un DBMS."""

from datetime import date
import math
import re

from .model import SQLError

NUMERIC = {'INT', 'FLOAT'}


def valid_name(name, node=None):
    if not re.fullmatch(r'[a-z_][a-z0-9_]*', name) or name.startswith('__'):
        raise SQLError(f'identificador no permitido: {name!r}', node)


def comparable(left, right):
    return (left == 'NULL' or right == 'NULL' or left == right
            or {left, right} <= NUMERIC or {left, right} == {'DATE', 'VARCHAR'})


def assignable(expected, actual):
    return actual == 'NULL' or expected == actual or (expected, actual) in {('FLOAT', 'INT'), ('DATE', 'VARCHAR')}


def convert(value, column, node=None):
    if value is None:
        if not column.get('nullable', True):
            raise SQLError(f"la columna '{column['name']}' no acepta NULL", node)
        return None
    expected = column['type']
    if expected == 'INT' and type(value) is int:
        return value
    if expected == 'FLOAT' and type(value) in {int, float}:
        value = float(value)
        if math.isfinite(value):
            return value
    if expected == 'BOOLEAN' and type(value) is bool:
        return value
    if expected == 'VARCHAR' and isinstance(value, str):
        if len(value) > column['length']:
            raise SQLError(f"'{column['name']}' excede VARCHAR({column['length']})", node)
        return value
    if expected == 'DATE':
        if isinstance(value, date):
            return value
        if isinstance(value, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            try:
                return date.fromisoformat(value)
            except ValueError:
                pass
        raise SQLError(f"fecha inválida para '{column['name']}': se requiere YYYY-MM-DD", node)
    raise SQLError(f"tipo incompatible para '{column['name']}': se esperaba {expected}", node)


def literal_value(node):
    if node.kind == 'literal':
        if node['type'] == 'DATE':
            return convert(node['value'], {'name': 'literal', 'type': 'DATE'}, node)
        return node['value']
    if node.kind == 'unary' and node['op'] in {'+', '-'}:
        value = literal_value(node['operand'])
        return value if node['op'] == '+' else -value
    raise ValueError('no es un literal')
