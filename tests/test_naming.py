"""Naming guard: no cryptic one- or two-letter variable names in pbridge.

Every name a developer binds (variables, parameters, loop targets, `except ... as`, comprehension
variables, lambda parameters) must say what it holds. Only a few universal conventions are allowed:
loop indexes `i`/`j`, coordinates `x`/`y` and their deltas `dx`/`dy`, `id`, `ok` and the throwaway `_`.

The TypeScript side has the same rule in `js/scripts/check-names.mjs` (`npm --prefix js run lint`);
this test runs it too, so `pb selftest` guards both languages.
"""
from __future__ import annotations

import ast
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ALLOWED = {"_", "i", "j", "x", "y", "dx", "dy", "id", "ok"}
MAX_SHORT = 2          # names of this length or shorter must be in ALLOWED


def bound_names(tree: ast.AST):
    """Yield (name, line) for every name the code binds."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            yield node.id, node.lineno
        elif isinstance(node, ast.arg):
            yield node.arg, node.lineno
        elif isinstance(node, ast.ExceptHandler) and node.name:
            yield node.name, node.lineno
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            yield node.name, node.lineno
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                if alias.asname:
                    yield alias.asname, node.lineno


def short_names(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(), str(path))
    return sorted({f"{path.relative_to(ROOT)}:{line} {name}" for name, line in bound_names(tree)
                   if len(name) <= MAX_SHORT and name not in ALLOWED})


class NamingTest(unittest.TestCase):
    def test_no_cryptic_names(self):
        files = sorted((ROOT / "src").rglob("*.py")) + sorted((ROOT / "tests").glob("*.py"))
        problems = [problem for path in files for problem in short_names(path)]
        self.assertEqual(problems, [], "rename these to descriptive names:\n  " + "\n  ".join(problems))

    @unittest.skipUnless(shutil.which("node") and (ROOT / "js" / "node_modules").is_dir(), "node or js/node_modules missing")
    def test_no_cryptic_names_in_typescript(self):
        result = subprocess.run(["node", str(ROOT / "js" / "scripts" / "check-names.mjs")], capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
