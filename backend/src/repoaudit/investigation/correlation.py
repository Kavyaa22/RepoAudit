"""Correlate live runtime artifacts with likely code entrypoints."""

from __future__ import annotations

import re
from dataclasses import dataclass

from repoaudit.investigation.evidence import extract_routes, extract_stack_paths

_CORRELATION_ID_PATTERN = re.compile(
    r"(?i)\b(?:correlation[_-]?id|request[_-]?id|trace[_-]?id|x-request-id)\s*[:=]\s*([A-Za-z0-9\-_.]{6,})"
)
_STATUS_PATTERN = re.compile(r"\b(?:status(?:\s*code)?|HTTP)\s*[:=]?\s*([1-5]\d{2})\b", re.I)
_METHOD_URL_PATTERN = re.compile(
    r"\b(?P<method>GET|POST|PUT|PATCH|DELETE|OPTIONS)\s+(?P<url>/[A-Za-z0-9_./{}?=&:%-]+)",
    re.I,
)


@dataclass
class CorrelationLead:
    """A concrete runtime → code lead for diagnosis."""

    kind: str
    detail: str
    routes: list[str]
    stack_paths: list[str]
    correlation_ids: list[str]
    status_codes: list[str]


def extract_correlation_ids(text: str) -> list[str]:
    ids: list[str] = []
    for match in _CORRELATION_ID_PATTERN.finditer(text or ""):
        value = match.group(1).strip()
        if value and value not in ids:
            ids.append(value)
    return ids[:10]


def extract_status_codes(text: str) -> list[str]:
    codes: list[str] = []
    for match in _STATUS_PATTERN.finditer(text or ""):
        code = match.group(1)
        if code not in codes:
            codes.append(code)
    return codes[:10]


def build_correlation_leads(*texts: str) -> list[CorrelationLead]:
    """Derive deterministic leads from console/network/backend evidence."""
    combined = "\n".join(t for t in texts if t)
    if not combined.strip():
        return []

    routes = extract_routes(combined)
    stacks = extract_stack_paths(combined)
    corr_ids = extract_correlation_ids(combined)
    statuses = extract_status_codes(combined)
    leads: list[CorrelationLead] = []

    for match in _METHOD_URL_PATTERN.finditer(combined):
        method = match.group("method").upper()
        url = match.group("url").split("?")[0]
        status_hint = statuses[0] if statuses else "unknown"
        leads.append(
            CorrelationLead(
                kind="network_to_handler",
                detail=f"Failing {method} {url} (status {status_hint}) should map to a route/handler.",
                routes=[url],
                stack_paths=[],
                correlation_ids=corr_ids,
                status_codes=statuses,
            )
        )

    if stacks:
        leads.append(
            CorrelationLead(
                kind="console_to_component",
                detail=f"Console/stack paths point at {', '.join(stacks[:3])}.",
                routes=routes,
                stack_paths=stacks,
                correlation_ids=corr_ids,
                status_codes=statuses,
            )
        )

    if corr_ids and (routes or stacks):
        leads.append(
            CorrelationLead(
                kind="fe_be_join",
                detail=(
                    f"Join frontend failure with backend logs using correlation ID(s): {', '.join(corr_ids[:3])}."
                ),
                routes=routes,
                stack_paths=stacks,
                correlation_ids=corr_ids,
                status_codes=statuses,
            )
        )

    if not leads and (routes or stacks or statuses):
        leads.append(
            CorrelationLead(
                kind="runtime_signal",
                detail="Runtime evidence present but incomplete; prefer route/stack + correlation ID for certainty.",
                routes=routes,
                stack_paths=stacks,
                correlation_ids=corr_ids,
                status_codes=statuses,
            )
        )

    return leads[:6]


def correlation_summary(leads: list[CorrelationLead]) -> list[str]:
    return [lead.detail for lead in leads]
