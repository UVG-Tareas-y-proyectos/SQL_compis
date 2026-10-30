import base64
import json
from datetime import date
from sqlcompis.pipeline import SQLEngine
from sqlcompis.storage import FileStorage


def ok(engine, sql):
    result = engine.execute(sql)
    assert result.ok, [str(d) for d in result.diagnostics]
    return result


def test_persistence_of_schema_types_and_records(tmp_path):
    engine = SQLEngine(tmp_path)
    ok(engine, "CREATE TABLE t (id INT PRIMARY KEY, nombre VARCHAR(30), f FLOAT, b BOOLEAN, d DATE);")
    ok(engine, "INSERT INTO t VALUES (1, 'O''Brien, UVG', 2, TRUE, '2026-11-01'), (2, NULL, 2.5, FALSE, NULL);")
    restarted = FileStorage(tmp_path)
    assert restarted.rows('t')[0]['d'] == date(2026, 11, 1)
    assert restarted.rows('t')[0]['nombre'] == "O'Brien, UVG"
    assert restarted.rows('t', {2})[0]['b'] is False
    assert (tmp_path / 'metadata.json').exists()
    assert (tmp_path / 'tables/t.csv').exists()


def test_insert_is_atomic_and_respects_constraints(tmp_path):
    engine = SQLEngine(tmp_path)
    ok(engine, 'CREATE TABLE t (id INT PRIMARY KEY, s VARCHAR(3) NOT NULL);')
    result = engine.execute("INSERT INTO t VALUES (1, 'a'), (1, 'b');")
    assert not result.ok
    assert engine.storage.rows('t') == []
    ok(engine, "INSERT INTO t VALUES (2, 'b');")
    assert engine.storage.rows('t')[0]['__rid'] == 1


def test_analyze_does_not_execute_ddl(tmp_path):
    engine = SQLEngine(tmp_path)
    assert engine.analyze('CREATE TABLE t (id INT); INSERT INTO t VALUES (1);').ok
    assert not (tmp_path / 'metadata.json').exists()


def test_recovery_rolls_back_interrupted_write(tmp_path):
    path = tmp_path / 'metadata.json'
    original = b'{"version":1,"tables":{},"indexes":{}}'
    path.write_bytes(b'write interrupted')
    (tmp_path / 'journal.json').write_text(json.dumps({'metadata.json': base64.b64encode(original).decode()}))
    recovered = FileStorage(tmp_path)
    assert recovered.metadata['tables'] == {}
    assert path.read_bytes() == original
    assert not (tmp_path / 'journal.json').exists()


def test_defaults_composite_primary_and_drop(tmp_path):
    engine = SQLEngine(tmp_path)
    ok(engine, "CREATE TABLE t (a INT, b INT, s VARCHAR(3) DEFAULT 'x', PRIMARY KEY(a,b));")
    ok(engine, 'INSERT INTO t(a,b) VALUES (1,2), (1,3);')
    assert engine.storage.rows('t')[0]['s'] == 'x'
    assert not engine.execute('INSERT INTO t(a,b) VALUES (1,2);').ok
    ok(engine, 'DROP TABLE t;')
    assert not (tmp_path / 'tables/t.csv').exists()
