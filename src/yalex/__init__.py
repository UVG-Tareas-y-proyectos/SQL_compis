"""Paquete YALex."""

__all__ = ["YALexEngine"]


def __getattr__(name):
    if name == "YALexEngine":
        from .yalex_gen import YALexEngine

        return YALexEngine
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
