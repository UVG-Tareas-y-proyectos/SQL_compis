from dataclasses import dataclass, field

from .ast_builder import ASTBuilder
from .frontend import SQLFrontend
from .interpreter import Interpreter
from .model import SQLError, Diagnostic
from .semantic import SemanticAnalyzer
from .storage import FileStorage


@dataclass
class Compilation:
    tokens: list = field(default_factory=list)
    tree: object = None
    ast: object = None
    diagnostics: list = field(default_factory=list)
    results: list = field(default_factory=list)

    @property
    def ok(self):
        return not self.diagnostics


class SQLEngine:
    def __init__(self, database='database'):
        self.frontend = SQLFrontend()
        self.storage = FileStorage(database)

    def analyze(self, sql):
        parsed = self.frontend.parse(sql)
        result = Compilation(parsed.tokens, parsed.tree, diagnostics=parsed.diagnostics)
        if not result.ok:
            return result
        try:
            result.ast = ASTBuilder().visit(parsed.tree)
            with self.storage.lock:
                self.storage.reload()
                SemanticAnalyzer(self.storage.metadata).analyze(result.ast)
        except SQLError as exc:
            result.diagnostics.append(exc.diagnostic)
        return result

    def execute(self, sql):
        with self.storage.lock:
            result = self.analyze(sql)
            if not result.ok:
                return result
            for statement in result.ast['statements']:
                try:
                    # Volver a ligar contra el catálogo real tras cada sentencia.
                    SemanticAnalyzer(self.storage.metadata).statement(statement)
                    result.results.append(Interpreter(self.storage).execute(statement))
                except SQLError as exc:
                    result.diagnostics.append(exc.diagnostic)
                    break
                except OSError as exc:
                    result.diagnostics.append(Diagnostic('almacenamiento', str(exc), statement.line, statement.column))
                    break
            return result
