"""
token.py - Estructura de datos para tokens
Compartida entre YALex y YAPar
"""

from dataclasses import dataclass


@dataclass
class Token:
    """Representa un token producido por el analizador léxico."""
    type: str       # Tipo del token: 'ID', 'INT', 'SUMA', etc.
    value: str      # Valor (lexema): 'suma', '42', '+', etc.
    line: int = 0   # Línea en el archivo fuente
    col: int = 0    # Columna en el archivo fuente

    def __repr__(self):
        return f"Token({self.type}, {self.value!r}, L{self.line}:C{self.col})"

    @property
    def column(self):
        """Alias compatible con el árbol y los diagnósticos de Compiscript."""
        return self.col

    def __str__(self):
        return self.value

    def __eq__(self, other):
        if isinstance(other, Token):
            return self.type == other.type and self.value == other.value
        return False


# Token especial de fin de entrada
EOF_TOKEN = Token(type='$', value='$', line=-1, col=-1)
