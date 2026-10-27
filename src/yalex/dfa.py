"""
dfa.py - Construcción de DFA por Subconjuntos

Convierte un NFA (con epsilon-transiciones) en un DFA
usando la construcción de subconjuntos (algoritmo de Rabin-Scott).
"""

from collections import deque

try:
    from .nfa import NFAState
except ImportError:
    from nfa import NFAState


class DFABuilder:
    """
    Construcción de subconjuntos: NFA -> DFA.

    Cada estado del DFA corresponde a un conjunto de estados del NFA.
    El DFA resultante se representa como tablas de transición.
    """

    def epsilon_closure(self, states: set) -> frozenset:
        """
        Cierre epsilon de un conjunto de estados NFA.
        Incluye todos los estados alcanzables solo por transiciones ε.
        """
        stack  = list(states)
        result = set(states)
        while stack:
            st = stack.pop()
            for nx in st.eps:
                if nx not in result:
                    result.add(nx)
                    stack.append(nx)
        return frozenset(result)

    def _matches(self, key, char: str) -> bool:
        """Verifica si una clave de transición NFA coincide con el carácter."""
        if key is None:                             # punto (cualquier carácter)
            return True
        if isinstance(key, tuple) and key[0] == 'class':
            in_set = char in set(key[2])
            return not in_set if key[1] else in_set # key[1] = negado
        return key == char

    def _build_alphabet(self, nfa_start: NFAState) -> list:
        """
        Recolecta todos los caracteres relevantes del NFA.
        Si hay clases negadas o comodines, expande el alfabeto ASCII.
        """
        visited  = set()
        stack    = [nfa_start]
        chars    = set()
        has_wild = False

        while stack:
            st = stack.pop()
            if st in visited:
                continue
            visited.add(st)
            for k, vlist in st.trans.items():
                if k is None:
                    has_wild = True
                elif isinstance(k, tuple) and k[0] == 'class':
                    chars.update(k[2])
                    if k[1]:
                        has_wild = True
                else:
                    chars.add(k)
                for v in vlist:
                    stack.append(v)
            for e in st.eps:
                stack.append(e)

        if has_wild:
            try:
                from .nfa import DEFAULT_ALPHABET
            except ImportError:
                from nfa import DEFAULT_ALPHABET
            chars.update(DEFAULT_ALPHABET)

        return sorted(chars)

    def build(self, nfa_start: NFAState, accept_map: dict) -> dict:
        """
        Ejecuta la construcción de subconjuntos.

        Retorna un diccionario con:
          trans      - tabla de transición {estado: {char: estado}}
          accepting  - estados de aceptación {estado: [índice_regla]}
          start      - estado inicial (siempre 0)
          num_states - número total de estados DFA
        """
        alphabet      = self._build_alphabet(nfa_start)
        start_closure = self.epsilon_closure({nfa_start})

        dstate_map = {start_closure: 0}
        dstates    = [start_closure]
        trans      = {}
        accepting  = {}
        queue      = deque([start_closure])

        while queue:
            S   = queue.popleft()
            sid = dstate_map[S]
            trans[sid] = {}

            # Verificar si algún estado NFA del conjunto es de aceptación
            rules = {accept_map[n] for n in S if n in accept_map}
            if rules:
                accepting[sid] = sorted(rules)  # orden = prioridad

            for ch in alphabet:
                # Calcular move(S, ch)
                T = set()
                for n in S:
                    for k, vlist in n.trans.items():
                        if self._matches(k, ch):
                            T.update(vlist)
                if not T:
                    continue

                T_closure = self.epsilon_closure(T)
                if T_closure not in dstate_map:
                    dstate_map[T_closure] = len(dstates)
                    dstates.append(T_closure)
                    queue.append(T_closure)

                trans[sid][ch] = dstate_map[T_closure]

        return {
            'trans':      trans,
            'accepting':  accepting,
            'start':      0,
            'num_states': len(dstates)
        }
