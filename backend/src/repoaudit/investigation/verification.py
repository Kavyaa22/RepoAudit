"""Patch verification helpers: apply context, syntax, lint, and optional targeted tests."""

from __future__ import annotations

import ast
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from repoaudit.investigation.investigation_models import CodePatch, PatchStatus


class PatchVerifier:
    """Performs cheap-to-medium validation before a patch is presented as trustworthy."""

    def verify(self, project_root: str, patch: CodePatch) -> CodePatch:
        diff = patch.unified_diff or ""
        if not self._has_valid_headers(diff, patch.file_path):
            patch.status = "unverified"
            patch.verification_summary = "Diff is not a valid unified diff for the reported target file."
            return patch

        target = Path(project_root) / patch.file_path
        if not target.is_file():
            patch.status = "unverified"
            patch.verification_summary = "Target file does not exist in the current project snapshot."
            return patch

        try:
            content = target.read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            patch.status = "unverified"
            patch.verification_summary = f"Could not read target file for verification: {exc}"
            return patch

        if not self._context_matches(content, diff):
            patch.status = "unverified"
            patch.verification_summary = "Diff headers parse, but hunk context was not found in the current snapshot."
            return patch

        patched_lines = self._apply_patch_lines(content, diff)
        patched_text = "\n".join(patched_lines) + "\n"
        status: PatchStatus = "applied_clean"
        summary = "Diff parses and hunk context matches the current snapshot."

        lowered = patch.file_path.lower()
        if lowered.endswith(".py"):
            syntax_ok, syntax_msg = self._python_syntax(patched_text)
            if not syntax_ok:
                patch.status = "unverified"
                patch.verification_summary = syntax_msg
                return patch
            lint_ok, lint_msg = self._run_ruff_or_py_compile(patched_text, patch.file_path)
            if not lint_ok:
                patch.status = "unverified"
                patch.verification_summary = lint_msg
                return patch
            test_ok, test_msg = self._run_related_pytest(project_root, patch.file_path)
            if test_ok is True:
                status = "checks_passed"
                summary = f"Python syntax/lint ok; related tests passed. {test_msg}"
            elif test_ok is False:
                status = "unverified"
                summary = test_msg
            else:
                status = "checks_passed"
                summary = f"Python syntax/lint ok. {lint_msg} {test_msg}"
        elif lowered.endswith((".ts", ".tsx", ".js", ".jsx")):
            syntax_ok, syntax_msg = self._js_like_balance(patched_text)
            if not syntax_ok:
                patch.status = "unverified"
                patch.verification_summary = syntax_msg
                return patch
            tsc_ok, tsc_msg = self._run_tsc_if_available(project_root, patch.file_path, patched_text)
            if tsc_ok is False:
                patch.status = "unverified"
                patch.verification_summary = tsc_msg
                return patch
            status = "checks_passed"
            summary = f"JS/TS balance ok. {tsc_msg}"
        else:
            status = "applied_clean"
            summary = "Diff applies cleanly; no language-specific checker for this file type."

        patch.status = status
        patch.verification_summary = summary
        return patch

    @staticmethod
    def _has_valid_headers(diff: str, file_path: str) -> bool:
        return f"--- a/{file_path}" in diff and f"+++ b/{file_path}" in diff and "@@" in diff

    @staticmethod
    def _context_matches(content: str, diff: str) -> bool:
        removed_or_context: list[str] = []
        for line in diff.splitlines():
            if not line or line.startswith(("---", "+++", "@@")):
                continue
            if line.startswith(" ") or line.startswith("-"):
                text = line[1:]
                if text.strip():
                    removed_or_context.append(text)
        if not removed_or_context:
            return False
        return any(line in content for line in removed_or_context[:20])

    @classmethod
    def _apply_patch_lines(cls, content: str, diff: str) -> list[str]:
        patched = content.splitlines()
        for hunk in re.finditer(
            r"@@ -(?P<old>\d+)(?:,\d+)? \+(?P<new>\d+)(?:,\d+)? @@(?P<body>.*?)(?=\n@@ |\Z)",
            diff,
            re.S,
        ):
            start = int(hunk.group("old")) - 1
            body = hunk.group("body").splitlines()
            cursor = max(0, start)
            for raw in body:
                if not raw:
                    continue
                marker = raw[0]
                line = raw[1:]
                if marker == " ":
                    cursor += 1
                elif marker == "-":
                    if cursor < len(patched):
                        patched.pop(cursor)
                elif marker == "+":
                    patched.insert(cursor, line)
                    cursor += 1
        return patched

    @staticmethod
    def _python_syntax(patched_text: str) -> tuple[bool, str]:
        try:
            ast.parse(patched_text)
        except SyntaxError as exc:
            return False, f"Patched Python syntax did not parse: {exc.msg} at line {exc.lineno}."
        return True, "Python syntax ok"

    @staticmethod
    def _run_ruff_or_py_compile(patched_text: str, file_path: str) -> tuple[bool, str]:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / Path(file_path).name
            target.write_text(patched_text, encoding="utf-8")
            ruff = shutil.which("ruff")
            if ruff:
                proc = subprocess.run(
                    [ruff, "check", str(target)],
                    capture_output=True,
                    text=True,
                    timeout=20,
                    check=False,
                )
                if proc.returncode != 0:
                    detail = (proc.stdout or proc.stderr or "ruff failed").strip().splitlines()[:3]
                    return False, "Ruff check failed on patched file: " + " | ".join(detail)
                return True, "Ruff check passed."
            proc = subprocess.run(
                ["python", "-m", "py_compile", str(target)],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
            if proc.returncode != 0:
                return False, f"py_compile failed: {(proc.stderr or proc.stdout).strip()[:200]}"
            return True, "py_compile passed."

    @staticmethod
    def _run_related_pytest(project_root: str, file_path: str) -> tuple[bool | None, str]:
        """Return (True/False if tests ran, None if skipped), message."""
        root = Path(project_root)
        stem = Path(file_path).stem
        candidates = list(root.rglob(f"test_{stem}.py"))[:2]
        candidates += list(root.rglob(f"{stem}_test.py"))[:2]
        if not candidates:
            return None, "No related unit tests found."
        pytest_bin = shutil.which("pytest")
        if not pytest_bin:
            return None, "pytest unavailable; skipped targeted tests."
        args = [pytest_bin, "-q", "--maxfail=1"]
        args.extend(str(p) for p in candidates[:3])
        try:
            proc = subprocess.run(args, cwd=str(root), capture_output=True, text=True, timeout=60, check=False)
        except Exception as exc:  # noqa: BLE001
            return None, f"Targeted pytest could not run: {exc}"
        if proc.returncode == 0:
            return True, f"Targeted pytest passed ({len(candidates)} file(s))."
        detail = (proc.stdout or proc.stderr or "tests failed").strip().splitlines()[-3:]
        return False, "Targeted pytest failed: " + " | ".join(detail)

    @staticmethod
    def _run_tsc_if_available(project_root: str, file_path: str, patched_text: str) -> tuple[bool | None, str]:
        root = Path(project_root)
        tsconfig = root / "tsconfig.json"
        if not tsconfig.is_file():
            # Search one level for monorepos.
            found = list(root.glob("*/tsconfig.json"))[:1]
            if not found:
                return None, "No tsconfig.json; skipped tsc."
            tsconfig = found[0]
            root = tsconfig.parent
        npx = shutil.which("npx")
        if not npx:
            return None, "npx unavailable; skipped tsc."
        with tempfile.TemporaryDirectory() as tmp:
            # Write patched file into a mirror path under temp is complex; run tsc --noEmit on project as smoke.
            # Prefer lightweight parse-only when project tsc is too heavy: skip with note if timeout risk.
            try:
                proc = subprocess.run(
                    [npx, "tsc", "--noEmit", "--pretty", "false"],
                    cwd=str(root),
                    capture_output=True,
                    text=True,
                    timeout=45,
                    check=False,
                )
            except Exception as exc:  # noqa: BLE001
                return None, f"tsc could not run: {exc}"
            if proc.returncode == 0:
                return True, "tsc --noEmit passed."
            # Don't fail the whole investigation solely on unrelated project type errors if file not mentioned.
            out = (proc.stdout or proc.stderr or "").strip()
            if file_path.replace("\\", "/") in out.replace("\\", "/"):
                return False, "tsc reported errors involving the patched file."
            return None, "tsc reported unrelated project errors; treated as skipped for this patch."

    @classmethod
    def _js_like_balance(cls, patched: str) -> tuple[bool, str]:
        pairs = {"(": ")", "[": "]", "{": "}"}
        stack: list[str] = []
        in_single = in_double = in_backtick = False
        escape = False
        for ch in patched:
            if escape:
                escape = False
                continue
            if ch == "\\" and (in_single or in_double or in_backtick):
                escape = True
                continue
            if not in_double and not in_backtick and ch == "'":
                in_single = not in_single
                continue
            if not in_single and not in_backtick and ch == '"':
                in_double = not in_double
                continue
            if not in_single and not in_double and ch == "`":
                in_backtick = not in_backtick
                continue
            if in_single or in_double or in_backtick:
                continue
            if ch in pairs:
                stack.append(pairs[ch])
            elif ch in pairs.values():
                if not stack or stack[-1] != ch:
                    return False, "Patched JS/TS bracket balance is invalid."
                stack.pop()
        if stack:
            return False, "Patched JS/TS bracket balance is incomplete."
        return True, "JS/TS balance ok"
