"""
Genera un parser Python independiente a partir de una gramatica YAPar.

El archivo generado contiene las tablas de parseo y usa el lexer Python generado
desde el archivo YALex indicado por la CLI.
"""

from pathlib import Path


class ParserGenerator:
    def generate_lr(self, grammar, table, lexer_module_name, out_path, method_name):
        productions = [(p.head, list(p.body)) for p in grammar.productions]
        source = self._render_lr(
            method_name=method_name,
            lexer_module_name=lexer_module_name,
            productions=productions,
            terminals=sorted(grammar.terminals),
            ignored=sorted(grammar.ignored_tokens),
            action=table.action,
            goto_table=table.goto_table,
            conflicts=table.conflicts,
        )
        Path(out_path).write_text(source, encoding="utf-8")

    def _render_lr(self, method_name, lexer_module_name, productions, terminals,
                   ignored, action, goto_table, conflicts):
        return f'''# Parser generado por YAPar.
# Metodo: {method_name}

import importlib
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
for candidate in (
    BASE,
    BASE / "shared",
    BASE.parent / "src",
    BASE.parent / "src" / "shared",
):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

LEXER_MODULE = {lexer_module_name!r}
PRODUCTIONS = {productions!r}
TERMINALS = set({terminals!r})
IGNORED = set({ignored!r})
ACTION = {action!r}
GOTO = {goto_table!r}
CONFLICTS = {conflicts!r}


class GeneratedParser:
    SHIFT = "shift"
    REDUCE = "reduce"
    ACCEPT = "accept"
    ERROR = "error"

    def __init__(self, lexer_module=None):
        self.lexer = lexer_module or importlib.import_module(LEXER_MODULE)

    def tokenize_types(self, text):
        tokens = self.lexer.tokenize(text)
        return [tok.type for tok in tokens if tok.type not in IGNORED and tok.type != "$"]

    def tokenize(self, text):
        return [tok for tok in self.lexer.tokenize(text) if tok.type not in IGNORED and tok.type != "$"]

    def parse_tokens(self, tokens):
        if not tokens or tokens[-1] != "$":
            tokens = list(tokens) + ["$"]

        stack = [0]
        symbols = ["$"]
        pos = 0
        steps = []

        while True:
            state = stack[-1]
            lookahead = tokens[pos]
            action_type, action_value = ACTION.get((state, lookahead), (self.ERROR, None))
            steps.append({{
                "stack": list(stack),
                "symbols": list(symbols),
                "input": tokens[pos:],
                "action": (action_type, action_value),
            }})

            if action_type == self.SHIFT:
                stack.append(action_value)
                symbols.append(lookahead)
                pos += 1
            elif action_type == self.REDUCE:
                head, body = PRODUCTIONS[action_value]
                pop_count = 0 if body == ["ε"] else len(body)
                for _ in range(pop_count):
                    stack.pop()
                    symbols.pop()
                goto_state = GOTO.get((stack[-1], head))
                if goto_state is None:
                    steps.append({{"error": f"GOTO({{stack[-1]}}, {{head}}) indefinido"}})
                    return steps, False
                stack.append(goto_state)
                symbols.append(head)
            elif action_type == self.ACCEPT:
                return steps, True
            else:
                steps.append({{"error": f"Error sintactico en estado {{state}} con {{lookahead!r}}"}})
                return steps, False

    def parse_text(self, text):
        return self.parse_tokens(self.tokenize_types(text))

    def error_location(self, steps, tokens):
        for step in reversed(steps):
            if "input" not in step or not step["input"]:
                continue
            consumed = len(tokens) + 1 - len(step["input"])
            if 0 <= consumed < len(tokens):
                tok = tokens[consumed]
                return f"linea {{tok.line}}, columna {{tok.col}}, token {{tok.type!r}}"
            return "fin de entrada"
        return "ubicacion no disponible"


def parse_text(text):
    return GeneratedParser().parse_text(text)


def main(argv=None):
    argv = argv or sys.argv[1:]
    if not argv:
        print("Uso: python " + Path(__file__).name + " <archivo_entrada>")
        return 2

    parser = GeneratedParser()
    exit_code = 0
    for path in argv:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        for number, line in enumerate(lines, 1):
            text = line.rstrip("\\n")
            if not text.strip():
                continue
            try:
                token_objects = parser.tokenize(text)
                tokens = [tok.type for tok in token_objects]
                steps, ok = parser.parse_tokens(tokens + ["$"])
            except Exception as exc:
                print(f"{{path}}:{{number}}: LEX ERROR: {{exc}}")
                exit_code = 1
                continue
            status = "ACEPTADA" if ok else "RECHAZADA"
            print(f"{{path}}:{{number}}: {{status}}  tokens={{tokens}}")
            if not ok:
                print(f"  Error cerca de {{parser.error_location(steps, token_objects)}}")
                exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
'''
