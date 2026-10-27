import re


class RegexParser:

    ESCAPES = {'n': '\n', 't': '\t', 'r': '\r',
               '\\': '\\', '"': '"', "'": "'"}

    def __init__(self, pattern: str, lets: dict = None):
        s = pattern
        # Expandir macros 'let' en el patrón
        if lets:
            for k, v in lets.items():
                s = re.sub(r'\{' + re.escape(k) + r'\}', '(' + v + ')', s)
            for k, v in lets.items():
                s = re.sub(r'(?<!\w)' + re.escape(k) + r'(?!\w)', '(' + v + ')', s)
        self.s = s
        self.i = 0
        self.n = len(s)


    def parse(self):
        """Punto de entrada: retorna el AST raíz."""
        return self._alt()


    def _alt(self):
        self._skip_ws()
        parts = [self._concat()]
        self._skip_ws()
        while self._peek() == '|':
            self._consume()
            parts.append(self._concat())
            self._skip_ws()
        return parts[0] if len(parts) == 1 else ('alt', parts)

    def _concat(self):
        nodes = []
        self._skip_ws()
        while self._peek() not in (None, ')', '|'):
            node = self._repeat()
            if node is None:
                break
            nodes.append(node)
            self._skip_ws()
        if not nodes:
            return ('epsilon',)
        return nodes[0] if len(nodes) == 1 else ('concat', nodes)

    def _repeat(self):
        self._skip_ws()
        node = self._diff()
        if node is None:
            return None
        self._skip_ws()
        while self._peek() in ('*', '+', '?'):
            op = self._consume()
            node = ('star', node) if op == '*' else \
                   ('plus', node) if op == '+' else \
                   ('opt',  node)
            self._skip_ws()
        return node

    def _diff(self):
        self._skip_ws()
        node = self._atom()
        self._skip_ws()
        while self._peek() == '#':
            self._consume()
            right = self._atom()
            node = ('diff', node, right)
            self._skip_ws()
        return node

    def _atom(self):
        self._skip_ws()
        c = self._peek()
        if c is None:
            return None
        if c == '(':
            self._consume()
            sub = self._alt()
            if self._peek() == ')':
                self._consume()
            return sub
        if c in ('"', "'"):
            return self._string(c)
        if c == '[':
            return self._char_class()
        if c in ('.', '_'):
            self._consume()
            return ('dot',)
        if c == '\\':
            self._consume()
            nxt = self._consume()
            return ('char', self.ESCAPES.get(nxt, nxt) if nxt else '')
        if c in ('*', '+', '?', ')', '|'):
            return None
        self._consume()
        return ('char', c)


    def _peek(self):
        return self.s[self.i] if self.i < self.n else None

    def _consume(self):
        c = self._peek()
        if c is not None:
            self.i += 1
        return c

    def _skip_ws(self):
        while self._peek() is not None and self._peek().isspace():
            self._consume()

    def _string(self, quote):
        self._consume()
        chars = []
        while True:
            c = self._consume()
            if c is None or c == quote:
                break
            if c == '\\':
                nxt = self._consume()
                chars.append(self.ESCAPES.get(nxt, nxt) if nxt else '')
            else:
                chars.append(c)
        content = ''.join(chars)
        if not content:
            return ('epsilon',)
        return ('char', content) if len(content) == 1 else ('str', content)

    def _char_class(self):
        self._consume()
        neg = self._peek() == '^'
        if neg:
            self._consume()
        items = []
        while True:
            c = self._consume()
            if c is None or c == ']':
                break
            if c == '\\':
                c = self._consume()
                items.append(self.ESCAPES.get(c, c) if c else '')
                continue
            if c == '-' and items and self._peek() not in (']', None):
                end = self._consume()
                if end == '\\':
                    end = self._consume()
                if end:
                    for ch in range(ord(items[-1]) + 1, ord(end) + 1):
                        items.append(chr(ch))
                continue
            items.append(c)
        return ('class', (neg, set(items)))
