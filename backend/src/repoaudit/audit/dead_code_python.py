"""Python static dead code scanner backed by Vulture and Python AST."""

from __future__ import annotations

import ast
import logging
from pathlib import Path
from typing import Any

import vulture

logger = logging.getLogger(__name__)


class PythonDeadCodeScanner:
    """Scans Python source files for unused imports, functions, classes, and variables."""

    def scan_project(self, rel_paths: list[str], root_dir: str) -> list[dict[str, Any]]:
        """
        Scans all Python files under root_dir.
        Returns a list of raw candidate dictionaries:
            [{"path": rel_path, "name": symbol_name, "typ": "import"|"function"|"class"|"variable", "line": lineno}]
        """
        py_files = [p.replace("\\", "/") for p in rel_paths if p.endswith(".py")]
        v = vulture.Vulture()

        candidates: list[dict[str, Any]] = []

        for rel_path in py_files:
            abs_path = Path(root_dir) / rel_path
            if not abs_path.is_file():
                continue

            try:
                code_text = abs_path.read_text(encoding="utf-8", errors="ignore")
                v.scan(code_text, filename=rel_path)

                # AST fallback check for unused imports
                unused_imports_ast = self._check_unused_imports_ast(code_text, rel_path)
                candidates.extend(unused_imports_ast)
            except Exception as exc:
                logger.debug("Failed to scan Python file %s: %s", rel_path, exc)

        for item in v.get_unused_code():
            # Avoid duplicate import candidates if captured by AST
            cand_typ = getattr(item, "typ", "symbol")
            filename = str(getattr(item, "filename", "unknown.py")).replace("\\", "/")
            name = str(getattr(item, "name", "symbol"))
            lineno = getattr(item, "first_lineno", 1)

            candidates.append(
                {
                    "path": filename,
                    "name": name,
                    "typ": cand_typ,
                    "line": lineno,
                    "confidence": getattr(item, "confidence", 60),
                }
            )

        return candidates

    def _check_unused_imports_ast(self, code_text: str, rel_path: str) -> list[dict[str, Any]]:
        """AST check for imports declared in a file that are never referenced in that file."""
        try:
            tree = ast.parse(code_text)
        except Exception:
            return []

        imported_names: dict[str, int] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name_used = alias.asname or alias.name
                    imported_names[name_used] = node.lineno
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    name_used = alias.asname or alias.name
                    imported_names[name_used] = node.lineno

        if not imported_names:
            return []

        # Find all Name nodes that are NOT in import statements
        used_names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and not isinstance(
                node.ctx, (ast.Store, ast.Del)
            ):
                used_names.add(node.id)
            elif isinstance(node, ast.Attribute):
                used_names.add(node.attr)

        candidates = []
        for imp_name, lineno in imported_names.items():
            if imp_name not in used_names and not imp_name.startswith("_"):
                candidates.append(
                    {
                        "path": rel_path,
                        "name": imp_name,
                        "typ": "import",
                        "line": lineno,
                        "confidence": 90,
                    }
                )

        return candidates
