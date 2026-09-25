"""Locked target folder style for structure audits.

Preferred product layout: two major roots (backend/, frontend/) with
Main Folder → Feature → Action → Files nesting.
"""

from __future__ import annotations

STRUCTURE_STYLE_ACTION_API = "action_api"
STRUCTURE_STYLE_CONSERVATIVE = "conservative"
DEFAULT_STRUCTURE_STYLE = STRUCTURE_STYLE_ACTION_API

PRODUCT_ROOTS = frozenset({"backend", "frontend"})

# Config / tooling filenames that belong at the product-root level
# (frontend/.env.example, backend/.gitignore, …) — never under a feature folder.
PRODUCT_ROOT_CONFIG_FILES = frozenset(
    {
        ".env",
        ".env.example",
        ".env.local",
        ".env.development",
        ".env.production",
        ".gitignore",
        ".dockerignore",
        ".npmrc",
        ".nvmrc",
        ".python-version",
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "tsconfig.json",
        "tsconfig.app.json",
        "tsconfig.node.json",
        "jsconfig.json",
        "vite.config.ts",
        "vite.config.js",
        "next.config.js",
        "next.config.mjs",
        "Dockerfile",
        "docker-compose.yml",
        "railway.toml",
        "vercel.json",
        "pyproject.toml",
        "requirements.txt",
        "Pipfile",
        "poetry.lock",
        "index.html",
    }
)

# Top-level folders that MAY be folded into backend/ or frontend/ in the target.
CONSOLIDATABLE_ROOTS = frozenset(
    {
        "docs",
        "doc",
        "scripts",
        "script",
        "tools",
        "tooling",
        "templates-src",
        "templates_src",
        "template-sources",
        "template-pipeline",
        "templates",
        "assets",
        "examples",
        "example",
        "samples",
        "notebooks",
        "data",
        "ops",
        "infra",
        "infrastructure",
        "deploy",
        "deployment",
        "ci",
        "shared",
        "packages",
        "libs",
        "lib",
        "common",
        "config",
        "configs",
    }
)

ACTION_API_STYLE_RULES = """
Target style: action_api (Main Folder → Feature → Action → Files)

FAIL if you only reprint the current tree. You must REORGANIZE.

1. Prefer exactly two product roots: backend/ and frontend/.
2. Fold consolidatable roots (docs, scripts, templates-src, …) under those two —
   they must NOT remain top-level siblings of backend/frontend in the proposed tree.
3. Hierarchy MUST be feature-first, action-second — NOT by technical type.
   Forbidden primary buckets: components/, services/, controllers/, utils/, hooks/, lib/, blocks/.
4. Backend source: backend/src/FEATURE/ACTION/ with that action's files only.
5. Frontend source: frontend/src/FEATURE/ACTION/ (or reuse frontend/src/features/FEATURE/ACTION/).
   Having frontend features/ without regrouping backend is NOT enough — both sides must match.
6. Shared/global code that spans many features may live under shared/lib/, shared/ui/, shared/api/ only.
7. Use a CLOSED catalog of ~8–12 product features (nouns users care about). Merge synonyms:
   auth NOT authentication; proposals NOT proposal + proposal_creator + thank; templates NOT
   highridgev4 + ink_copper_exact_css as separate top-level domains.
8. Actions MUST be real verbs (create, login, export, preview, provision, track, …) or known
   sub-features under a catalog feature (templates/ink_copper). NEVER invent folders by
   chopping camelCase (ThankYouPage → thank/you is WRONG; use proposals/public).
9. Do not encode file type in folder names (*_css, *_json). Keep .css next to the component.
10. Per-product config (MANDATORY):
   - frontend/ MUST keep its own .env.example and .gitignore (and similar tooling files).
   - backend/ MUST keep its own .env.example and .gitignore (and similar tooling files).
   - Do NOT bury .env.example / .gitignore / package.json / Dockerfile under a feature folder.
11. You may move files between folders. You must NEVER change file contents, imports, or code.
12. Reuse existing suitable feature/action folders — do not create duplicates (one folder per feature).
13. Always include concrete folder_changes (from_path → to_path → reason) for every regrouped file.
14. Aim for backend/frontend feature symmetry — same product nouns on both sides when both exist.
""".strip()

GOLDEN_ACTION_API_EXAMPLE = """
```text
repository/
├── backend/
│   ├── .env.example
│   ├── .gitignore
│   ├── package.json
│   └── src/
│       ├── auth/
│       │   ├── login/
│       │   │   ├── login.route.ts
│       │   │   ├── login.service.ts
│       │   │   └── login.schema.ts
│       │   └── signup/
│       │       ├── signup.route.ts
│       │       └── signup.service.ts
│       └── shared/
│           └── db/
│               └── client.ts
└── frontend/
    ├── .env.example
    ├── .gitignore
    ├── package.json
    └── src/
        ├── auth/
        │   ├── login/
        │   │   ├── LoginPage.tsx
        │   │   ├── LoginForm.tsx
        │   │   └── login.api.ts
        │   └── signup/
        │       ├── SignupPage.tsx
        │       └── signup.api.ts
        └── shared/
            └── lib/
                └── relativeTime.ts
```
""".strip()


def style_prompt_block(style: str = DEFAULT_STRUCTURE_STYLE) -> str:
    """Human-readable style block for LLM prompts."""
    if style == STRUCTURE_STYLE_CONSERVATIVE:
        return (
            "Target style: conservative — keep current major roots, suggest minimal moves, "
            "do not force feature/action nesting. Still keep frontend/ and backend/ each with "
            "their own .env.example and .gitignore when those product roots exist."
        )
    return f"{ACTION_API_STYLE_RULES}\n\nGolden example:\n{GOLDEN_ACTION_API_EXAMPLE}"
