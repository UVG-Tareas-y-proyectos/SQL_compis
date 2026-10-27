"""
nfa.py - Autómata Finito No Determinista (NFA)

Implementa la construcción de Thompson:
  AST de regex -> NFA con epsilon-transiciones
"""

from collections import defaultdict

try:
    from .regex_parser import RegexParser
except ImportError:
    from regex_parser import RegexParser

# ASCII imprimible + espacios en blanco + caracteres del espanol, para que
# las clases negadas ([^"] en strings, [^\n] en comentarios) los acepten.
DEFAULT_ALPHABET = ({chr(c) for c in range(32, 127)} | {'\n', '\t', '\r'}
                    | set('áéíóúÁÉÍÓÚñÑüÜ¿¡'))


class NFAState:
    """Estado del NFA. Cada estado tiene un id único."""
    _counter = 0

    def __init__(self):
        self.id    = NFAState._counter
        NFAState._counter += 1
        self.eps   = []                     # transiciones epsilon
        self.trans = defaultdict(list)      # símbolo -> [NFAState]

    @classmethod
    def reset(cls):
        cls._counter = 0

    def __repr__(self):
        return f"S{self.id}"


class NFA:
    """NFA con un único estado inicial y uno de aceptación."""

    def __init__(self, start: NFAState, accept: NFAState):
        self.start  = start
        self.accept = accept


class NFABuilder:
    """
    Construcción de Thompson: convierte un AST de regex en NFA.
    Cada operación crea exactamente 2 estados nuevos.
    """

    def build(self, ast) -> NFA:
        t = ast[0]

        if t == 'char':
            s, a = NFAState(), NFAState()
            s.trans[ast[1]].append(a)
            return NFA(s, a)

        if t == 'str':
            states = []
            for ch in ast[1]:
                s, a = NFAState(), NFAState()
                s.trans[ch].append(a)
                states.append((s, a))
            for i in range(len(states) - 1):
                states[i][1].eps.append(states[i + 1][0])
            return NFA(states[0][0], states[-1][1])

        if t == 'dot':
            s, a = NFAState(), NFAState()
            s.trans[None].append(a)         # None = cualquier carácter
            return NFA(s, a)

        if t == 'class':
            neg, items = ast[1]
            s, a = NFAState(), NFAState()
            s.trans[('class', neg, frozenset(items))].append(a)
            return NFA(s, a)

        if t == 'diff':
            left = self._char_set(ast[1])
            right = self._char_set(ast[2])
            if left is None or right is None:
                raise ValueError("El operador # solo se soporta entre simbolos o conjuntos")
            s, a = NFAState(), NFAState()
            s.trans[('class', False, frozenset(left - right))].append(a)
            return NFA(s, a)

        if t == 'epsilon':
            s, a = NFAState(), NFAState()
            s.eps.append(a)
            return NFA(s, a)

        if t == 'star':
            inner = self.build(ast[1])
            s, a  = NFAState(), NFAState()
            s.eps.extend([inner.start, a])
            inner.accept.eps.extend([inner.start, a])
            return NFA(s, a)

        if t == 'plus':
            inner = self.build(ast[1])
            s, a  = NFAState(), NFAState()
            s.eps.append(inner.start)
            inner.accept.eps.extend([inner.start, a])
            return NFA(s, a)

        if t == 'opt':
            inner = self.build(ast[1])
            s, a  = NFAState(), NFAState()
            s.eps.extend([inner.start, a])
            inner.accept.eps.append(a)
            return NFA(s, a)

        if t == 'concat':
            nfas = [self.build(n) for n in ast[1]]
            for i in range(len(nfas) - 1):
                nfas[i].accept.eps.append(nfas[i + 1].start)
            return NFA(nfas[0].start, nfas[-1].accept)

        if t == 'alt':
            s, a = NFAState(), NFAState()
            for part in ast[1]:
                nfa = self.build(part)
                s.eps.append(nfa.start)
                nfa.accept.eps.append(a)
            return NFA(s, a)

        # Fallback: epsilon
        s, a = NFAState(), NFAState()
        s.eps.append(a)
        return NFA(s, a)

    def _char_set(self, ast):
        kind = ast[0]
        if kind == 'char' and len(ast[1]) == 1:
            return {ast[1]}
        if kind == 'str':
            return set(ast[1])
        if kind == 'dot':
            return set(DEFAULT_ALPHABET)
        if kind == 'class':
            neg, items = ast[1]
            return set(DEFAULT_ALPHABET - set(items)) if neg else set(items)
        return None

    def build_combined(self, alternatives: list, lets: dict = None):
        """
        Combina múltiples reglas en un único NFA.
        El orden determina prioridad (primera regla que coincide gana).
        Retorna (nfa_start, accept_map) donde accept_map mapea
        estado de aceptación -> índice de la regla.
        """
        NFAState.reset()
        start      = NFAState()
        accept_map = {}

        for idx, (regexp, _action) in enumerate(alternatives):
            ast = RegexParser(regexp, lets).parse()
            nfa = self.build(ast)
            start.eps.append(nfa.start)
            accept_map[nfa.accept] = idx

        return start, accept_map
