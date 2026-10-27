class RegexTreeExporter:
    def __init__(self):
        self.nodes = []
        self.edges = []
        self._counter = 0

    def export(self, rule_asts, svg_path, dot_path=None):
        self.nodes = []
        self.edges = []
        self._counter = 0

        root = self._new_node("YALex rules")
        for idx, (regex, ast) in enumerate(rule_asts):
            rule_node = self._new_node(f"rule {idx}: {regex}")
            self.edges.append((root, rule_node))
            ast_root = self._walk(ast)
            self.edges.append((rule_node, ast_root))

        levels = self._levels(root)
        positions = self._positions(levels)

        svg = self._to_svg(positions)
        with open(svg_path, "w", encoding="utf-8") as f:
            f.write(svg)

        if dot_path:
            with open(dot_path, "w", encoding="utf-8") as f:
                f.write(self._to_dot())

    def _walk(self, ast):
        kind = ast[0]
        if kind == "char":
            return self._new_node(repr(ast[1]))
        if kind == "str":
            return self._new_node(f"str {ast[1]!r}")
        if kind == "class":
            neg, items = ast[1]
            label = ("[^" if neg else "[") + self._short("".join(sorted(items))) + "]"
            return self._new_node(label)
        if kind == "dot":
            return self._new_node("_")
        if kind == "epsilon":
            return self._new_node("epsilon")
        if kind in ("star", "plus", "opt"):
            labels = {"star": "*", "plus": "+", "opt": "?"}
            node = self._new_node(labels[kind])
            child = self._walk(ast[1])
            self.edges.append((node, child))
            return node
        if kind == "diff":
            node = self._new_node("#")
            left = self._walk(ast[1])
            right = self._walk(ast[2])
            self.edges.extend([(node, left), (node, right)])
            return node
        if kind in ("concat", "alt"):
            node = self._new_node("concat" if kind == "concat" else "|")
            for child_ast in ast[1]:
                child = self._walk(child_ast)
                self.edges.append((node, child))
            return node
        return self._new_node(str(ast))

    def _new_node(self, label):
        node_id = f"n{self._counter}"
        self._counter += 1
        self.nodes.append((node_id, self._short(label)))
        return node_id

    def _short(self, value, limit=34):
        value = str(value).replace("\n", "\\n").replace("\t", "\\t")
        return value if len(value) <= limit else value[: limit - 3] + "..."

    def _levels(self, root):
        children = {node: [] for node, _ in self.nodes}
        for parent, child in self.edges:
            children.setdefault(parent, []).append(child)

        levels = []
        queue = [(root, 0)]
        seen = set()
        while queue:
            node, level = queue.pop(0)
            if node in seen:
                continue
            seen.add(node)
            while len(levels) <= level:
                levels.append([])
            levels[level].append(node)
            for child in children.get(node, []):
                queue.append((child, level + 1))
        return levels

    def _positions(self, levels):
        positions = {}
        x_gap = 170
        y_gap = 95
        margin = 70
        max_width = max((len(level) for level in levels), default=1)
        width = max(900, margin * 2 + max_width * x_gap)
        for depth, level in enumerate(levels):
            total = (len(level) - 1) * x_gap
            start = (width - total) / 2
            for idx, node in enumerate(level):
                positions[node] = (start + idx * x_gap, margin + depth * y_gap)
        return positions

    def _to_svg(self, positions):
        label_by_id = dict(self.nodes)
        max_x = max((x for x, _ in positions.values()), default=900) + 120
        max_y = max((y for _, y in positions.values()), default=500) + 90
        parts = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{int(max_x)}" height="{int(max_y)}" viewBox="0 0 {int(max_x)} {int(max_y)}">',
            "<style>text{font:12px Consolas,monospace}.node{fill:#f8fafc;stroke:#334155;stroke-width:1.2}.edge{stroke:#64748b;stroke-width:1.1}</style>",
            '<rect width="100%" height="100%" fill="#ffffff"/>',
        ]
        for parent, child in self.edges:
            x1, y1 = positions[parent]
            x2, y2 = positions[child]
            parts.append(f'<line class="edge" x1="{x1}" y1="{y1 + 20}" x2="{x2}" y2="{y2 - 20}"/>')
        for node_id, label in self.nodes:
            x, y = positions[node_id]
            width = max(70, min(210, 12 + len(label) * 7))
            parts.append(f'<rect class="node" x="{x - width / 2:.1f}" y="{y - 20}" width="{width}" height="40" rx="6"/>')
            parts.append(f'<text x="{x}" y="{y + 4}" text-anchor="middle">{self._xml(label)}</text>')
        parts.append("</svg>")
        return "\n".join(parts)

    def _to_dot(self):
        label_by_id = dict(self.nodes)
        lines = ["digraph regex_tree {", "  rankdir=TB;", "  node [shape=box, fontname=Consolas];"]
        for node_id, label in self.nodes:
            lines.append(f'  {node_id} [label="{self._dot(label)}"];')
        for parent, child in self.edges:
            lines.append(f"  {parent} -> {child};")
        lines.append("}")
        return "\n".join(lines)

    def _xml(self, text):
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    def _dot(self, text):
        return text.replace("\\", "\\\\").replace('"', '\\"')
