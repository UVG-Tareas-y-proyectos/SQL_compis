"""
first_follow.py - Cálculo de conjuntos FIRST y FOLLOW

Basado en la teoría vista en clase (7/04/2026):
  - FIRST(X): terminales con los que puede comenzar X
  - FOLLOW(A): terminales que pueden seguir a A en alguna forma sentencial
"""

try:
    from .grammar import Grammar
except ImportError:
    from grammar import Grammar


def compute_first(grammar: Grammar) -> dict:
    """
    Calcula FIRST(X) para todos los símbolos de la gramática.
    
    Reglas:
      1. Si X es terminal: FIRST(X) = {X}
      2. Si X -> ε existe: ε ∈ FIRST(X)
      3. Si X -> Y1 Y2 ... Yk:
           - Todo FIRST(Y1) sin {ε} ∈ FIRST(X)
           - Si epsilon en FIRST(Y1), también FIRST(Y2) sin epsilon en FIRST(X)
           - ... y así sucesivamente
    """
    first = {}

    # Inicializar: FIRST de terminales es el mismo terminal
    for t in grammar.terminals:
        first[t] = {t}
    first['$'] = {'$'}
    first['ε'] = {'ε'}

    # Inicializar no terminales como conjuntos vacíos
    for nt in grammar.non_terminals:
        first[nt] = set()

    changed = True
    while changed:
        changed = False
        for prod in grammar.productions:
            head = prod.head
            body = prod.body

            old_size = len(first[head])

            if body == ['ε']:
                first[head].add('ε')
            else:
                # Calcular FIRST del cuerpo
                body_first = _first_of_sequence(body, first)
                first[head].update(body_first)

            if len(first[head]) != old_size:
                changed = True

    return first


def _first_of_sequence(sequence, first_sets) -> set:
    """
    Calcula FIRST de una secuencia de símbolos.
    Usado internamente para cuerpos de producciones.
    """
    result = set()
    all_derive_epsilon = True

    for symbol in sequence:
        if symbol == 'ε':
            result.add('ε')
            break

        sym_first = first_sets.get(symbol, set())
        result.update(sym_first - {'ε'})

        if 'ε' not in sym_first:
            all_derive_epsilon = False
            break
    else:
        # Todos los símbolos pueden derivar ε
        pass

    if all_derive_epsilon:
        result.add('ε')

    return result


def compute_follow(grammar: Grammar, first: dict) -> dict:
    """
    Calcula FOLLOW(A) para todos los no terminales.
    
    Reglas:
      1. $ ∈ FOLLOW(S) donde S es el símbolo inicial
      2. Si A -> αBβ: FIRST(β) sin {ε} ⊆ FOLLOW(B)
      3. Si A -> αBβ y epsilon en FIRST(β): FOLLOW(A) en FOLLOW(B)
      4. Si A -> αB: FOLLOW(A) en FOLLOW(B)
    """
    follow = {nt: set() for nt in grammar.non_terminals}

    # Regla 1: $ en FOLLOW del símbolo inicial
    if grammar.start_symbol:
        follow[grammar.start_symbol].add('$')

    changed = True
    while changed:
        changed = False
        for prod in grammar.productions:
            head = prod.head
            body = prod.body

            if body == ['ε']:
                continue

            for i, symbol in enumerate(body):
                if symbol not in grammar.non_terminals:
                    continue  # Solo para no terminales

                old_size = len(follow[symbol])

                # Beta = lo que viene después del símbolo actual
                beta = body[i + 1:]

                if beta:
                    # Regla 2: FIRST(β) sin {ε} ⊆ FOLLOW(symbol)
                    beta_first = _first_of_sequence(beta, first)
                    follow[symbol].update(beta_first - {'ε'})

                    # Regla 3: Si ε ∈ FIRST(β), FOLLOW(head) ⊆ FOLLOW(symbol)
                    if 'ε' in beta_first:
                        follow[symbol].update(follow[head])
                else:
                    # Regla 4: Si symbol es el último, FOLLOW(head) ⊆ FOLLOW(symbol)
                    follow[symbol].update(follow[head])

                if len(follow[symbol]) != old_size:
                    changed = True

    return follow


def compute_first_of_string(symbols: list, first: dict) -> set:
    """
    Utilidad pública: FIRST de una lista de símbolos.
    Útil para construir tablas LL(1) y LALR.
    """
    return _first_of_sequence(symbols, first)


