from dataclasses import dataclass, field
from typing import Any


@dataclass
class Diagnostic:
    phase: str
    message: str
    line: int = 1
    column: int = 1

    def __str__(self):
        return f'[{self.phase}] línea {self.line}, columna {self.column}: {self.message}'


class SQLError(Exception):
    def __init__(self, message, node=None, phase='semántico'):
        super().__init__(message)
        self.diagnostic = Diagnostic(phase, message, getattr(node, 'line', 1),
                                     getattr(node, 'column', 1))


@dataclass
class SyntaxNode:
    rule: str
    children: list = field(default_factory=list)
    line: int = 1
    column: int = 1

    @property
    def trees(self):
        return [c for c in self.children if isinstance(c, SyntaxNode)]

    @property
    def tokens(self):
        return [c for c in self.children if not isinstance(c, SyntaxNode)]


@dataclass
class Node:
    kind: str
    data: dict[str, Any] = field(default_factory=dict)
    line: int = 1
    column: int = 1
    meta: dict = field(default_factory=dict, repr=False)

    def __getitem__(self, key):
        return self.data[key]

    def get(self, key, default=None):
        return self.data.get(key, default)

    def walk(self):
        yield self
        for value in self.data.values():
            values = value if isinstance(value, list) else [value]
            for child in values:
                if isinstance(child, Node):
                    yield from child.walk()


def tree_lines(value, indent=0):
    prefix = '  ' * indent
    if isinstance(value, SyntaxNode):
        yield prefix + value.rule
        for child in value.children:
            yield from tree_lines(child, indent+1)
    elif isinstance(value, Node):
        yield prefix + value.kind
        for key, child in value.data.items():
            if isinstance(child, (Node, list)):
                yield prefix + '  ' + key
                for item in child if isinstance(child, list) else [child]:
                    yield from tree_lines(item, indent+2)
            else:
                yield prefix + f'  {key}: {child}'
    else:
        yield prefix + (f'{value.type}: {value.value}' if hasattr(value, 'type') else str(value))
