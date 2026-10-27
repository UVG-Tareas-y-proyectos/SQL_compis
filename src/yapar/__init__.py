"""Paquete YAPar."""

__all__ = [
    'YAParParser', 'Grammar', 'Production', 'LRItem',
    'compute_first', 'compute_follow', 'compute_first_of_string',
    'LR0Automaton', 'SLRTable', 'LALRTable', 'LR1Automaton', 'LL1Table',
]


def __getattr__(name):
    if name == "YAParParser":
        from .yapar_parser import YAParParser

        return YAParParser
    if name in {"Grammar", "Production", "LRItem"}:
        from .grammar import Grammar, LRItem, Production

        return {"Grammar": Grammar, "Production": Production, "LRItem": LRItem}[name]
    if name in {"compute_first", "compute_follow", "compute_first_of_string"}:
        from .first_follow import compute_first, compute_first_of_string, compute_follow

        return {
            "compute_first": compute_first,
            "compute_follow": compute_follow,
            "compute_first_of_string": compute_first_of_string,
        }[name]
    if name == "LR0Automaton":
        from .lr0_automaton import LR0Automaton

        return LR0Automaton
    if name == "SLRTable":
        from .slr1_table import SLRTable

        return SLRTable
    if name in {"LALRTable", "LR1Automaton"}:
        from .lalr_table import LALRTable, LR1Automaton

        return {"LALRTable": LALRTable, "LR1Automaton": LR1Automaton}[name]
    if name == "LL1Table":
        from .ll1_table import LL1Table

        return LL1Table
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
