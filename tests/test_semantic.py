import pytest
from sqlcompis.frontend import SQLFrontend
from sqlcompis.ast_builder import ASTBuilder
from sqlcompis.semantic import SemanticAnalyzer
from sqlcompis.model import SQLError

SCHEMA = 'CREATE TABLE t (id INT PRIMARY KEY, nombre VARCHAR(5), edad INT, fecha DATE); CREATE TABLE s (id INT, valor FLOAT);'


def analyze(sql):
    parsed = SQLFrontend().parse(SCHEMA+sql)
    assert parsed.ok, parsed.diagnostics
    ast = ASTBuilder().visit(parsed.tree)
    SemanticAnalyzer().analyze(ast)
    return ast


@pytest.mark.parametrize('sql', [
    'SELECT t.nombre FROM t INNER JOIN s ON t.id = s.id;',
    "INSERT INTO t VALUES (1, 'Ana', 20, '2026-11-01');",
    'SELECT edad, COUNT(*) AS n FROM t GROUP BY edad HAVING n > 1 ORDER BY n DESC;',
    'SELECT nombre FROM t WHERE EXISTS (SELECT 1 FROM s WHERE s.id = t.id);',
    'SELECT nombre FROM t WHERE edad > (SELECT AVG(edad) FROM t);',
])
def test_valid(sql):
    analyze(sql)


@pytest.mark.parametrize(('sql', 'message'), [
    ('SELECT * FROM fantasma;', 'tabla inexistente'),
    ('SELECT xyz FROM t;', 'columna inexistente'),
    ('SELECT id FROM t JOIN s ON t.id = s.id;', 'ambigua'),
    ("INSERT INTO t VALUES (1, 'demasiado', 2, NULL);", 'VARCHAR'),
    ("INSERT INTO t VALUES (1, 'Ana', TRUE, NULL);", 'incompatibles'),
    ("INSERT INTO t VALUES (1, 'Ana', 2, '2026-02-30');", 'fecha inválida'),
    ('INSERT INTO t VALUES (1);', 'cantidad'),
    ('SELECT nombre, COUNT(*) FROM t;', 'GROUP BY'),
    ('SELECT * FROM t WHERE COUNT(*) > 1;', 'agregación'),
    ('SELECT SUM(nombre) FROM t;', 'numérico'),
    ('SELECT * FROM t WHERE edad > (SELECT id, valor FROM s);', 'sola columna'),
    ('CREATE INDEX ix ON t(id); CREATE INDEX ix ON t(edad);', 'duplicado'),
    ('DROP INDEX ausente;', 'inexistente'),
    ('SELECT * FROM t WHERE 1;', 'BOOLEAN'),
])
def test_invalid(sql, message):
    with pytest.raises(SQLError, match=message) as error:
        analyze(sql)
    assert error.value.diagnostic.line > 0 and error.value.diagnostic.column > 0
