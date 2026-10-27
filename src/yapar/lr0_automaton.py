"""
lr0_automaton.py - Construcción del Autómata LR(0)

Implementa:
  - closure(I): cierra un conjunto de items LR(0)
  - goto(I, X): transición del autómata
  - canonical_collection(): colección canónica de conjuntos LR(0)
"""

try:
    from .grammar import Grammar, LRItem, Production
except ImportError:
    from grammar import Grammar, LRItem, Production


class LR0Automaton:
    def __init__(self, grammar: Grammar):
        self.grammar = grammar
        self.states = []          # list[frozenset[LRItem]]: cada estado = conjunto de items
        self.transitions = {}     # dict[(state_idx, symbol) -> state_idx]
        self.state_index = {}     # dict[frozenset -> int]: mapeo estado -> índice

        # Aumentar la gramática si aún no está aumentada
        if not grammar.augmented_start:
            grammar.augment()

        self._build()

    def closure(self, items: set) -> frozenset:
        """
        CLOSURE(I):
        Para cada item [A -> α • B β] en I,
        agrega [B -> • γ] para cada producción B -> γ.
        Repite hasta que no cambien.
        """
        closure_set = set(items)
        changed = True

        while changed:
            changed = False
            new_items = set()
            for item in closure_set:
                dot_sym = item.dot_symbol
                if dot_sym and dot_sym in self.grammar.non_terminals:
                    for prod in self.grammar.get_productions_for(dot_sym):
                        new_item = LRItem(prod, 0)
                        if new_item not in closure_set:
                            new_items.add(new_item)
                            changed = True
            closure_set.update(new_items)

        return frozenset(closure_set)

    def goto(self, state: frozenset, symbol: str) -> frozenset:
        """
        GOTO(I, X):
        Conjunto de items que resultan de avanzar el punto
        sobre el símbolo X en el estado I.
        """
        moved = set()
        for item in state:
            if item.dot_symbol == symbol:
                moved.add(item.advance())
        if not moved:
            return frozenset()
        return self.closure(moved)

    def _build(self):
        """Construye la colección canónica de conjuntos LR(0)."""
        # Estado inicial: closure del item inicial S' -> • S
        aug_prod = self.grammar.productions[0]  # S' -> S (primera después de augment)
        initial_item = LRItem(aug_prod, 0)
        initial_state = self.closure({initial_item})

        self.states = [initial_state]
        self.state_index[initial_state] = 0
        self.transitions = {}

        queue = [initial_state]

        while queue:
            state = queue.pop(0)
            state_idx = self.state_index[state]

            # Reunir todos los símbolos después del punto en este estado
            symbols = set()
            for item in state:
                if item.dot_symbol:
                    symbols.add(item.dot_symbol)

            for sym in symbols:
                next_state = self.goto(state, sym)
                if not next_state:
                    continue

                if next_state not in self.state_index:
                    new_idx = len(self.states)
                    self.states.append(next_state)
                    self.state_index[next_state] = new_idx
                    queue.append(next_state)

                next_idx = self.state_index[next_state]
                self.transitions[(state_idx, sym)] = next_idx

    def get_state_idx(self, state: frozenset) -> int:
        return self.state_index.get(state, -1)

    def print_automaton(self):
        """Imprime el autómata en formato legible."""
        print("=== AUTÓMATA LR(0) ===\n")
        for i, state in enumerate(self.states):
            print(f"Estado I{i}:")
            for item in sorted(state, key=str):
                print(f"  {item}")
            print()

        print("=== TRANSICIONES ===")
        for (from_state, symbol), to_state in sorted(self.transitions.items()):
            print(f"  goto(I{from_state}, {symbol}) = I{to_state}")

    def to_dict(self):
        """Serializa el autómata a dict (para GUI/visualización)."""
        states_data = []
        for i, state in enumerate(self.states):
            states_data.append({
                'id': i,
                'items': [str(item) for item in sorted(state, key=str)]
            })
        transitions_data = [
            {'from': f, 'symbol': s, 'to': t}
            for (f, s), t in self.transitions.items()
        ]
        return {'states': states_data, 'transitions': transitions_data}


