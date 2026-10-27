import pytest
from sqlcompis.frontend import SQLFrontend


@pytest.fixture(scope='module')
def frontend():
    return SQLFrontend()


@pytest.mark.parametrize('sql', [
    'SELECT nombre FROM estudiantes WHERE edad >= 18;',
    "create table t (id int primary key, nombre varchar(20) not null, f date, b boolean);",
    "INSERT INTO t VALUES (1, 'O''Brien', DATE '2026-11-01', TRUE);",
    'SELECT e.nombre, COUNT(*) AS n FROM estudiantes e INNER JOIN cursos c ON e.id = c.id GROUP BY e.nombre HAVING COUNT(*) > 1 ORDER BY n DESC;',
    'SELECT id FROM t WHERE id IN (SELECT id FROM s) AND NOT EXISTS (SELECT 1 FROM z WHERE z.id = t.id);',
    'CREATE INDEX ix ON t (id); DROP INDEX ix; UPDATE t SET id = id + 1 WHERE id <> 3; DELETE FROM t; DROP TABLE t;',
    'SELECT (SELECT MAX(id) FROM t) FROM s WHERE id NOT IN (1, 2, 3);',
    'SELECT "nombre" FROM "estudiantes"',
])
def test_sql_grammar(frontend, sql):
    result = frontend.parse(sql)
    assert result.ok, [str(d) for d in result.diagnostics]
    assert result.tree.rule == 'script'


def test_positions_and_errors(frontend):
    assert frontend.parse('SELECT @;').diagnostics[0].phase == 'léxico'
    error = frontend.parse('SELECT FROM t;').diagnostics[0]
    assert error.phase == 'sintáctico' and error.line == 1 and error.column > 1
    tokens = frontend.parse("-- comentario\nSELECT 'Hola';").tokens
    assert tokens[0].type == 'SELECT' and tokens[0].line == 2


def test_no_slr_conflicts(frontend):
    assert frontend.table.conflicts == []
