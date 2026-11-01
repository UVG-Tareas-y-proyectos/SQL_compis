import json
import pytest
from sqlcompis.pipeline import SQLEngine
from test_storage import ok
from test_queries import query


@pytest.fixture
def db(tmp_path):
    engine = SQLEngine(tmp_path)
    ok(engine, 'CREATE TABLE t (id INT PRIMARY KEY, edad INT, nombre VARCHAR(20)); CREATE TABLE s (id INT, curso INT);')
    values = ','.join(f"({i},{i%30},'n{i}')" for i in range(1,101))
    ok(engine, 'INSERT INTO t VALUES '+values+'; INSERT INTO s VALUES (2,3),(4,3),(8,2); CREATE INDEX ix_id ON t(id); CREATE INDEX ix_edad ON t(edad);')
    return engine


def test_index_really_reads_only_candidates(db, monkeypatch):
    original = db.storage.rows
    def forbid_full_scan(name, ids=None):
        assert ids is not None, 'SELECT no debe recorrer todos los registros de t'
        return original(name, ids)
    monkeypatch.setattr(db.storage, 'rows', forbid_full_scan)
    result = ok(db, 'SELECT nombre FROM t WHERE id=50;').results[0]
    assert result.rows == [['n50']]
    assert result.plan[-1]['rows_read'] == 1
    assert result.plan[-1]['total_rows'] == 100
    assert result.plan[-1]['indexes'] == ['ix_id']


@pytest.mark.parametrize('condition', ['id>=95', 'id IN (2,4,8)', 'id NOT IN (2,NULL)',
    'id=2 OR id=4', 'id>90 AND edad<10', 'NOT (id <= 95)', '2 < id', 'edad IS NULL', 'edad IS NOT NULL'])
def test_index_and_scan_are_equivalent(db, condition):
    indexed = query(db, f'SELECT id FROM t WHERE {condition} ORDER BY id;')
    ok(db, 'DROP INDEX ix_id; DROP INDEX ix_edad;')
    scanned = query(db, f'SELECT id FROM t WHERE {condition} ORDER BY id;')
    assert indexed == scanned


def test_or_with_unindexed_branch_does_not_lose_rows(db):
    assert query(db, "SELECT id FROM t WHERE id=2 OR nombre='n99' ORDER BY id;") == [[2],[99]]


def test_indexes_are_updated_and_persist_across_restart(db):
    ok(db, "INSERT INTO t VALUES (101,21,'extra'); UPDATE t SET edad=29 WHERE id=101; DELETE FROM t WHERE id=2;")
    reopened = SQLEngine(db.storage.root)
    assert query(reopened, 'SELECT nombre FROM t WHERE id=101;') == [['extra']]
    assert query(reopened, 'SELECT id FROM t WHERE id=2;') == []
    indexed_ids = {row[0] for row in query(reopened, 'SELECT id FROM t WHERE edad=29;')}
    assert 101 in indexed_ids
    data = json.loads((db.storage.root/'indexes/ix_id.json').read_text())
    assert '2' not in data['entries'] and '101' in data['entries']


@pytest.mark.parametrize(('sql', 'expected'), [
    ('SELECT id FROM t WHERE id IN (SELECT id FROM s WHERE curso=3) ORDER BY id;', [[2],[4]]),
    ('SELECT id FROM s WHERE id NOT IN (SELECT id FROM t WHERE id<4) ORDER BY id;', [[4],[8]]),
    ('SELECT id FROM t x WHERE EXISTS (SELECT 1 FROM s WHERE s.id=x.id) ORDER BY id;', [[2],[4],[8]]),
    ('SELECT id FROM s WHERE NOT EXISTS (SELECT 1 FROM t WHERE t.id=s.id AND t.id<4) ORDER BY id;', [[4],[8]]),
    ('SELECT id FROM t WHERE id=(SELECT MAX(id) FROM s);', [[8]]),
    ('SELECT id FROM t WHERE id > (SELECT AVG(id) FROM s) AND id<7 ORDER BY id;', [[5],[6]]),
    ('SELECT (SELECT id FROM s WHERE id=999);', [[None]]),
])
def test_nested_queries(db, sql, expected):
    assert query(db, sql) == expected


def test_invalid_scalar_cardinality_is_semantic_error(db):
    result = db.execute('SELECT id FROM t WHERE id=(SELECT id FROM s);')
    assert not result.ok
    assert result.diagnostics[0].phase == 'semántico'
    assert 'más de un registro' in result.diagnostics[0].message


def test_null_in_semantics(tmp_path):
    engine = SQLEngine(tmp_path)
    ok(engine, 'CREATE TABLE t(x INT); INSERT INTO t VALUES (1),(NULL); CREATE INDEX ix ON t(x);')
    assert query(engine, 'SELECT x FROM t WHERE x NOT IN (2,NULL);') == []
    assert query(engine, 'SELECT x FROM t WHERE x IN (SELECT x FROM t WHERE x=999);') == []
    assert query(engine, 'SELECT x FROM t WHERE x NOT IN (SELECT x FROM t WHERE x=999);') == [[1],[None]]


def test_drop_table_removes_index_files(db):
    ok(db, 'DROP TABLE t;')
    assert not (db.storage.root/'indexes/ix_id.json').exists()
    assert not db.storage.metadata['indexes']


def test_uncorrelated_scalar_uses_index_and_is_evaluated_once(db):
    result = ok(db, 'SELECT id FROM t WHERE id=(SELECT MAX(id) FROM s);').results[0]
    assert result.rows == [[8]]
    access = next(p for p in result.plan if p['table'] == 't')
    assert access['access'] == 'índice' and access['rows_read'] == 1
    assert len([p for p in result.plan if p['table'] == 's']) == 1


def test_in_subquery_with_order_alias_does_not_require_binding_on_alias(db):
    result = ok(db, 'SELECT id FROM t WHERE id IN (SELECT id AS x FROM s ORDER BY x) ORDER BY id;').results[0]
    assert result.rows == [[2], [4], [8]]
    assert len([p for p in result.plan if p['table'] == 's']) == 1
