"""Keyword extraction and domain synonym expansion for issue investigation."""

from __future__ import annotations

import re

# Words stripped from automatic feature extraction.
STOPWORDS = frozenset({
    "the", "and", "this", "that", "with", "from", "when", "error", "issue", "bug",
    "not", "working", "fails", "fail", "failed", "after", "before", "into", "between",
    "well", "very", "also", "just", "only", "then", "than", "have", "has", "had",
    "was", "were", "are", "been", "being", "does", "did", "doing", "would", "could",
    "should", "about", "what", "which", "where", "while", "during", "generated",
    "whole", "entire", "some", "any", "all", "for", "but", "now", "still",
})

# Expand user terms to related search tokens used in typical codebases.
SYNONYMS: dict[str, list[str]] = {
    "mom": ["mom", "meeting", "meetings", "minutes", "workflow"],
    "transcript": ["transcript", "transcripts", "transcription", "excerpt"],
    "redirect": ["redirect", "navigation", "navigate", "scroll", "routing", "route"],
    "navigation": ["navigation", "navigate", "scroll", "redirect", "routing"],
    "scroll": ["scroll", "scrollinto", "navigation", "highlight"],
    "click": ["click", "onclick", "handler", "pointer"],
    "highlight": ["highlight", "coverage", "mapped", "green"],
    "login": ["login", "auth", "authentication", "signin"],
    "auth": ["auth", "authentication", "login", "session"],
    "payment": ["payment", "checkout", "billing", "stripe"],
    "dashboard": ["dashboard", "overview", "home"],
}


def extract_search_terms(
    issue_description: str,
    error_log: str = "",
    feature_name: str = "",
    action_name: str = "",
) -> list[str]:
    """Collect normalized search terms from report fields with synonym expansion."""
    raw_tokens: list[str] = []

    for source in (feature_name, action_name, issue_description, error_log):
        if not source:
            continue
        raw_tokens.extend(re.findall(r"\b[a-zA-Z]{3,}\b", source.lower()))

    terms: list[str] = []
    seen: set[str] = set()

    def add(term: str) -> None:
        t = term.lower().strip()
        if not t or t in STOPWORDS or t in seen:
            return
        seen.add(t)
        terms.append(t)

    for token in raw_tokens:
        add(token)
        for synonym in SYNONYMS.get(token, []):
            add(synonym)

    return terms


def primary_feature_action(
    issue_description: str,
    feature_name: str = "",
    action_name: str = "",
) -> tuple[str, str]:
    """Pick primary feature/action labels for path heuristics."""
    feature = (feature_name or "").strip().lower()
    action = (action_name or "").strip().lower()

    if feature:
        return feature, action

    terms = extract_search_terms(issue_description)
    if not terms:
        return "", ""

    feature = terms[0]
    action = terms[1] if len(terms) > 1 else ""
    return feature, action


def build_retrieval_query(report_description: str, error_log: str, feature_name: str, action_name: str) -> str:
    """Build a single query string for TF-IDF retrieval."""
    terms = extract_search_terms(report_description, error_log, feature_name, action_name)
    parts = [report_description.strip()]
    if error_log.strip():
        parts.append(error_log.strip())
    if terms:
        parts.append(" ".join(terms))
    if feature_name.strip():
        parts.append(feature_name.strip())
    if action_name.strip():
        parts.append(action_name.strip())
    return " ".join(parts)
