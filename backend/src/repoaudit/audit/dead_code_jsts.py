"""TypeScript/JavaScript & package.json static dead code scanner."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Standard build / CLI tools that may not be directly imported in source code
BUILD_TOOLING_PACKAGES = {
    "typescript",
    "vite",
    "vitest",
    "tailwindcss",
    "postcss",
    "autoprefixer",
    "eslint",
    "prettier",
    "ruff",
    "hatchling",
    "pytest",
    "mypy",
    "nodewebkit",
    "electron",
    "ts-node",
    "tsx",
    "rimraf",
    "concurrently",
    "cross-env",
}


class JSTSDeadCodeScanner:
    """Scans JS/TS codebases and package manifests for unused exports & dependencies."""

    def scan_project(self, rel_paths: list[str], root_dir: str) -> list[dict[str, Any]]:
        """
        Returns list of candidates:
            [{"path": rel_path, "name": symbol_or_package, "typ": "dependency"|"export"|"orphan_file"}]
        """
        candidates: list[dict[str, Any]] = []

        # 1. Package.json Unused Dependency Scan
        pkg_candidates = self._scan_package_dependencies(rel_paths, root_dir)
        candidates.extend(pkg_candidates)

        # 2. JS/TS Unreferenced Exports & Orphan File Scan
        jsts_files = [
            p.replace("\\", "/")
            for p in rel_paths
            if p.endswith((".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"))
            and "node_modules" not in p
            and ".next" not in p
            and "dist" not in p
        ]

        export_candidates = self._scan_jsts_exports_and_imports(jsts_files, root_dir)
        candidates.extend(export_candidates)

        return candidates

    def _scan_package_dependencies(
        self, rel_paths: list[str], root_dir: str
    ) -> list[dict[str, Any]]:
        """Scans package.json for packages declared in dependencies but never imported."""
        candidates: list[dict[str, Any]] = []
        pkg_paths = [p for p in rel_paths if os_path_basename(p) == "package.json"]

        for pkg_rel in pkg_paths:
            abs_pkg = Path(root_dir) / pkg_rel
            if not abs_pkg.is_file():
                continue

            try:
                pkg_data = json.loads(abs_pkg.read_text(encoding="utf-8"))
                deps = dict(pkg_data.get("dependencies", {}))
                dev_deps = dict(pkg_data.get("devDependencies", {}))
                all_deps = {**deps, **dev_deps}
            except Exception:
                continue

            if not all_deps:
                continue

            # Read all source code in project directory to find import strings
            all_source_code = []
            for r in rel_paths:
                if (
                    r.endswith((".js", ".jsx", ".ts", ".tsx", ".html", ".vue", ".svelte", ".py"))
                    and not r.endswith("package.json")
                    and "node_modules" not in r
                ):
                    fpath = Path(root_dir) / r
                    if fpath.is_file():
                        try:
                            all_source_code.append(fpath.read_text(encoding="utf-8", errors="ignore"))
                        except Exception:
                            pass

            full_corpus = "\n".join(all_source_code)

            for dep_name in all_deps:
                # Skip toolings / types
                if dep_name.startswith("@types/") or dep_name in BUILD_TOOLING_PACKAGES:
                    continue

                # Check if package name is imported
                # Match: import ... from 'package' or require('package')
                pattern = r"['\"]" + re.escape(dep_name) + r"(?:/[^'\"]*)?['\"]"
                if not re.search(pattern, full_corpus):
                    candidates.append(
                        {
                            "path": pkg_rel,
                            "name": dep_name,
                            "typ": "dependency",
                            "line": 1,
                            "confidence": 85,
                        }
                    )

        return candidates

    def _scan_jsts_exports_and_imports(
        self, jsts_files: list[str], root_dir: str
    ) -> list[dict[str, Any]]:
        """Scans JS/TS files for exports that are never imported in other files."""
        if not jsts_files:
            return []

        file_contents: dict[str, str] = {}
        for rel_path in jsts_files:
            abs_path = Path(root_dir) / rel_path
            if abs_path.is_file():
                try:
                    file_contents[rel_path] = abs_path.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    pass

        # Collect exports per file
        # Regex match: export (const|function|class|type|interface) <name>
        export_pattern = re.compile(
            r"export\s+(?:async\s+)?(?:const|function|class|type|interface|enum|let|var)\s+([A-Za-z0-9_$]+)"
        )

        all_imports_corpus = "\n".join(file_contents.values())

        candidates: list[dict[str, Any]] = []

        for rel_path, content in file_contents.items():
            # Skip page entrypoints (Next.js/React Router page.tsx, index.ts, main.ts, vite.config.ts)
            fname = os_path_basename(rel_path).lower()
            if fname in ("page.tsx", "page.jsx", "index.ts", "index.tsx", "main.ts", "main.tsx", "vite.config.ts", "next.config.js"):
                continue

            matches = export_pattern.findall(content)
            for symbol_name in matches:
                # Check if symbol is referenced anywhere outside its file
                # Search for import { symbol_name } or usage
                usage_pattern = r"\b" + re.escape(symbol_name) + r"\b"
                matches_count = len(re.findall(usage_pattern, all_imports_corpus))
                # Symbol is declared in current file, so count = 1 means it's only in current file
                if matches_count <= 1 and not symbol_name.startswith("use"):
                    candidates.append(
                        {
                            "path": rel_path,
                            "name": symbol_name,
                            "typ": "export",
                            "line": 1,
                            "confidence": 75,
                        }
                    )

        return candidates


def os_path_basename(path: str) -> str:
    """Helper basename function for path string."""
    return path.replace("\\", "/").split("/")[-1]
