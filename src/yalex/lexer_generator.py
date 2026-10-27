class LexerGenerator:
    def generate(self, header: str, dfa: dict, actions: list, out_path: str):
        lines = []
        lines.extend(self._file_header(header))
        lines.extend(self._dfa_tables(dfa))
        lines.extend(self._actions(actions))
        lines.extend(self._tokenizer())
        lines.extend(self._main_block())

        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        print(f"[YALex] Lexer generado: {out_path}")

    def _file_header(self, header: str) -> list:
        lines = [
            "import sys",
            "from pathlib import Path",
            "",
            "BASE = Path(__file__).resolve().parent",
            "for candidate in (BASE, BASE / 'shared', BASE.parent / 'src', BASE.parent / 'src' / 'shared'):",
            "    if str(candidate) not in sys.path:",
            "        sys.path.insert(0, str(candidate))",
            "",
            "from tok import Token, EOF_TOKEN",
            "",
        ]
        if header:
            lines.extend(header.splitlines())
            lines.append("")
        return lines

    def _dfa_tables(self, dfa: dict) -> list:
        return [
            f"DFA_START  = {dfa['start']}",
            f"DFA_STATES = {dfa['num_states']}",
            f"DFA_TRANS  = {repr(dfa['trans'])}",
            f"DFA_ACCEPT = {repr(dfa['accepting'])}",
            "",
        ]

    def _actions(self, actions: list) -> list:
        lines = ["ACTIONS = []", ""]
        for idx, action in enumerate(actions):
            lines.append(f"def _action_{idx}(lxm, line, col):")
            if not action.strip() or action.strip() == "pass":
                lines.append("    return None")
            else:
                for line in action.strip().splitlines():
                    lines.append("    " + line.rstrip())
            lines.extend([f"ACTIONS.append(_action_{idx})", ""])
        return lines

    def _tokenizer(self) -> list:
        return [
            "def tokenize(text: str) -> list:",
            "    tokens = []",
            "    pos, lineno, col = 0, 1, 1",
            "    n = len(text)",
            "    while pos < n:",
            "        state = DFA_START",
            "        last_accept = None",
            "        last_pos = pos",
            "        i = pos",
            "        while i < n:",
            "            ch = text[i]",
            "            nxt = DFA_TRANS.get(state, {}).get(ch)",
            "            if nxt is None:",
            "                break",
            "            state = nxt",
            "            if state in DFA_ACCEPT:",
            "                last_accept = DFA_ACCEPT[state]",
            "                last_pos = i + 1",
            "            i += 1",
            "        if last_accept is None:",
            "            ch = text[pos]",
            "            raise SyntaxError(",
            "                f'LEX ERROR linea {lineno} col {col}: caracter inesperado {repr(ch)}'",
            "            )",
            "        lexeme = text[pos:last_pos]",
            "        result = ACTIONS[last_accept[0]](lexeme, lineno, col)",
            "        if isinstance(result, Token):",
            "            tokens.append(result)",
            "        elif isinstance(result, tuple) and len(result) == 2:",
            "            tokens.append(Token(result[0], result[1], lineno, col))",
            "        for ch in lexeme:",
            "            if ch == '\\n':",
            "                lineno += 1",
            "                col = 1",
            "            else:",
            "                col += 1",
            "        pos = last_pos",
            "    tokens.append(EOF_TOKEN)",
            "    return tokens",
            "",
        ]

    def _main_block(self) -> list:
        return [
            "if __name__ == '__main__':",
            "    if len(sys.argv) < 2:",
            "        print('Uso: python lexer.py <archivo>')",
            "        sys.exit(1)",
            "    text = open(sys.argv[1], encoding='utf-8').read()",
            "    for token in tokenize(text):",
            "        print(token)",
        ]

