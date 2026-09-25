"""Multi-Signal Dead Code & Dependency Analysis Engine."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from repoaudit.audit.plain_language import dead_code_verdict

from repoaudit.indexing.scanner.scanner import IgnoreRules, _SKIP_DIRS
from repoaudit.audit.dead_code_jsts import JSTSDeadCodeScanner
from repoaudit.audit.dead_code_models import (
    ConfidenceLevel,
    DeadCodeAuditResult,
    DeadCodeCategory,
    DeadCodeFinding,
)
from repoaudit.audit.dead_code_python import PythonDeadCodeScanner

if TYPE_CHECKING:
    from repoaudit.indexing.models import ProjectContext

logger = logging.getLogger(__name__)

FRAMEWORK_DECORATOR_PATTERNS = {
    "@router",
    "@app",
    "@pytest",
    "@celery",
    "@task",
    "@event",
    "@receiver",
    "@validator",
    "@field_validator",
    "@classmethod",
    "@staticmethod",
    "@property",
    "@click",
}


class DeadCodeEngine:
    """Multi-Signal Reachability and Confidence Scorer Engine."""

    def __init__(self) -> None:
        self.py_scanner = PythonDeadCodeScanner()
        self.jsts_scanner = JSTSDeadCodeScanner()

    def run_audit(self, project: ProjectContext) -> DeadCodeAuditResult:
        """Executes multi-signal dead code and unused dependency analysis."""
        rel_paths = [f.path.replace("\\", "/") for f in project.files]

        # 1. Collect static candidates
        py_candidates = self.py_scanner.scan_project(rel_paths, project.root)
        jsts_candidates = self.jsts_scanner.scan_project(rel_paths, project.root)
        dir_candidates = self._scan_empty_directories(project.root)
        all_candidates = py_candidates + jsts_candidates + dir_candidates

        findings: list[DeadCodeFinding] = []
        counts: dict[str, int] = {
            "unused_import": 0,
            "dead_function": 0,
            "dead_class": 0,
            "orphan_file": 0,
            "unused_dependency": 0,
            "empty_folder": 0,
        }

        # Build combined corpus of test files for reference checking
        test_corpus = ""
        for f in project.files:
            p_lower = f.path.lower()
            if "test" in p_lower or "spec" in p_lower:
                abs_f = Path(project.root) / f.path
                if abs_f.is_file():
                    try:
                        test_corpus += "\n" + abs_f.read_text(encoding="utf-8", errors="ignore")
                    except Exception:
                        pass

        # 2. Multi-Signal Confidence Evaluation
        for cand in all_candidates:
            finding = self._evaluate_candidate(cand, project, test_corpus)
            if finding and finding.confidence_score >= 50:
                findings.append(finding)
                counts[finding.category] = counts.get(finding.category, 0) + 1

        # 3. Calculate Health Score
        high_count = sum(1 for f in findings if f.confidence_level == "HIGH")
        medium_count = sum(1 for f in findings if f.confidence_level == "MEDIUM")
        deduction = (high_count * 10) + (medium_count * 4)
        health_score = max(0, 100 - deduction)

        verdict = dead_code_verdict(len(findings), high_count)

        return DeadCodeAuditResult(
            total_findings=len(findings),
            health_score=health_score,
            summary_verdict=verdict,
            findings=findings,
            counts_by_category=counts,
        )

    def _scan_empty_directories(self, root_dir: str | Path) -> list[dict[str, Any]]:
        """Scans the project directory tree for empty folders and sub-folders."""
        root_path = Path(root_dir).resolve()
        if not root_path.is_dir():
            return []

        try:
            ignore_rules = IgnoreRules.from_root(root_path)
        except Exception:
            ignore_rules = IgnoreRules([])

        empty_candidates: list[dict[str, Any]] = []
        non_empty_dirs: set[Path] = set()

        for dirpath, dirnames, filenames in os.walk(root_path, topdown=False):
            current_dir = Path(dirpath)
            if current_dir == root_path:
                continue

            try:
                rel_posix = current_dir.relative_to(root_path).as_posix()
            except ValueError:
                continue

            dir_name = current_dir.name

            # Skip system / package manager / tooling folders
            if dir_name in _SKIP_DIRS or dir_name.endswith(".egg-info"):
                continue
            if ignore_rules.matches(rel_posix, is_dir=True):
                continue

            # Check for active (non-ignored) files in this directory
            has_files = False
            for fname in filenames:
                file_rel = f"{rel_posix}/{fname}"
                if not ignore_rules.matches(file_rel, is_dir=False):
                    has_files = True
                    break

            # Check if any child subdirectory was non-empty
            has_non_empty_subdir = False
            for dname in dirnames:
                child_path = current_dir / dname
                if child_path in non_empty_dirs:
                    has_non_empty_subdir = True
                    break

            if has_files or has_non_empty_subdir:
                non_empty_dirs.add(current_dir)
            else:
                empty_candidates.append({
                    "path": rel_posix,
                    "name": dir_name,
                    "typ": "empty_folder",
                    "confidence": 90,
                    "line": 1,
                })

        return empty_candidates

    def _evaluate_candidate(
        self,
        cand: dict[str, Any],
        project: ProjectContext,
        test_corpus: str,
    ) -> DeadCodeFinding | None:
        path = cand["path"]
        name = cand["name"]
        typ = cand.get("typ", "symbol")

        # Map candidate type to category
        category: DeadCodeCategory
        if typ == "dependency":
            category = "unused_dependency"
        elif typ == "empty_folder":
            category = "empty_folder"
        elif typ == "import":
            category = "unused_import"
        elif typ in ("function", "method"):
            category = "dead_function"
        elif typ == "class":
            category = "dead_class"
        else:
            category = "dead_function"

        if category == "empty_folder":
            score = 90
            level: ConfidenceLevel = "HIGH"
            signals = [f"Directory '{path}' contains no active files or sub-folders"]
            desc = f"Directory '{path}' is empty and contains no active code or files."
            sug = f"Remove empty directory '{path}' or add a '.gitkeep' file if it should be preserved."
            return DeadCodeFinding(
                path=path,
                symbol_name=name,
                category=category,
                confidence_level=level,
                confidence_score=score,
                signals_found=signals,
                description=desc,
                suggestion=sug,
            )

        signals: list[str] = [f"Static scanner detected unreferenced {typ} '{name}'"]
        # Start lower so tool confidence + signals can differentiate scores
        base_score = 25

        # Signal 1: Initial tool confidence (graduated, does not saturate for all)
        tool_conf = int(cand.get("confidence", 60))
        # Map 50..100 -> +10..+40
        base_score += max(10, min(40, (tool_conf - 40)))

        # Signal 2: Test suite reference check
        if name in test_corpus:
            base_score -= 35
            signals.append(f"Referenced in test suite ('{name}')")
        else:
            base_score += 12
            signals.append("No references found in test files")

        # Signal 3: Framework Decorators & Route Immunity Check
        abs_path = Path(project.root) / path
        if abs_path.is_file():
            try:
                content = abs_path.read_text(encoding="utf-8", errors="ignore")
                lines = content.splitlines()
                for idx, line in enumerate(lines):
                    if name in line:
                        context_window = lines[max(0, idx - 3) : idx + 1]
                        if any(any(pat in ctx for pat in FRAMEWORK_DECORATOR_PATTERNS) for ctx in context_window):
                            base_score -= 50
                            signals.append(f"Annotated with framework decorator in '{path}'")
                            break
            except Exception:
                pass

        # Category nuance so portions don't all look identical
        if category == "unused_dependency":
            base_score += 8
            signals.append("Dependency never imported across corpus")
        elif category == "unused_import":
            base_score += 5
        elif category == "dead_class":
            base_score += 3
        elif category == "dead_function":
            base_score += 0

        # Exclude entrypoint files (main.py, index.ts, router.py, page.tsx)
        filename_lower = path.split("/")[-1].lower()
        if filename_lower in ("main.py", "app.py", "run_dev.py", "setup.py", "page.tsx", "layout.tsx", "index.ts", "index.tsx", "vite.config.ts"):
            if category != "unused_dependency":
                return None

        # Clamp confidence score 0 to 100
        score = max(0, min(100, base_score))

        # Assign confidence level
        level: ConfidenceLevel
        if score >= 80:
            level = "HIGH"
        elif score >= 50:
            level = "MEDIUM"
        else:
            level = "LOW"
            return None  # Suppress low confidence items to prevent false positives

        # Formulate description and suggestion
        if category == "unused_dependency":
            desc = f"Package '{name}' is declared in '{path}' but is never imported across the codebase."
            sug = f"Remove '{name}' from '{path}' dependencies."
        elif category == "unused_import":
            desc = f"Import '{name}' in '{path}' (line {cand.get('line', 1)}) is never used in this file."
            sug = f"Safely delete unused import '{name}' from '{path}'."
        elif category == "dead_function":
            desc = f"Function '{name}' in '{path}' (line {cand.get('line', 1)}) has no callers."
            sug = f"Refactor or remove dead function '{name}'."
        elif category == "dead_class":
            desc = f"Class '{name}' in '{path}' (line {cand.get('line', 1)}) is never instantiated or inherited."
            sug = f"Refactor or remove dead class '{name}'."
        else:
            desc = f"Symbol '{name}' in '{path}' appears to be dead code."
            sug = f"Remove or document '{name}'."

        return DeadCodeFinding(
            path=path,
            symbol_name=name,
            category=category,
            confidence_level=level,
            confidence_score=score,
            signals_found=signals,
            description=desc,
            suggestion=sug,
        )
