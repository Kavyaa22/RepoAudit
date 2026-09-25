import pytest
import tempfile
from pathlib import Path
from repoaudit.audit.dead_code_engine import DeadCodeEngine
from repoaudit.audit.dead_code_jsts import JSTSDeadCodeScanner
from repoaudit.audit.dead_code_python import PythonDeadCodeScanner
from repoaudit.audit.engine import AuditEngine
from repoaudit.indexing.models import FileInfo, ProjectContext


def test_python_dead_code_scanner(tmp_path):
    # Create sample Python file with an unused import and uncalled function
    py_content = """import os
import sys

def used_function():
    return sys.version

def dead_uncalled_function():
    return "never called"

used_function()
"""
    file_path = tmp_path / "sample.py"
    file_path.write_text(py_content, encoding="utf-8")

    scanner = PythonDeadCodeScanner()
    candidates = scanner.scan_project(["sample.py"], str(tmp_path))

    # Expect unused import 'os' and 'dead_uncalled_function'
    names = [c["name"] for c in candidates]
    assert "os" in names
    assert "dead_uncalled_function" in names


def test_jsts_dead_code_scanner(tmp_path):
    # Create sample package.json with an unused dependency
    pkg_json = """{
  "name": "demo",
  "dependencies": {
    "axios": "^1.0.0",
    "unused-package-xyz": "^2.0.0"
  }
}"""
    (tmp_path / "package.json").write_text(pkg_json, encoding="utf-8")

    # Create index.js that imports axios but not unused-package-xyz
    js_code = """import axios from 'axios';
console.log(axios);
"""
    (tmp_path / "index.js").write_text(js_code, encoding="utf-8")

    scanner = JSTSDeadCodeScanner()
    candidates = scanner.scan_project(["package.json", "index.js"], str(tmp_path))

    deps = [c["name"] for c in candidates if c["typ"] == "dependency"]
    assert "unused-package-xyz" in deps
    assert "axios" not in deps


def test_dead_code_engine_framework_immunity(tmp_path):
    # Create FastAPI file where endpoint is decorated with @router
    py_code = """from fastapi import APIRouter
router = APIRouter()

@router.get("/health")
def health_check():
    return {"status": "ok"}
"""
    (tmp_path / "router.py").write_text(py_code, encoding="utf-8")

    files = [FileInfo(path="router.py", size=len(py_code))]
    project = ProjectContext(name="FastAPIApp", root=str(tmp_path), files=files)

    engine = DeadCodeEngine()
    result = engine.run_audit(project)

    # Endpoint decorated with @router must NOT be flagged as High confidence dead code
    health_findings = [f for f in result.findings if f.symbol_name == "health_check"]
    assert len(health_findings) == 0


def test_audit_engine_integration(tmp_path):
    py_code = """import unused_math_lib

def dead_calc():
    return 42
"""
    (tmp_path / "calc.py").write_text(py_code, encoding="utf-8")

    files = [FileInfo(path="calc.py", size=len(py_code))]
    project = ProjectContext(name="IntegrationApp", root=str(tmp_path), files=files)

    engine = AuditEngine()
    result = engine.run_dead_code_audit(project)

    assert result.total_findings >= 1
    assert result.health_score < 100


def test_empty_folder_detection(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "active.py").write_text("print('hello')", encoding="utf-8")

    empty_dir = tmp_path / "empty_dir"
    empty_dir.mkdir()

    nested_sub = tmp_path / "nested_empty" / "sub_empty"
    nested_sub.mkdir(parents=True)

    files = [FileInfo(path="src/active.py", size=14)]
    project = ProjectContext(name="EmptyDirApp", root=str(tmp_path), files=files)

    engine = DeadCodeEngine()
    result = engine.run_audit(project)

    empty_findings = [f for f in result.findings if f.category == "empty_folder"]
    empty_paths = [f.path for f in empty_findings]

    assert "empty_dir" in empty_paths
    assert "nested_empty/sub_empty" in empty_paths
    assert "nested_empty" in empty_paths
    assert "src" not in empty_paths
