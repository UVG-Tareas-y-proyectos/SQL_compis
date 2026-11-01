import importlib.util
import json
from pathlib import Path
import subprocess
import sys

from sqlcompis.frontend import SQLFrontend
from sqlcompis.pipeline import SQLEngine

ROOT = Path(__file__).resolve().parents[1]


def cli(db, *args):
    return subprocess.run([sys.executable, str(ROOT / 'scripts/sqlcompis.py'),
        '--db', str(db), *args], capture_output=True, encoding='utf-8')


def test_cli_demo_persistence_and_index_plan(tmp_path):
    output = cli(tmp_path, str(ROOT / 'examples/demo_completa.sql'), '--json')
    assert output.returncode == 0, output.stderr
    data = json.loads(output.stdout)
    assert data['ok'] and len(data['results']) == 17
    assert data['results'][8]['rows'] == [['José', 22], ['Ana', 20]]
    assert data['results'][8]['plan'][0]['rows_read'] == 2
    assert data['results'][8]['plan'][0]['access'] == 'índice'
    again = cli(tmp_path, '-c', 'SELECT nombre FROM estudiantes WHERE edad=18;', '--json')
    assert json.loads(again.stdout)['results'][0]['rows'] == [['Luis']]


def test_cli_analysis_does_not_create_table_and_exports_trees(tmp_path):
    output = cli(tmp_path, '-c', 'CREATE TABLE t(id INT);', '--analizar', '--tokens', '--arbol', '--ast', '--json')
    data = json.loads(output.stdout)
    assert output.returncode == 0 and data['ok']
    assert data['tokens'] and data['tree'] and data['ast']
    assert not SQLEngine(tmp_path).storage.metadata['tables']


def test_cli_errors_are_nonzero_and_located(tmp_path):
    output = cli(tmp_path, '-c', 'SELECT FROM t;', '--json')
    data = json.loads(output.stdout)
    assert output.returncode == 1 and not data['ok']
    assert data['diagnostics'][0]['line'] == 1
    assert cli(tmp_path, str(tmp_path / 'inexistente.sql')).returncode == 2


def test_regenerate_own_frontend_without_cache(tmp_path):
    parser = SQLFrontend(generated=tmp_path / 'generated')
    parsed = parser.parse("CREATE TABLE t(id INT); SELECT 1 + 2 * 3;")
    assert parsed.ok
    assert not parser.table.conflicts


def test_gui_executes_demo_clears_results_and_shows_errors(tmp_path):
    spec = importlib.util.spec_from_file_location('sql_ide', ROOT / 'scripts/ide.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    app = module.SQLIDE(tmp_path)
    app.withdraw()
    try:
        assert app.result.ok and not app.engine.storage.metadata['tables']
        app.execute()
        assert app.result.ok
        assert len(app.result_tree.get_children()) == 4
        assert app.plan_tree.get_children()
        app.load('SELECT no_existe FROM estudiantes;')
        app.analyze()
        assert not app.result.ok and app.error_tree.get_children()
        assert not app.result_tree.get_children()
        assert not app.plan_tree.get_children()
        item = app.error_tree.get_children()[0]
        app.error_tree.selection_set(item)
        app.go_to_error()
        assert app.editor.index('insert').startswith('1.')
        app.load('SELECT COUNT(*) AS total FROM estudiantes;')
        app.execute()
        assert app.result.ok and app.result.results[0].rows == [[4]]
        assert not app.error_tree.get_children()
    finally:
        app.destroy()
