"""Lexer DFA y parser SLR generados por YALex/YAPar del proyecto anterior."""

from contextlib import redirect_stdout
from dataclasses import dataclass, field
import hashlib
import importlib.util
import io
from pathlib import Path
import pickle
import re
import sys

from .model import Diagnostic, SyntaxNode

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src' / 'shared'))
from tok import Token
from yalex.yalex_gen import YALexEngine
from yapar.first_follow import compute_first, compute_follow
from yapar.lr0_automaton import LR0Automaton
from yapar.slr1_table import SLRTable
from yapar.yapar_parser import YAParParser

KEYWORDS = {w: w for w in '''CREATE TABLE DROP INDEX ON INSERT INTO VALUES UPDATE SET
DELETE SELECT DISTINCT FROM WHERE AND OR NOT ORDER BY ASC DESC INNER JOIN COUNT SUM
AVG MIN MAX GROUP HAVING IN EXISTS AS IS NULL TRUE FALSE INT FLOAT VARCHAR BOOLEAN
DATE PRIMARY KEY UNIQUE DEFAULT'''.split()}
KEYWORDS.update(INTEGER='INT', REAL='FLOAT', BOOL='BOOLEAN')


@dataclass
class Parsed:
    tokens: list = field(default_factory=list)
    tree: object = None
    ast: object = None
    diagnostics: list = field(default_factory=list)

    @property
    def ok(self):
        return not self.diagnostics


class SQLFrontend:
    def __init__(self, generated=None):
        self.generated = Path(generated or ROOT / 'generated')
        self.generated.mkdir(parents=True, exist_ok=True)
        yal, yalp = ROOT / 'grammar' / 'SQL.yal', ROOT / 'grammar' / 'SQL.yalp'
        generator_sources = sorted((ROOT / 'src' / 'yalex').glob('*.py')) + sorted((ROOT / 'src' / 'yapar').glob('*.py'))
        fingerprint = hashlib.sha256(yal.read_bytes()+yalp.read_bytes()+
                                     b''.join(p.read_bytes() for p in generator_sources)).hexdigest()
        stamp = self.generated / 'sql.sha256'
        lexer_path = self.generated / 'sql_lexer.py'
        cache = self.generated / 'sql_slr.pkl'
        if not (stamp.exists() and stamp.read_text() == fingerprint and lexer_path.exists() and cache.exists()):
            with redirect_stdout(io.StringIO()):
                YALexEngine().compile(str(yal), str(lexer_path))
                grammar = YAParParser().parse_file(str(yalp))
                first = compute_first(grammar)
                follow = compute_follow(grammar, first)
                automaton = LR0Automaton(grammar)
                table = SLRTable(grammar)
                table.build_slr(automaton, first, follow)
            if table.conflicts:
                raise RuntimeError(f'La gramática SQL tiene conflictos SLR: {table.conflicts[:3]}')
            cache.write_bytes(pickle.dumps((grammar, table)))
            stamp.write_text(fingerprint)
        self.grammar, self.table = pickle.loads(cache.read_bytes())
        spec = importlib.util.spec_from_file_location('sql_generated_lexer', lexer_path)
        self.lexer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.lexer)

    def parse(self, source):
        result = Parsed()
        try:
            for token in self.lexer.tokenize(source):
                if token.type == '$':
                    continue
                if token.type == 'ID' and not token.value.startswith('"'):
                    token.type = KEYWORDS.get(token.value.upper(), 'ID')
                result.tokens.append(token)
        except SyntaxError as exc:
            match = re.search(r'linea (\d+) col (\d+)', str(exc))
            line, col = map(int, match.groups()) if match else (1, 1)
            result.diagnostics.append(Diagnostic('léxico', str(exc), line, col))
            return result
        tokens = list(result.tokens)
        if tokens and tokens[-1].type != 'SEMI':
            last = tokens[-1]
            tokens.append(Token('SEMI', ';', last.line, last.col+len(last.value)))
        states, values, position = [0], [], 0
        while True:
            look = tokens[position].type if position < len(tokens) else '$'
            action, value = self.table.get_action(states[-1], look)
            if action == self.table.SHIFT:
                states.append(value)
                values.append(tokens[position])
                position += 1
            elif action == self.table.REDUCE:
                production = self.grammar.productions[value]
                count = 0 if production.body == ['ε'] else len(production.body)
                children = values[-count:] if count else []
                if count:
                    del values[-count:]
                    del states[-count:]
                located = children[0] if children else (tokens[position] if position < len(tokens) else None)
                node = SyntaxNode(production.head, children, getattr(located, 'line', 1),
                                  getattr(located, 'column', 1))
                states.append(self.table.get_goto(states[-1], production.head))
                values.append(node)
            elif action == self.table.ACCEPT:
                result.tree = values[-1]
                return result
            else:
                token = tokens[position] if position < len(tokens) else (tokens[-1] if tokens else Token('', '', 1, 1))
                expected = sorted(t for (s, t) in self.table.action if s == states[-1])
                result.diagnostics.append(Diagnostic('sintáctico',
                    f'entrada inesperada {token.value!r}; se esperaba: {", ".join(expected)}', token.line, token.col))
                return result
