from sqlcompis.ast_builder import ASTBuilder
from sqlcompis.frontend import SQLFrontend


def build(sql):
    parsed = SQLFrontend().parse(sql)
    assert parsed.ok, parsed.diagnostics
    return ASTBuilder().visit(parsed.tree)


def test_ast_removes_punctuation_and_preserves_precedence():
    ast = build('SELECT a + b * 2 AS total FROM estudiantes e WHERE NOT e.id IN (1, 2);')
    query = ast['statements'][0]
    expr = query['items'][0]['expression']
    assert expr['op'] == '+' and expr['right']['op'] == '*'
    assert query['items'][0]['alias'] == 'total'
    assert query['source']['alias'] == 'e'
    assert query['where'].kind == 'unary'
    assert query['where']['operand'].kind == 'in'


def test_types_constraints_and_literals():
    ast = build("CREATE TABLE t (id INT PRIMARY KEY, s VARCHAR(5) DEFAULT 'a', PRIMARY KEY(id)); INSERT INTO t VALUES (1, 'O''B');")
    assert ast['statements'][0]['elements'][1]['type']['length'] == 5
    assert ast['statements'][1]['rows'][0]['expressions'][1]['value'] == "O'B"


def test_scalar_and_correlated_subqueries_have_distinct_nodes():
    query = build('SELECT (SELECT MAX(id) FROM t) FROM s WHERE EXISTS (SELECT 1 FROM t WHERE t.id = s.id);')['statements'][0]
    assert query['items'][0]['expression'].kind == 'scalar'
    assert query['where'].kind == 'exists'
