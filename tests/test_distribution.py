import ast
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class DistributionTests(unittest.TestCase):
    def test_local_document_links_exist(self):
        documents = [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]
        for document in documents:
            text = document.read_text(encoding="utf-8")
            for link in re.findall(r"\]\(([^)\s]+)\)", text):
                if link.startswith(("https://", "http://", "#")):
                    continue
                target = document.parent / link.split("#", 1)[0]
                with self.subTest(document=document.name, link=link):
                    self.assertTrue(target.is_file(), f"Missing document: {target}")

    def test_runtime_python_has_no_third_party_dependencies(self):
        paths = [
            ROOT / "tools" / "install.py",
            ROOT / "templates" / "ghes" / ".github" / "scripts"
            / "build_review_payload.py",
        ]
        for path in paths:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                modules = []
                if isinstance(node, ast.Import):
                    modules = [alias.name.split(".")[0] for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    modules = [(node.module or "").split(".")[0]]
                for module in modules:
                    with self.subTest(path=path.name, module=module):
                        self.assertIn(module, sys.stdlib_module_names)


if __name__ == "__main__":
    unittest.main()
