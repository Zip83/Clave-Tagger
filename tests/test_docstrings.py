import ast
import unittest
from pathlib import Path


class DocstringTests(unittest.TestCase):
    def test_placeholder_docstrings_are_not_reintroduced(self):
        """Mechanical placeholder docstrings should not pass review."""
        roots = [Path("music_category"), Path("music_category_gui.py")]
        placeholders = []
        for root in roots:
            paths = [root] if root.is_file() else sorted(root.glob("*.py"))
            for path in paths:
                tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        docstring = ast.get_docstring(node) or ""
                        if docstring.startswith("Provide ") and docstring.endswith(" behavior."):
                            placeholders.append(f"{path}:{node.lineno}:{node.name}")

        self.assertEqual(placeholders, [])


if __name__ == "__main__":
    unittest.main()
