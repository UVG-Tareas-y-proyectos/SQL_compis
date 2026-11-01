"""CLI del intérprete SQL con almacenamiento propio."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from sqlcompis.pipeline import SQLEngine
from sqlcompis.model import SQLError, tree_lines


def display(value):
    return 'NULL' if value is None else 'TRUE' if value is True else 'FALSE' if value is False else str(value)


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description='SQL Compis: intérprete con archivos propios')
    parser.add_argument('archivo', nargs='?', type=Path, help='archivo fuente .sql')
    parser.add_argument('-c', '--consulta', help='sentencias SQL escritas directamente')
    parser.add_argument('--db', type=Path, default=ROOT / 'database', help='directorio de la base de datos')
    parser.add_argument('--analizar', action='store_true', help='validar sin ejecutar ni modificar datos')
    parser.add_argument('--tokens', action='store_true')
    parser.add_argument('--arbol', action='store_true', help='mostrar árbol sintáctico concreto')
    parser.add_argument('--ast', action='store_true', help='mostrar árbol abstracto')
    parser.add_argument('--plan', action='store_true', help='mostrar uso de índices y filas leídas')
    parser.add_argument('--json', action='store_true', help='salida estructurada para pruebas o integración')
    args = parser.parse_args(argv)
    if (args.archivo is None) == (args.consulta is None):
        parser.error('indique un archivo .sql o una consulta con -c')
    try:
        sql = args.archivo.read_text(encoding='utf-8-sig') if args.archivo else args.consulta
        engine = SQLEngine(args.db)
        result = engine.analyze(sql) if args.analizar else engine.execute(sql)
    except OSError as exc:
        print(f'No se pudo abrir el archivo: {exc}', file=sys.stderr)
        return 2
    except SQLError as exc:
        print(exc.diagnostic, file=sys.stderr)
        return 1
    if args.json:
        payload = {'ok': result.ok, 'diagnostics': [asdict(d) for d in result.diagnostics],
                   'results': [asdict(r) for r in result.results]}
        if args.tokens:
            payload['tokens'] = [asdict(t) for t in result.tokens]
        if args.arbol and result.tree:
            payload['tree'] = list(tree_lines(result.tree))
        if args.ast and result.ast:
            payload['ast'] = list(tree_lines(result.ast))
        print(json.dumps(payload, ensure_ascii=False, default=str, indent=2))
    else:
        if args.tokens:
            print('=== Tokens ===')
            for token in result.tokens:
                print(f'{token.type:<14} {token.value!r:<28} L{token.line}:C{token.column}')
        for requested, value, title in [(args.arbol, result.tree, 'Árbol sintáctico'), (args.ast, result.ast, 'AST')]:
            if requested and value:
                print(f'\n=== {title} ===')
                print('\n'.join(tree_lines(value)))
        for diagnostic in result.diagnostics:
            print(diagnostic, file=sys.stderr)
        for number, output in enumerate(result.results, 1):
            print(f'\n=== Sentencia {number} ===')
            if output.columns:
                print(' | '.join(output.columns))
                for row in output.rows:
                    print(' | '.join(display(value) for value in row))
            print(output.message)
            if args.plan:
                for access in output.plan:
                    print(f"Plan: {access['table']} ({access['alias']}) - {access['access']} "
                          f"{', '.join(access['indexes'])}; filas leídas {access['rows_read']}/{access['total_rows']}")
        if args.analizar and result.ok:
            print('Análisis correcto. No se ejecutaron las sentencias.')
    return 0 if result.ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
