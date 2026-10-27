"""
yapar_parser.py - Lee y parsea archivos .yalp (formato YAPar)

Formato esperado del archivo:
    %token TOKEN_A TOKEN_B
    IGNORE WS
    %%
    production:
        TOKEN_A production TOKEN_B
        | TOKEN_A
    ;
"""

import re
try:
    from .grammar import Grammar
except ImportError:
    from grammar import Grammar


class YAParParser:
    def __init__(self):
        self.grammar = None
        self.errors = []

    def parse_file(self, filepath):
        """Lee y parsea un archivo .yalp. Retorna un objeto Grammar."""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
        except FileNotFoundError:
            raise FileNotFoundError(f"Archivo no encontrado: {filepath}")

        return self.parse_string(content, filepath)

    def parse_string(self, content, source_name="<string>"):
        """Parsea el contenido de un archivo .yalp como string."""
        self.grammar = Grammar()
        self.errors = []

        # Eliminar comentarios /* ... */
        content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)

        # Separar sección de tokens y sección de producciones
        if '%%' not in content:
            self._error(0, "Falta el separador '%%' entre tokens y producciones")
            raise SyntaxError("Archivo .yalp inválido: falta '%%'")

        parts = content.split('%%', 1)
        token_section = parts[0].strip()
        production_section = parts[1].strip()

        self._parse_tokens(token_section, source_name)
        self._parse_productions(production_section, source_name)

        # El primer no terminal de las producciones es el símbolo inicial
        if self.grammar.productions:
            # El start es el head de la primera producción real
            first_heads = []
            for line in production_section.split('\n'):
                line = line.strip()
                if line and not line.startswith('|') and ':' in line:
                    first_heads.append(line.split(':')[0].strip())
            if first_heads:
                self.grammar.start_symbol = first_heads[0]

        if self.errors:
            print("Advertencias al parsear:")
            for e in self.errors:
                print(f"  {e}")

        return self.grammar

    def _parse_tokens(self, section, source_name):
        """Parsea la sección de tokens (%token, IGNORE)."""
        for line_num, line in enumerate(section.split('\n'), 1):
            line = line.strip()
            if not line:
                continue

            if line.startswith('%token'):
                # %token TOKEN_A TOKEN_B ...
                tokens = line[len('%token'):].split()
                for token in tokens:
                    if token:
                        self.grammar.terminals.add(token)

            elif line.startswith('IGNORE'):
                # IGNORE TOKEN_NAME
                parts = line.split()
                if len(parts) >= 2:
                    self.grammar.ignored_tokens.add(parts[1])
                else:
                    self._error(line_num, f"IGNORE sin token: '{line}'")

    def _parse_productions(self, section, source_name):
        """Parsea la sección de producciones."""
        # Normalizar: unir líneas de continuación
        lines = section.split('\n')
        
        current_head = None
        current_bodies = []
        current_body = []
        line_num = 0

        i = 0
        while i < len(lines):
            line = lines[i].strip()
            line_num += 1

            if not line:
                i += 1
                continue

            # Fin de producción
            if line == ';':
                if current_head and current_body is not None:
                    current_bodies.append(current_body)
                if current_head:
                    self._register_production(current_head, current_bodies)
                current_head = None
                current_bodies = []
                current_body = []
                i += 1
                continue

            # Inicio de nueva producción: "nombre:"
            if ':' in line and not line.startswith('|'):
                # Puede ser "nombre:" sola o "nombre: cuerpo"
                head_part, _, body_part = line.partition(':')
                head = head_part.strip()

                if head and head[0].islower():
                    # Es un no terminal válido (minúsculas en YAPar)
                    if current_head:
                        # Guardar producción anterior si quedó incompleta
                        if current_body:
                            current_bodies.append(current_body)
                        self._register_production(current_head, current_bodies)
                        current_bodies = []

                    current_head = head
                    current_body = []
                    body_part = body_part.strip()
                    if body_part and body_part != '|':
                        current_body = self._tokenize_body(body_part)
                    i += 1
                    continue

            # Alternativa: "| cuerpo"
            if line.startswith('|'):
                if current_head is None:
                    self._error(line_num, f"'|' sin producción activa: '{line}'")
                    i += 1
                    continue
                if current_body is not None:
                    current_bodies.append(current_body)
                rest = line[1:].strip()
                current_body = self._tokenize_body(rest) if rest else ['ε']
                i += 1
                continue

            # Continuación del cuerpo actual
            if current_head and current_body is not None:
                current_body.extend(self._tokenize_body(line))

            i += 1

        # Registrar última producción si quedó sin ';'
        if current_head:
            if current_body:
                current_bodies.append(current_body)
            self._register_production(current_head, current_bodies)

    def _tokenize_body(self, body_str):
        """Divide el cuerpo de una producción en símbolos."""
        if not body_str or body_str.strip() in ('ε', 'epsilon', ''):
            return ['ε']
        return body_str.split()

    def _register_production(self, head, bodies):
        """Registra todas las alternativas de una producción en la gramática."""
        self.grammar.non_terminals.add(head)
        if not bodies:
            self.grammar.add_production(head, ['ε'])
            return
        for body in bodies:
            if not body:
                body = ['ε']
            self.grammar.add_production(head, body)
            # Los símbolos en MAYÚSCULAS son terminales
            for sym in body:
                if sym != 'ε' and (sym.isupper() or (sym[0].isupper() and sym in self.grammar.terminals)):
                    self.grammar.terminals.add(sym)
                elif sym != 'ε' and sym[0].islower():
                    self.grammar.non_terminals.add(sym)

    def _error(self, line_num, msg):
        self.errors.append(f"Línea {line_num}: {msg}")


