"""prompt templates for repoaudit analysis pipeline."""

from __future__ import annotations

import json
import re


def _lang_instruction(language: str) -> str:
    lang_map = {
        "en": "Respond in English.",
        "zh": "请用中文回答。",
        "ja": "日本語で回答してください。",
        "ko": "한국어로 답변해주세요.",
    }
    return lang_map.get(language, "Respond in English.")


def _json_instruction() -> str:
    return (
        "Output ONLY valid JSON. No markdown fences, no explanation text before or after. "
        "Just the JSON object/array."
    )


def build_overview_prompt(file_tree: str, key_files: str, language: str = "en") -> list[dict]:
    return [
        {
            "role": "system",
            "content": (
                "You are a senior software engineer writing an onboarding overview for a new teammate. "
                "Be specific and concrete about what the system does, how it is organized, and how pieces connect. "
                "Do NOT use filler phrases like 'leveraging', 'utilizing', 'cutting-edge', "
                "'robust', or 'comprehensive'. Prefer concrete nouns (APIs, folders, workflows). "
                f"{_lang_instruction(language)}"
            ),
        },
        {
            "role": "user",
            "content": (
                f"Here is the file tree and key files of a project:\n\n"
                f"## File Tree\n```\n{file_tree}\n```\n\n"
                f"## Key Files\n{key_files}\n\n"
                f"Generate a project overview as JSON with this structure:\n"
                "{\n"
                '  "name": "project name",\n'
                '  "one_liner": "what this project does in one sentence (max 25 words)",\n'
                '  "description": "4-6 detailed paragraphs in plain language covering: (1) product purpose and users, (2) major subsystems and how they interact, (3) backend vs frontend (or other) responsibilities, (4) important workflows such as audit/import/scan if present, (5) notable tech choices and repo organization",\n'
                '  "tech_stack": [{"name": "Python", "category": "language", "version": "3.10+"}],\n'
                '  "setup_instructions": ["step 1", "step 2", "step 3"],\n'
                '  "key_features": ["feature 1", "feature 2", "feature 3", "feature 4"]\n'
                "}\n\n"
                "Write enough detail that a new engineer understands the repo without opening every file. "
                f"{_json_instruction()}"
            ),
        },
    ]


def build_module_prompt(
    module_name: str,
    files_context: str,
    project_summary: str,
    language: str = "en",
) -> list[dict]:
    return [
        {
            "role": "system",
            "content": (
                "You are a Principal Software Auditor and Technical Lead conducting an architecture domain review. "
                "Write with clarity for both non-technical stakeholders and technical auditors. "
                "Explain the business purpose of the domain, what capabilities it provides, "
                "how its files interact, and highlight key functions/classes simply without unnecessary jargon. "
                f"{_lang_instruction(language)}"
            ),
        },
        {
            "role": "user",
            "content": (
                f"Project Context: {project_summary}\n\n"
                f"Document the Architecture Domain: '{module_name}'. Here are representative files:\n\n"
                f"{files_context}\n\n"
                "Output JSON with this exact schema:\n"
                "{\n"
                f'  "name": "{module_name}",\n'
                '  "purpose": "One crisp sentence explaining the business/technical purpose of this domain",\n'
                '  "description": "Executive breakdown (2-3 paragraphs: what this domain executes, why it matters, and how it fits into the overall application)",\n'
                '  "files": [\n'
                '    {"path": "file.py", "purpose": "Clear explanation of file responsibility", '
                '"key_symbols": [{"name": "SymbolName", "kind": "function/class", "description": "What it accomplishes"}]}\n'
                '  ],\n'
                '  "relationships": [{"source": "source.py", "target": "target.py", "description": "How and why they communicate"}],\n'
                '  "key_concepts": [{"name": "Concept / Workflow", "explanation": "Plain explanation of pattern or business flow"}]\n'
                "}\n\n"
                f"{_json_instruction()}"
            ),
        },
    ]


def build_architecture_prompt(
    file_tree: str,
    key_files: str,
    language: str = "en",
) -> list[dict]:
    return [
        {
            "role": "system",
            "content": (
                "You are a Principal Software Architect conducting a comprehensive codebase architecture review. "
                "Identify the structural architectural patterns, component boundaries, data flow paths, and structural strengths/weaknesses. "
                "Provide detailed, specific architectural insights rather than high-level generalities. "
                "Ensure valid Mermaid diagram syntax with alphanumeric node IDs and clean labels. "
                f"{_lang_instruction(language)}"
            ),
        },
        {
            "role": "user",
            "content": (
                f"## File Tree\n```\n{file_tree}\n```\n\n"
                f"## Key Files\n{key_files}\n\n"
                "Perform a thorough architectural evaluation and return JSON with this precise structure:\n"
                "{\n"
                '  "architecture_type": "Primary Pattern (e.g., Layered Architecture, Client-Server SPA + REST API, Modular Monolith, Event-Driven, Microservices, CLI Engine)",\n'
                '  "description": "Architectural overview (1-2 paragraphs: design, domain separation, responsibilities)",\n'
                '  "components": [\n'
                '    {"name": "Subsystem / Layer Name", "purpose": "Clear responsibility & domain role", "files": ["src/app/core.py", "..."]}\n'
                '  ],\n'
                '  "mermaid_component": "graph TD\\n  A[Client Layer] --> B[API Gateway / Router]\\n  B --> C[Business Logic Engine]\\n  C --> D[Data Store]",\n'
                '  "mermaid_sequence": "sequenceDiagram\\n  participant User\\n  participant Client\\n  participant API\\n  participant Engine\\n  User->>Client: Triggers Action\\n  Client->>API: Request\\n  API->>Engine: Process\\n  Engine-->>Client: Result",\n'
                '  "data_flow": "Detailed step-by-step data lifecycle explanation describing input ingestion, processing, transformation, caching, and persistence."\n'
                "}\n\n"
                "CRITICAL: Keep mermaid_component compact and valid. Use \\n for line breaks and simple alphanumeric node IDs. "
                "Do NOT include %%{init}%%, classDef, or style directives. Use plain node IDs only, no custom styling or theme overrides. "
                "If space is limited, omit mermaid_sequence rather than mermaid_component. "
                f"{_json_instruction()}"
            ),
        },
    ]


