"""
slr1_table.py - Construcción de tablas SLR(1) y LALR

La tabla tiene dos secciones:
  - ACTION[state, terminal]  -> shift s | reduce r | accept | error
  - GOTO[state, non_terminal] -> state_number
"""

try:
    from .grammar import Grammar, LRItem
    from .lr0_automaton import LR0Automaton
    from .first_follow import compute_first, compute_follow
except ImportError:
    from grammar import Grammar, LRItem
    from lr0_automaton import LR0Automaton
    from first_follow import compute_first, compute_follow


class SLRTable:
    # Tipos de acción
    SHIFT  = 'shift'
    REDUCE = 'reduce'
    ACCEPT = 'accept'
    ERROR  = 'error'

    def __init__(self, grammar: Grammar):
        self.grammar = grammar
        self.conflicts = []     # lista de conflictos detectados
        self.action = {}        # dict[(state, terminal)] -> (type, value)
        self.goto_table = {}    # dict[(state, non_terminal)] -> state

    def build_slr(self, automaton: LR0Automaton, first: dict, follow: dict):
        """
        Construye la tabla SLR(1).
        SLR usa FOLLOW(A) para decidir cuándo reducir.
        """
        self.action = {}
        self.goto_table = {}
        self.conflicts = []

        aug_start = self.grammar.augmented_start    # S'
        prods = self.grammar.productions

        for state_idx, state in enumerate(automaton.states):
            for item in state:
                dot_sym = item.dot_symbol
                head = item.production.head

                if dot_sym is not None:
                    if dot_sym in self.grammar.terminals:
                        next_state = automaton.transitions.get((state_idx, dot_sym))
                        if next_state is not None:
                            self._set_action(state_idx, dot_sym,
                                             (self.SHIFT, next_state))

                    elif dot_sym in self.grammar.non_terminals:
                        next_state = automaton.transitions.get((state_idx, dot_sym))
                        if next_state is not None:
                            self.goto_table[(state_idx, dot_sym)] = next_state

                else:
                    # El punto está al final del item (item completo)
                    prod_idx = prods.index(item.production)

                    if head == aug_start:
                        self._set_action(state_idx, '$', (self.ACCEPT, None))

                    else:
                        # SLR: reducir para cada terminal en FOLLOW(head)
                        for terminal in follow.get(head, set()):
                            self._set_action(state_idx, terminal,
                                             (self.REDUCE, prod_idx))

    def build_lalr(self, first: dict, follow: dict):
        """Construye la tabla LALR(1) usando la implementación LR(1) fusionada."""
        try:
            from .lalr_table import LALRTable
        except ImportError:
            from lalr_table import LALRTable

        table = LALRTable(self.grammar).build_lalr_full(first)
        self.action = table.action
        self.goto_table = table.goto_table
        self.conflicts = table.conflicts
        self.states = table.states
        self.merged_transitions = table.merged_transitions
        return self

    def _set_action(self, state, terminal, action):
        """Asigna acción a la tabla. Detecta conflictos."""
        key = (state, terminal)
        if key in self.action:
            existing = self.action[key]
            if existing != action:
                conflict_type = self._conflict_type(existing[0], action[0])
                self.conflicts.append({
                    'state': state,
                    'terminal': terminal,
                    'existing': existing,
                    'new': action,
                    'type': conflict_type
                })
                # Convención: en conflicto shift/reduce, preferir shift
                if conflict_type == 'shift/reduce' and action[0] == self.SHIFT:
                    self.action[key] = action
                return
        self.action[key] = action

    def _conflict_type(self, a, b):
        types = {a, b}
        if self.SHIFT in types and self.REDUCE in types:
            return 'shift/reduce'
        if types == {self.REDUCE}:
            return 'reduce/reduce'
        return 'unknown'

    def get_action(self, state, terminal):
        return self.action.get((state, terminal), (self.ERROR, None))

    def get_goto(self, state, non_terminal):
        return self.goto_table.get((state, non_terminal), None)

    def parse(self, tokens: list):
        """
        Ejecuta el algoritmo de parsing shift-reduce.
        tokens: lista de terminales (strings), debe terminar con '$'
        Retorna: list de pasos (stack, input, action)
        """
        if tokens[-1] != '$':
            tokens = tokens + ['$']

        stack = [0]           # pila de estados
        sym_stack = ['$']     # pila de símbolos (para visualización)
        pos = 0
        steps = []

        while True:
            state = stack[-1]
            lookahead = tokens[pos]
            action_type, action_val = self.get_action(state, lookahead)

            step = {
                'stack': list(stack),
                'symbols': list(sym_stack),
                'input': tokens[pos:],
                'action': (action_type, action_val)
            }
            steps.append(step)

            if action_type == self.SHIFT:
                stack.append(action_val)
                sym_stack.append(lookahead)
                pos += 1

            elif action_type == self.REDUCE:
                prod = self.grammar.productions[action_val]
                # Hacer pop según |cuerpo de la producción|
                pop_count = 0 if prod.body == ['ε'] else len(prod.body)
                for _ in range(pop_count):
                    stack.pop()
                    sym_stack.pop()
                # Ir al estado indicado por GOTO
                top_state = stack[-1]
                goto_state = self.get_goto(top_state, prod.head)
                if goto_state is None:
                    steps.append({'error': f"GOTO({top_state}, {prod.head}) indefinido"})
                    return steps, False
                stack.append(goto_state)
                sym_stack.append(prod.head)

            elif action_type == self.ACCEPT:
                step['action'] = (self.ACCEPT, None)
                return steps, True

            else:
                steps.append({'error': f"Error sintáctico en estado {state} con '{lookahead}'"})
                return steps, False

    def print_table(self):
        """Imprime la tabla ACTION/GOTO."""
        terminals = sorted(self.grammar.terminals | {'$'})
        non_terms = sorted(self.grammar.non_terminals - {self.grammar.augmented_start or ''})
        n_states = len(set(s for s, _ in self.action) | set(s for s, _ in self.goto_table))
        max_state = max((s for s, _ in list(self.action.keys()) + list(self.goto_table.keys())),
                        default=0)

        print("=== ACTION ===")
        header = f"{'Estado':>6} | " + " | ".join(f"{t:>6}" for t in terminals)
        print(header)
        print('-' * len(header))

        for s in range(max_state + 1):
            row = f"{s:>6} | "
            cells = []
            for t in terminals:
                act = self.action.get((s, t))
                if act is None:
                    cells.append(f"{'':>6}")
                elif act[0] == self.SHIFT:
                    cells.append(f"{'s'+str(act[1]):>6}")
                elif act[0] == self.REDUCE:
                    cells.append(f"{'r'+str(act[1]):>6}")
                elif act[0] == self.ACCEPT:
                    cells.append(f"{'acc':>6}")
                else:
                    cells.append(f"{'err':>6}")
            print(row + " | ".join(cells))

        print("\n=== GOTO ===")
        header2 = f"{'Estado':>6} | " + " | ".join(f"{nt:>10}" for nt in non_terms)
        print(header2)
        print('-' * len(header2))
        for s in range(max_state + 1):
            row = f"{s:>6} | "
            cells = [f"{str(self.goto_table.get((s, nt), '')):>10}" for nt in non_terms]
            print(row + " | ".join(cells))

        if self.conflicts:
            print(f"\n! {len(self.conflicts)} conflicto(s) detectado(s):")
            for c in self.conflicts:
                print(f"  Estado {c['state']}, terminal '{c['terminal']}': {c['type']}")


