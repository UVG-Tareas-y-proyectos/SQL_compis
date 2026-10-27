"""
ll1_table.py - Construcción de tabla LL(1) y parser predictivo

La tabla M[A, a] indica qué producción usar cuando:
  - A es el no terminal en la cima de la pila
  - a es el siguiente token de entrada
"""

try:
    from .grammar import Grammar
    from .first_follow import compute_first, compute_follow, compute_first_of_string
except ImportError:
    from grammar import Grammar
    from first_follow import compute_first, compute_follow, compute_first_of_string


class LL1Table:
    def __init__(self, grammar: Grammar):
        self.grammar = grammar
        self.table = {}         # dict[(non_terminal, terminal)] -> Production
        self.conflicts = []
        self.first = {}
        self.follow = {}

    def build(self, first: dict, follow: dict):
        """
        Construye la tabla LL(1).
        
        Regla: Para cada producción A -> α:
          1. Para cada terminal a ∈ FIRST(α): M[A, a] = A -> α
          2. Si ε ∈ FIRST(α): para cada b ∈ FOLLOW(A): M[A, b] = A -> α
          3. Si ε ∈ FIRST(α) y $ ∈ FOLLOW(A): M[A, $] = A -> α
        """
        self.first = first
        self.follow = follow
        self.table = {}
        self.conflicts = []

        for prod in self.grammar.productions:
            head = prod.head
            body = prod.body

            # Calcular FIRST del cuerpo de la producción
            body_first = compute_first_of_string(body, first)

            # Regla 1 y 2
            for terminal in body_first:
                if terminal != 'ε':
                    self._set(head, terminal, prod)

            # Si ε ∈ FIRST(body), usar FOLLOW
            if 'ε' in body_first:
                for terminal in follow.get(head, set()):
                    self._set(head, terminal, prod)

    def _set(self, nt, t, prod):
        key = (nt, t)
        if key in self.table:
            if self.table[key] != prod:
                self.conflicts.append({
                    'non_terminal': nt,
                    'terminal': t,
                    'existing': self.table[key],
                    'new': prod
                })
        else:
            self.table[key] = prod

    def get(self, non_terminal, terminal):
        """Retorna la producción para M[A, a], o None si no existe."""
        return self.table.get((non_terminal, terminal), None)

    def is_ll1(self):
        """Una gramática es LL(1) si no tiene conflictos en su tabla."""
        return len(self.conflicts) == 0

    def parse(self, tokens: list):
        """
        Ejecuta el parser predictivo no recursivo (basado en pila).
        tokens: lista de terminales, debe terminar con '$'
        Retorna: (pasos, aceptado)
        """
        if tokens[-1] != '$':
            tokens = tokens + ['$']

        stack = ['$', self.grammar.start_symbol]
        pos = 0
        steps = []
        MAX_STEPS = 5000  # límite de seguridad contra loops infinitos (recursión izquierda)

        while stack:
            if len(steps) > MAX_STEPS:
                steps.append({'stack': list(reversed(stack)), 'input': tokens[pos:],
                               'action': 'error: demasiados pasos (posible recursión izquierda)'})
                return steps, False
            top = stack[-1]
            current = tokens[pos]

            step = {
                'stack': list(reversed(stack)),
                'input': tokens[pos:],
                'action': None
            }

            if top == '$':
                if current == '$':
                    step['action'] = 'accept'
                    steps.append(step)
                    return steps, True
                else:
                    step['action'] = f"error: pila vacía pero quedan tokens"
                    steps.append(step)
                    return steps, False

            elif top in self.grammar.terminals or top == '$':
                # Terminal en la cima: debe coincidir con el input
                if top == current:
                    step['action'] = f"match '{top}'"
                    stack.pop()
                    pos += 1
                else:
                    step['action'] = f"error: esperaba '{top}', encontró '{current}'"
                    steps.append(step)
                    return steps, False

            elif top in self.grammar.non_terminals:
                # No terminal: consultar tabla
                prod = self.get(top, current)
                if prod is None:
                    step['action'] = f"error: M[{top}, {current}] vacío"
                    steps.append(step)
                    return steps, False

                step['action'] = f"usar {prod}"
                stack.pop()

                # Apilar el cuerpo de la producción en reversa
                if prod.body != ['ε']:
                    for sym in reversed(prod.body):
                        stack.append(sym)
            else:
                step['action'] = f"error: símbolo desconocido '{top}'"
                steps.append(step)
                return steps, False

            steps.append(step)

        return steps, False

    def print_table(self):
        """Imprime la tabla LL(1)."""
        terminals = sorted(self.grammar.terminals | {'$'})
        non_terms = sorted(nt for nt in self.grammar.non_terminals
                           if nt != self.grammar.augmented_start)

        col_w = 20
        header = f"{'':>15} | " + " | ".join(f"{t[:col_w]:>{col_w}}" for t in terminals)
        print("=== TABLA LL(1) ===")
        print(header)
        print('-' * len(header))

        for nt in non_terms:
            row = f"{nt:>15} | "
            cells = []
            for t in terminals:
                prod = self.table.get((nt, t))
                if prod:
                    cell = ' '.join(
                        "epsilon" if sym == 'ε' else sym for sym in prod.body
                    ) if prod.body != ['ε'] else 'epsilon'
                    cell = f"{nt}->{cell}"[:col_w]
                    cells.append(f"{cell:>{col_w}}")
                else:
                    cells.append(f"{'':>{col_w}}")
            print(row + " | ".join(cells))

        if self.conflicts:
            print(f"\n! Gramatica NO es LL(1): {len(self.conflicts)} conflicto(s)")
            for c in self.conflicts:
                print(f"  M[{c['non_terminal']}, {c['terminal']}]:")
                print(f"    Existente: {c['existing']}")
                print(f"    Nuevo:     {c['new']}")
        else:
            print("\nGramatica es LL(1)")

    def print_parse_steps(self, steps, accepted):
        """Imprime la traza del parsing paso a paso."""
        print(f"\n{'Pila':30} {'Entrada':25} {'Acción':30}")
        print('-' * 90)
        for step in steps:
            stack_str = ' '.join(str(s) for s in step['stack'])
            input_str = ' '.join(step['input'])
            action_str = str(step.get('action', ''))
            print(f"{stack_str:30} {input_str:25} {action_str:30}")
        print(f"\nResultado: {'ACEPTADO' if accepted else 'RECHAZADO'}")


