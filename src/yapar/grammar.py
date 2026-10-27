"""
grammar.py - Estructuras de datos para gramáticas libres de contexto
"""

class Production:
    """Representa una producción A -> alpha"""
    def __init__(self, head, body):
        self.head = head          # str: lado izquierdo (no terminal)
        self.body = body          # list[str]: lado derecho (terminales y no terminales)

    def __repr__(self):
        body = ["epsilon" if s == "ε" else s for s in self.body]
        body_str = ' '.join(body) if body else 'epsilon'
        return f"{self.head} -> {body_str}"

    def __eq__(self, other):
        return isinstance(other, Production) and self.head == other.head and self.body == other.body

    def __hash__(self):
        return hash((self.head, tuple(self.body)))


class Grammar:
    """Gramática libre de contexto G = (V, T, P, S)"""
    def __init__(self):
        self.terminals = set()          # Terminales (tokens)
        self.non_terminals = set()      # No terminales
        self.productions = []           # Lista de Production
        self.start_symbol = None        # Símbolo inicial
        self.ignored_tokens = set()     # Tokens a ignorar (IGNORE)
        self.augmented_start = None     # S' para gramática aumentada

    def add_production(self, head, body):
        """Agrega una producción. body es list[str]."""
        p = Production(head, body)
        self.productions.append(p)
        self.non_terminals.add(head)
        for symbol in body:
            if symbol == 'ε':
                continue
            if symbol.isupper() or symbol.startswith("'"):
                self.terminals.add(symbol)
        return p

    def get_productions_for(self, non_terminal):
        """Retorna todas las producciones de un no terminal dado."""
        return [p for p in self.productions if p.head == non_terminal]

    def augment(self):
        """
        Crea gramática aumentada agregando S' -> S
        Necesario para construcción del autómata LR(0)
        """
        if self.augmented_start:
            return  # Ya fue aumentada
        if not self.start_symbol:
            raise ValueError("No se puede aumentar una gramatica sin simbolo inicial")

        augmented = self.start_symbol + "'"
        while augmented in self.non_terminals:
            augmented += "'"
        self.augmented_start = augmented
        aug_prod = Production(self.augmented_start, [self.start_symbol])
        self.productions.insert(0, aug_prod)
        self.non_terminals.add(self.augmented_start)
        return aug_prod

    def __repr__(self):
        lines = [f"Start: {self.start_symbol}"]
        lines.append(f"Terminals: {self.terminals}")
        lines.append(f"Non-terminals: {self.non_terminals}")
        lines.append("Productions:")
        for i, p in enumerate(self.productions):
            lines.append(f"  ({i}) {p}")
        return '\n'.join(lines)


class LRItem:
    """
    Item LR(0): A -> α • β
    El punto (•) se representa como índice `dot_pos`
    """
    def __init__(self, production, dot_pos=0, lookahead=None):
        self.production = production    # Production
        self.dot_pos = dot_pos          # int: posición del punto
        self.lookahead = lookahead      # set[str] | None: para items LR(1)/LALR

    @property
    def dot_symbol(self):
        """Símbolo inmediatamente después del punto. None si el punto está al final."""
        if self.dot_pos < len(self.production.body):
            sym = self.production.body[self.dot_pos]
            return None if sym == 'ε' else sym
        return None

    @property
    def is_complete(self):
        """True si el punto está al final (item kernel completo)."""
        return self.dot_pos >= len(self.production.body) or \
               (len(self.production.body) == 1 and self.production.body[0] == 'ε')

    def advance(self):
        """Retorna nuevo item con el punto avanzado una posición."""
        return LRItem(self.production, self.dot_pos + 1, 
                      frozenset(self.lookahead) if self.lookahead else None)

    def __eq__(self, other):
        if not isinstance(other, LRItem):
            return False
        base = self.production == other.production and self.dot_pos == other.dot_pos
        if self.lookahead is not None and other.lookahead is not None:
            return base and frozenset(self.lookahead) == frozenset(other.lookahead)
        return base

    def __hash__(self):
        la = frozenset(self.lookahead) if self.lookahead else None
        return hash((self.production.head, tuple(self.production.body), self.dot_pos, la))

    def __repr__(self):
        body = list(self.production.body)
        body.insert(self.dot_pos, '.')
        body_str = ' '.join(body)
        la_str = f", {sorted(self.lookahead)}" if self.lookahead else ""
        return f"[{self.production.head} -> {body_str}{la_str}]"
