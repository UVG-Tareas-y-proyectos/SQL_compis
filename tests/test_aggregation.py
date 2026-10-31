import pytest
from sqlcompis.pipeline import SQLEngine
from test_storage import ok
from test_queries import query


@pytest.fixture
def db(tmp_path):
    engine = SQLEngine(tmp_path)
    ok(engine, "CREATE TABLE estudiantes (id INT PRIMARY KEY, nombre VARCHAR(20)); CREATE TABLE notas (estudiante_id INT, curso VARCHAR(10), nota FLOAT); INSERT INTO estudiantes VALUES (1,'Ana'),(2,'Luis'),(3,'Eva'); INSERT INTO notas VALUES (1,'Compis',90),(1,'SQL',80),(2,'Compis',70),(2,'SQL',NULL);")
    return engine


def test_inner_join_group_and_having(db):
    rows = query(db, 'SELECT e.nombre, COUNT(*) AS n, AVG(n.nota) AS promedio FROM estudiantes e INNER JOIN notas n ON e.id=n.estudiante_id GROUP BY e.nombre HAVING AVG(n.nota) >= 80 ORDER BY promedio DESC;')
    assert rows == [['Ana', 2, 85.0]]


def test_all_aggregates_ignore_null(db):
    assert query(db, 'SELECT COUNT(*), COUNT(nota), SUM(nota), AVG(nota), MIN(nota), MAX(nota) FROM notas;') == [[4,3,240.0,80.0,70.0,90.0]]


def test_empty_group_and_empty_input(db):
    assert query(db, 'SELECT COUNT(*), SUM(nota), AVG(nota), MIN(nota), MAX(nota) FROM notas WHERE nota > 100;') == [[0,None,None,None,None]]
    assert query(db, 'SELECT curso, COUNT(*) FROM notas WHERE nota > 100 GROUP BY curso;') == []


def test_null_groups_and_multiple_order_keys(db):
    assert query(db, 'SELECT curso, COUNT(nota) AS cantidad FROM notas GROUP BY curso ORDER BY cantidad DESC, curso;') == [['Compis',2],['SQL',1]]


def test_self_join_and_star_projection(db):
    assert query(db, 'SELECT a.nombre, b.nombre FROM estudiantes a JOIN estudiantes b ON a.id < b.id ORDER BY a.id, b.id;') == [['Ana','Luis'],['Ana','Eva'],['Luis','Eva']]


def test_min_max_dates_and_text(tmp_path):
    engine = SQLEngine(tmp_path)
    ok(engine, "CREATE TABLE t(d DATE, s VARCHAR(10)); INSERT INTO t VALUES ('2026-01-01','b'),('2026-10-01','a');")
    assert query(engine, 'SELECT MIN(s), MAX(s) FROM t;') == [['a','b']]
    assert str(query(engine, 'SELECT MAX(d) FROM t;')[0][0]) == '2026-10-01'


def test_having_without_explicit_group(db):
    assert query(db, 'SELECT COUNT(*) AS n FROM notas HAVING COUNT(*) > 2;') == [[4]]


def test_nested_aggregate_is_rejected(db):
    result = db.execute('SELECT SUM(AVG(nota)) FROM notas;')
    assert not result.ok and 'anidadas' in result.diagnostics[0].message
