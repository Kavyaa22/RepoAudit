"""One-time migration script: RepoWiki -> RepoAudit layout."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OLD = ROOT / "RepoWiki"
NEW = ROOT / "RepoAudit"
SRC = OLD / "src" / "repowiki"

MOVES = {
    "config.py": "platform/config.py",
    "cli.py": "interfaces/cli/cli.py",
    "__init__.py": "__init__.py",
    "__main__.py": "__main__.py",
    "core/scanner.py": "indexing/scanner/scanner.py",
    "core/analyzer.py": "indexing/analyzer/analyzer.py",
    "core/graph.py": "indexing/graph/graph.py",
    "core/wiki_builder.py": "indexing/wiki/builder.py",
    "core/cache.py": "indexing/cache/cache.py",
    "core/models.py": "indexing/models.py",
    "core/rag.py": "retrieval/lexical.py",
    "export/markdown.py": "indexing/wiki/export/markdown.py",
    "export/json_export.py": "indexing/wiki/export/json_export.py",
    "export/html.py": "indexing/wiki/export/html.py",
    "llm/client.py": "indexing/llm/client.py",
    "llm/prompts.py": "indexing/llm/prompts.py",
    "ingest/local.py": "ingestion/local.py",
    "ingest/github.py": "ingestion/github/client.py",
    "server/app.py": "main.py",
    "server/models.py": "interfaces/api/schemas.py",
    "server/routers/scan.py": "interfaces/api/routes/scan.py",
    "server/routers/wiki.py": "interfaces/api/routes/wiki.py",
    "server/routers/chat.py": "interfaces/api/routes/chat.py",
}

IMPORT_REPLACEMENTS = [
    ("from repowiki.server.routers", "from repoaudit.interfaces.api.routes"),
    ("from repowiki.server.models", "from repoaudit.interfaces.api.schemas"),
    ("from repowiki.server.app", "from repoaudit.main"),
    ("from repowiki.export.markdown", "from repoaudit.indexing.wiki.export.markdown"),
    ("from repowiki.export.json_export", "from repoaudit.indexing.wiki.export.json_export"),
    ("from repowiki.export.html", "from repoaudit.indexing.wiki.export.html"),
    ("from repowiki.ingest.github", "from repoaudit.ingestion.github.client"),
    ("from repowiki.ingest.local", "from repoaudit.ingestion.local"),
    ("from repowiki.llm.client", "from repoaudit.indexing.llm.client"),
    ("from repowiki.llm.prompts", "from repoaudit.indexing.llm.prompts"),
    ("from repowiki.core.wiki_builder", "from repoaudit.indexing.wiki.builder"),
    ("from repowiki.core.scanner", "from repoaudit.indexing.scanner.scanner"),
    ("from repowiki.core.analyzer", "from repoaudit.indexing.analyzer.analyzer"),
    ("from repowiki.core.graph", "from repoaudit.indexing.graph.graph"),
    ("from repowiki.core.cache", "from repoaudit.indexing.cache.cache"),
    ("from repowiki.core.models", "from repoaudit.indexing.models"),
    ("from repowiki.core.rag", "from repoaudit.retrieval.lexical"),
    ("from repowiki.config", "from repoaudit.platform.config"),
    ("from repowiki.cli", "from repoaudit.interfaces.cli.cli"),
    ("from repowiki import", "from repoaudit import"),
    ("repowiki.server.app:create_app", "repoaudit.main:create_app"),
    ("repowiki.cli:cli", "repoaudit.interfaces.cli.cli:cli"),
    ("pip install repowiki[web]", "pip install repoaudit[web]"),
    ("pip install repowiki", "pip install repoaudit"),
    ('prog_name="repowiki"', 'prog_name="repoaudit"'),
    ("RepoWiki", "RepoAudit"),
    ("repowiki", "repoaudit"),
    ("REPOWIKI_", "REPOAUDIT_"),
    (".repowikiignore", ".repoauditignore"),
    (".repowiki/", ".repoaudit/"),
    ('".repowiki"', '".repoaudit"'),
]


def transform(content: str) -> str:
    for old, new in IMPORT_REPLACEMENTS:
        content = content.replace(old, new)
    return content


def migrate_sources() -> None:
    pkg_root = NEW / "backend" / "src" / "repoaudit"
    if NEW.exists():
        shutil.rmtree(NEW)
    pkg_root.mkdir(parents=True)

    for src_rel, dst_rel in MOVES.items():
        src = SRC / src_rel
        dst = pkg_root / dst_rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(transform(src.read_text(encoding="utf-8")), encoding="utf-8")
        print(f"moved {src_rel} -> {dst_rel}")


if __name__ == "__main__":
    migrate_sources()
    print("Done migrating Python sources")
