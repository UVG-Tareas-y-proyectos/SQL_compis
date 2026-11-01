import pytest
from sqlcompis.pipeline import SQLEngine
from test_storage import ok
from test_queries import query


def test_unicode_and_sql_escaped_strings_round_trip(tmp_path):
    db = SQLEngine(tmp_path)
    ok(db, "-- nombres en español\nCREATE TABLE t (s VARCHAR(50)); INSERT INTO t VALUES ('José 🐍'),('O''Brien'),('\\N'),('null'); CREATE INDEX ix ON t(s);")
    assert query(SQLEngine(tmp_path), 'SELECT s FROM t;') == [['José 🐍'], ["O'Brien"], ['\\N'], ['null']]
    assert query(db, "SELECT s FROM t WHERE s='José 🐍';") == [['José 🐍']]


@pytest.mark.parametrize('condition', ['x=1','x<>1','x>=2','x<2','x IN (1,2,NULL)',
    'x NOT IN (1,2)','NOT x IN (1,NULL)','NOT x IS NULL',
    'x=1 OR x IS NULL','x>1 AND x<4','x IS NULL OR y=9','y=9 AND x>1'])
def test_null_and_boolean_index_plans_match_scans(tmp_path, condition):
    db = SQLEngine(tmp_path)
    ok(db, 'CREATE TABLE t(x INT, y INT); INSERT INTO t VALUES (1,9),(2,0),(3,9),(NULL,9); CREATE INDEX ix ON t(x);')
    expected = query(db, f'SELECT x,y FROM t WHERE {condition} ORDER BY x;')
    ok(db, 'DROP INDEX ix;')
    assert query(db, f'SELECT x,y FROM t WHERE {condition} ORDER BY x;') == expected


def test_date_and_boolean_indexes(tmp_path):
    db = SQLEngine(tmp_path)
    ok(db, "CREATE TABLE t(id INT, d DATE, b BOOLEAN); INSERT INTO t VALUES (1,'2026-01-01',TRUE),(2,'2026-11-01',FALSE),(3,NULL,NULL); CREATE INDEX ix_d ON t(d); CREATE INDEX ix_b ON t(b);")
    assert query(db, "SELECT id FROM t WHERE d>='2026-10-01';") == [[2]]
    assert query(db, 'SELECT id FROM t WHERE b=TRUE;') == [[1]]
    assert query(db, 'SELECT id FROM t WHERE b IS NULL;') == [[3]]
    assert not db.execute("SELECT id FROM t WHERE d='2026-02-30';").ok


def test_correlated_nested_scopes_and_empty_scalar(tmp_path):
    db = SQLEngine(tmp_path)
    ok(db, 'CREATE TABLE t(id INT); INSERT INTO t VALUES (1),(2),(3); CREATE INDEX ix ON t(id);')
    assert query(db, 'SELECT a.id FROM t a WHERE EXISTS (SELECT 1 FROM t b WHERE b.id=a.id AND EXISTS (SELECT 1 FROM t c WHERE c.id=b.id AND c.id=2));') == [[2]]


def test_failed_scalar_delete_is_atomic(tmp_path):
    db = SQLEngine(tmp_path)
    ok(db, 'CREATE TABLE t(id INT); INSERT INTO t VALUES (1),(2);')
    assert not db.execute('DELETE FROM t WHERE id=(SELECT id FROM t);').ok
    assert query(db, 'SELECT id FROM t ORDER BY id;') == [[1],[2]]


def test_multiple_assignments_use_original_row(tmp_path):
    db = SQLEngine(tmp_path)
    ok(db, 'CREATE TABLE t(a INT,b INT); INSERT INTO t VALUES (1,2); UPDATE t SET a=b,b=a;')
    assert query(db, 'SELECT * FROM t;') == [[2,1]]


def test_storage_rolls_back_io_failure(tmp_path, monkeypatch):
    db = SQLEngine(tmp_path)
    ok(db, 'CREATE TABLE t(id INT); INSERT INTO t VALUES (1); CREATE INDEX ix ON t(id);')
    original = db.storage.atomic_write
    failed = False
    def fail_once(name, data):
        nonlocal failed
        if name == 'offsets/t.json' and not failed:
            failed = True
            raise OSError('fallo simulado')
        return original(name, data)
    monkeypatch.setattr(db.storage, 'atomic_write', fail_once)
    assert not db.execute('INSERT INTO t VALUES (2);').ok
    assert query(SQLEngine(tmp_path), 'SELECT id FROM t WHERE id>=1 ORDER BY id;') == [[1]]
