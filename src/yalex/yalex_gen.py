"""
yalex_gen.py - Orquestador principal de YALex

Une todas las etapas del pipeline:
  .yal -> regex -> NFA -> DFA -> lexer.py

Uso:
    python yalex_gen.py example.yal -o lexer.py
"""

import re
import sys
import argparse

try:
    from .yal_reader import YALReader
    from .nfa import NFABuilder
    from .dfa import DFABuilder
    from .lexer_generator import LexerGenerator
    from .regex_parser import RegexParser
    from .regex_tree import RegexTreeExporter
except ImportError:
    from yal_reader import YALReader
    from nfa import NFABuilder
    from dfa import DFABuilder
    from lexer_generator import LexerGenerator
    from regex_parser import RegexParser
    from regex_tree import RegexTreeExporter


class YALexEngine:
    """
    Orquesta el pipeline completo de YALex:
      1. Leer y descomponer el archivo .yal
      2. Construir NFA combinado desde las reglas
      3. Convertir NFA a DFA (subconjuntos)
      4. Generar el código Python del lexer
    """

    def __init__(self):
        self.reader    = YALReader()
        self.nfa_build = NFABuilder()
        self.dfa_build = DFABuilder()
        self.generator = LexerGenerator()
        self.tree_exporter = RegexTreeExporter()

    def compile(self, yal_path: str, out_path: str = 'lexer.py',
                tree_path: str = None, dot_path: str = None) -> dict:
        text = self.reader.remove_comments(self.reader.read(yal_path))
        header, lets, _entry, rules_block, _trailer = self.reader.split(text)
        rules_block = self.reader.remove_comments(rules_block)

        for k, v in lets.items():
            rules_block = re.sub(r'\{' + re.escape(k) + r'\}', '(' + v + ')', rules_block)

        alternatives = self.reader.split_alternatives(rules_block)
        if not alternatives:
            raise ValueError("No se encontraron reglas en el archivo .yal")

        rule_asts = [
            (regex, RegexParser(regex, lets).parse())
            for regex, _action in alternatives
        ]
        if tree_path:
            self.tree_exporter.export(rule_asts, tree_path, dot_path)

        nfa_start, accept_map = self.nfa_build.build_combined(alternatives, lets)
        dfa     = self.dfa_build.build(nfa_start, accept_map)
        actions = [action for _regex, action in alternatives]
        self.generator.generate(header, dfa, actions, out_path)
        return dfa


def main():
    ap = argparse.ArgumentParser(description='YALex - Generador de Analizadores Lexicos')
    ap.add_argument('file',        help='Archivo .yal de especificacion')
    ap.add_argument('-o', '--out', default='lexer.py', help='Archivo de salida')
    ap.add_argument('--tree', help='Archivo SVG para graficar el arbol de expresiones')
    ap.add_argument('--dot', help='Archivo DOT opcional para Graphviz')
    args = ap.parse_args()
    YALexEngine().compile(args.file, args.out, args.tree, args.dot)


if __name__ == '__main__':
    main()
