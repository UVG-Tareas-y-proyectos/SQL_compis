import re


class YALReader:
    def read(self, path: str) -> str:
        return open(path, 'r', encoding='utf-8').read()

    def split(self, text: str):
        header, trailer, lets = "", "", {}

        # Header: primer bloque { }
        if text.lstrip().startswith("{"):
            start = text.find("{")
            depth = 0
            for i in range(start, len(text)):
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        header = text[start + 1:i].strip()
                        text = text[:start] + text[i + 1:]
                        break

        # Trailer: bloque separado DESPUES del bloque rule (poco comun)
        # Se omite extraccion automatica para no confundir con acciones de reglas

        # Definiciones let
        lets_re = re.compile(
            r'let\s+([A-Za-z_]\w*)\s*=\s*(.+?)(?=\n(?:let|rule|\Z))', re.S
        )
        for m in lets_re.finditer(text):
            lets[m.group(1)] = m.group(2).strip()

        # Bloque rule
        rule_re = re.compile(r'rule\s+([A-Za-z_]\w*)\s*(?:\[.*?\]\s*)?=\s*(.+)', re.S)
        m = rule_re.search(text)
        if not m:
            raise ValueError("No se encontró bloque 'rule ... =' en el archivo .yal")

        entrypoint  = m.group(1)
        rules_block = text[m.start(2):].strip()
        return header, lets, entrypoint, rules_block, trailer

    def remove_comments(self, s: str) -> str:
        out = []
        in_dquote = in_squote = in_class = False
        brace_depth = 0
        i = 0
        while i < len(s):
            c = s[i]
            if s.startswith('(*', i) and not in_dquote and not in_squote \
               and not in_class and brace_depth == 0:
                end = s.find('*)', i + 2)
                if end == -1:
                    break
                i = end + 2
                continue
            if   c == '"'  and not in_squote and not in_class and brace_depth == 0:
                in_dquote = not in_dquote
            elif c == "'"  and not in_dquote and not in_class and brace_depth == 0:
                in_squote = not in_squote
            elif c == '['  and not in_dquote and not in_squote and brace_depth == 0:
                in_class = True
            elif c == ']'  and in_class:
                in_class = False
            elif c == '{'  and not in_dquote and not in_squote:
                brace_depth += 1
            elif c == '}'  and brace_depth > 0 and not in_dquote and not in_squote:
                brace_depth -= 1
            out.append(c)
            i += 1
        return ''.join(out)

    def split_alternatives(self, rules_block: str) -> list:
        alternatives = []
        i, n = 0, len(rules_block)
        while i < n:
            while i < n and rules_block[i].isspace():
                i += 1
            if i < n and rules_block[i] == '|':
                i += 1
                while i < n and rules_block[i].isspace():
                    i += 1

            start = i
            in_sq = in_dq = in_squote = escaped = False
            while i < n:
                c = rules_block[i]
                if escaped:
                    escaped = False; i += 1; continue
                if c == '\\':
                    escaped = True;  i += 1; continue
                if   c == '"'  and not in_squote and not in_sq:  in_dq     = not in_dq
                elif c == "'"  and not in_dq     and not in_sq:  in_squote = not in_squote
                elif c == '['  and not in_dq     and not in_squote: in_sq  = True
                elif c == ']'  and in_sq:                           in_sq  = False
                elif c == '{'  and not in_sq and not in_dq and not in_squote: break
                i += 1

            regexp = rules_block[start:i].strip()
            if i >= n or rules_block[i] != '{':
                break

            depth, brace_start = 0, i
            while i < n:
                if   rules_block[i] == '{': depth += 1
                elif rules_block[i] == '}':
                    depth -= 1
                    if depth == 0:
                        action = rules_block[brace_start + 1:i].strip()
                        i += 1
                        break
                i += 1
            alternatives.append((regexp, action))
        return alternatives
