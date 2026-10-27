"""
lalr_table.py - Construcción de tabla LALR(1)

LALR fusiona estados LR(1) que tienen el mismo NÚCLEO (core),
combinando sus lookaheads. Más poderoso que SLR, menos que LR(1).
"""

try:
    from .grammar import Grammar, LRItem, Production
    from .first_follow import compute_first, compute_follow, compute_first_of_string
    from .slr1_table import SLRTable
except ImportError:
    from grammar import Grammar, LRItem, Production
    from first_follow import compute_first, compute_follow, compute_first_of_string
    from slr1_table import SLRTable


class LR1Automaton:
    """Autómata LR(1) con items [A -> α • β, a] donde a es el lookahead."""

    def __init__(self, grammar: Grammar, first: dict):
        self.grammar = grammar
        self.first = first
        self.states = []
        self.transitions = {}
        self.state_index = {}

        if not grammar.augmented_start:
            grammar.augment()

        self._build()

    def closure1(self, items: frozenset) -> frozenset:
        """
        CLOSURE para items LR(1):
        Si [A -> α • B β, a] ∈ I, para cada producción B -> γ
        y para cada b ∈ FIRST(βa), agregar [B -> • γ, b]
        """
        closure_set = set(items)
        changed = True

        while changed:
            changed = False
            new_items = set()
            for item in list(closure_set):
                dot_sym = item.dot_symbol
                if dot_sym and dot_sym in self.grammar.non_terminals:
                    # β es lo que viene después del punto, excluyendo dot_sym
                    body = item.production.body
                    beta_start = item.dot_pos + 1
                    beta = body[beta_start:] if beta_start < len(body) else []

                    for lookahead in item.lookahead:
                        # FIRST(β a) donde a es el lookahead actual
                        sequence = beta + [lookahead]
                        first_beta_a = compute_first_of_string(sequence, self.first)

                        for prod in self.grammar.get_productions_for(dot_sym):
                            for b in first_beta_a:
                                if b == 'ε':
                                    continue
                                new_item = LRItem(prod, 0, frozenset({b}))
                                # Buscar si ya existe el item con mismo núcleo
                                existing = next(
                                    (x for x in closure_set
                                     if x.production == prod and x.dot_pos == 0),
                                    None
                                )
                                if existing:
                                    if b not in existing.lookahead:
                                        closure_set.discard(existing)
                                        merged = LRItem(prod, 0,
                                            frozenset(existing.lookahead | {b}))
                                        closure_set.add(merged)
                                        changed = True
                                else:
                                    candidate = next(
                                        (x for x in new_items
                                         if x.production == prod and x.dot_pos == 0),
                                        None
                                    )
                                    if candidate:
                                        new_items.discard(candidate)
                                        new_items.add(LRItem(prod, 0,
                                            frozenset(candidate.lookahead | {b})))
                                    else:
                                        new_items.add(new_item)
                                    changed = True

            closure_set.update(new_items)

        return frozenset(closure_set)

    def goto1(self, state: frozenset, symbol: str) -> frozenset:
        moved = set()
        for item in state:
            if item.dot_symbol == symbol:
                new_la = item.lookahead if item.lookahead else frozenset()
                moved.add(LRItem(item.production, item.dot_pos + 1, new_la))
        if not moved:
            return frozenset()
        return self.closure1(frozenset(moved))

    def _build(self):
        aug_prod = self.grammar.productions[0]
        initial_item = LRItem(aug_prod, 0, frozenset({'$'}))
        initial_state = self.closure1(frozenset({initial_item}))

        self.states = [initial_state]
        self.state_index[initial_state] = 0
        queue = [initial_state]

        while queue:
            state = queue.pop(0)
            state_idx = self.state_index[state]

            symbols = {item.dot_symbol for item in state if item.dot_symbol}

            for sym in symbols:
                next_state = self.goto1(state, sym)
                if not next_state:
                    continue
                if next_state not in self.state_index:
                    new_idx = len(self.states)
                    self.states.append(next_state)
                    self.state_index[next_state] = new_idx
                    queue.append(next_state)
                self.transitions[(state_idx, sym)] = self.state_index[next_state]

    def _item_core(self, item: LRItem):
        """Núcleo de un item: (producción, posición del punto)."""
        return (item.production, item.dot_pos)

    def state_core(self, state: frozenset):
        """Núcleo de un estado: conjunto de cores de sus items."""
        return frozenset(self._item_core(item) for item in state)


class LALRTable(SLRTable):
    """Tabla LALR(1): usa items LR(1) fusionados por núcleo."""

    def build_lalr_full(self, first: dict):
        """
        Construcción completa LALR(1):
        1. Construir autómata LR(1)
        2. Fusionar estados con el mismo núcleo (combinando lookaheads)
        3. Construir tabla ACTION/GOTO desde los estados fusionados
        """
        self.action = {}
        self.goto_table = {}
        self.conflicts = []

        lr1 = LR1Automaton(self.grammar, first)

        core_to_states = {}
        for state in lr1.states:
            core = lr1.state_core(state)
            if core not in core_to_states:
                core_to_states[core] = []
            core_to_states[core].append(state)

        merged_states = []
        state_map = {}  # LR(1) state -> merged state index

        for core, group in core_to_states.items():
            merged_items = {}
            for state in group:
                for item in state:
                    key = (item.production, item.dot_pos)
                    if key in merged_items:
                        merged_items[key] = frozenset(
                            merged_items[key] | item.lookahead
                        )
                    else:
                        merged_items[key] = item.lookahead

            merged = frozenset(
                LRItem(prod, dp, la)
                for (prod, dp), la in merged_items.items()
            )
            merged_idx = len(merged_states)
            merged_states.append(merged)

            for state in group:
                state_map[lr1.state_index[state]] = merged_idx

        merged_transitions = {}
        for (from_lr1, sym), to_lr1 in lr1.transitions.items():
            from_lalr = state_map[from_lr1]
            to_lalr = state_map[to_lr1]
            merged_transitions[(from_lalr, sym)] = to_lalr

        aug_start = self.grammar.augmented_start
        prods = self.grammar.productions

        for state_idx, state in enumerate(merged_states):
            for item in state:
                dot_sym = item.dot_symbol
                head = item.production.head

                if dot_sym is not None:
                    # SHIFT
                    if dot_sym in self.grammar.terminals:
                        next_s = merged_transitions.get((state_idx, dot_sym))
                        if next_s is not None:
                            self._set_action(state_idx, dot_sym, (self.SHIFT, next_s))
                    # GOTO
                    elif dot_sym in self.grammar.non_terminals:
                        next_s = merged_transitions.get((state_idx, dot_sym))
                        if next_s is not None:
                            self.goto_table[(state_idx, dot_sym)] = next_s
                else:
                    # Item completo
                    prod_idx = prods.index(item.production)
                    if head == aug_start:
                        self._set_action(state_idx, '$', (self.ACCEPT, None))
                    else:
                        # REDUCE con lookahead LR(1)
                        for la in item.lookahead:
                            self._set_action(state_idx, la, (self.REDUCE, prod_idx))

        self.states = merged_states
        self.merged_transitions = merged_transitions
        return self


