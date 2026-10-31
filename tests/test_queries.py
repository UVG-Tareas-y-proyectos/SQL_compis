import pytest
from sqlcompis.pipeline import SQLEngine
from test_storage import ok


@pytest.fixture
def db(tmp_path):
    engine = SQLEngine(tmp_path)
    ok(engine, "CREATE TABLE estudiantes (id INT PRIMARY KEY, nombre VARCHAR(30), edad INT, activo BOOLEAN); INSERT INTO estudiantes VALUES (1,'Ana',20,TRUE), (2,'Luis',17,FALSE), (3,'Eva',22,TRUE), (4,'Sol',NULL,NULL);")
    return engine


def query(db, sql):
    return ok(db, sql).results[-1].rows


@pytest.mark.parametrize(('sql','expected'), [
    ('SELECT nombre FROM estudiantes WHERE edad >= 18 ORDER BY nombre;', [['Ana'], ['Eva']]),
    ('SELECT nombre FROM estudiantes WHERE activo AND edad > 20;', [['Eva']]),
    ('SELECT nombre FROM estudiantes WHERE NOT activo OR edad IS NULL ORDER BY id;', [['Luis'], ['Sol']]),
    ('SELECT nombre FROM estudiantes ORDER BY edad DESC;', [['Eva'], ['Ana'], ['Luis'], ['Sol']]),
    ('SELECT DISTINCT activo FROM estudiantes ORDER BY activo;', [[None], [False], [True]]),
    ('SELECT 2+3*4 AS resultado;', [[14]]),
    ('SELECT NULL = NULL, TRUE AND NULL, FALSE OR NULL;', [[None, None, None]]),
])
def test_select_where_and_order(db, sql, expected):
    assert query(db, sql) == expected


def test_update_and_delete_persist(db, tmp_path):
    ok(db, 'UPDATE estudiantes SET edad = edad + 1 WHERE activo = TRUE;')
    ok(db, 'DELETE FROM estudiantes WHERE edad < 18;')
    assert query(SQLEngine(tmp_path), 'SELECT id, edad FROM estudiantes ORDER BY id;') == [[1,21],[3,23],[4,None]]


def test_update_uses_original_values_and_rolls_back_uniqueness(db):
    assert not db.execute('UPDATE estudiantes SET id = 1;').ok
    assert query(db, 'SELECT id FROM estudiantes ORDER BY id;') == [[1],[2],[3],[4]]


def test_scalar_cardinality_error_does_not_modify_rows(db):
    result = db.execute('UPDATE estudiantes SET edad = (SELECT edad FROM estudiantes);')
    assert not result.ok and 'más de un registro' in result.diagnostics[0].message
    assert query(db, 'SELECT edad FROM estudiantes WHERE id=1;') == [[20]]