def build_reading_guide_prompt(
    rankings: str,
    module_summaries: str,
    language: str = "en",
) -> list[dict]:
    return [
        {
            "role": "system",
            "content": (
                "You are a mentor helping a developer understand a new codebase. "
                "Create a reading guide: which files to read, in what order, and why. "
                "Start from entry points and configuration, then core logic, then utilities. "
                "Each step should say WHAT to look for, not just WHICH files. "
                f"{_lang_instruction(language)}"
            ),
        },
        {
            "role": "user",
            "content": (
                f"## File Importance Rankings (by PageRank)\n{rankings}\n\n"
                f"## Module Summaries\n{module_summaries}\n\n"
                "Create a reading guide with 5-10 steps. Output JSON:\n"
                "{\n"
                '  "introduction": "brief intro on how to approach this codebase",\n'
                '  "steps": [\n'
                '    {"order": 1, "title": "step title", "files": ["file1.py", "file2.py"], '
                '"explanation": "what to look for and why", "time_estimate": "5 min"}\n'
                '  ],\n'
                '  "tips": ["general tip 1", "general tip 2"]\n'
                "}\n\n"
                f"{_json_instruction()}"
            ),
        },
    ]


def build_chat_prompt(
    question: str,
    context_chunks: str,
    language: str = "en",
) -> list[dict]:
    # Detect if user is asking for root cause analysis / troubleshooting a broken feature
    lower_q = question.lower()
    is_root_cause_investigation = any(
        kw in lower_q
        for kw in [
            "error",
            "not working",
            "working well but now",
            "broken",
            "failed",
            "exception",
            "bug",
            "root cause",
            "issue",
            "why is",
            "fix",
            "traceback",
        ]
    )

    if is_root_cause_investigation:
        system_instruction = (
            "You are a Senior Principal Engineer performing a Root Cause Analysis & Debugging Investigation on a codebase. "
            "The user is reporting an issue where a feature was working or is now throwing an error / failing. "
            "Analyze the provided code context from the feature/action modules carefully to:\n"
            "1. Identify the EXACT ROOT CAUSE explaining why this error or issue is occurring.\n"
            "2. Identify the specific file, folder (e.g. src/app/services/<feature_name>/<action_name>/...), function, or line of code where the logic breaks.\n"
            "3. Provide step-by-step concrete SOLUTIONS and COMPLETE REFACTORED CODE BLOCKS to fix the issue.\n"
            "Be precise, reference exact file paths and line ranges, and provide ready-to-use code fixes. "
            f"{_lang_instruction(language)}"
        )
    else:
        system_instruction = (
            "You are a knowledgeable developer answering questions about a codebase. "
            "Answer based on the actual code shown below, not general knowledge. "
            "Reference specific files and line numbers when relevant. "
            "Be direct -- answer the question, don't give a lecture. "
            f"{_lang_instruction(language)}"
        )

    return [
        {
            "role": "system",
            "content": system_instruction,
        },
        {
            "role": "user",
            "content": (
                f"## Relevant Code Chunks (Feature / Action Modules)\n{context_chunks}\n\n"
                f"## User Problem / Question\n{question}"
            ),
        },
    ]



def extract_json(text: str) -> dict | list | None:
    """extract JSON from LLM output, handling markdown fences and extra text."""
    # strip markdown code fences
    text = re.sub(r"^```(?:json)?\s*\n?", "", text.strip(), flags=re.MULTILINE)
    text = re.sub(r"\n?```\s*$", "", text.strip(), flags=re.MULTILINE)

    # try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # find the first { or [ and match to the last } or ]
    for start_char, end_char in [("{", "}"), ("[", "]")]:
        start = text.find(start_char)
        if start == -1:
            continue
        end = text.rfind(end_char)
        if end == -1 or end <= start:
            continue
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            continue

    return None


def salvage_architecture_partial(text: str) -> dict:
    """Pull architecture string fields from truncated LLM JSON.

    Used when extract_json fails so mermaid_component is not silently dropped.
    """
    if not text:
        return {}
    out: dict = {}
    keys = (
        "architecture_type",
        "description",
        "mermaid_component",
        "mermaid_sequence",
        "data_flow",
    )
    for key in keys:
        match = re.search(
            rf'"{key}"\s*:\s*"((?:\\.|[^"\\])*)"',
            text,
        )
        if not match:
            continue
        try:
            out[key] = json.loads(f'"{match.group(1)}"')
        except json.JSONDecodeError:
            out[key] = match.group(1).replace("\\n", "\n").replace('\\"', '"')
    return out
