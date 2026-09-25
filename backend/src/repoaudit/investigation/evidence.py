"""Evidence scoring, live-artifact redaction, and routing hints for investigations."""

from __future__ import annotations

import re

from repoaudit.investigation.investigation_models import EvidenceAssessment, IssueReport

_SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[A-Za-z0-9._\-]+"),
    re.compile(r"(?i)(api[_-]?key\s*[:=]\s*)[A-Za-z0-9._\-]+"),
    re.compile(r"(?i)(password\s*[:=]\s*)[^\s,;]+"),
    re.compile(r"(?i)(token\s*[:=]\s*)[A-Za-z0-9._\-]+"),
)
_EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_URL_PATTERN = re.compile(r"(?P<method>GET|POST|PUT|PATCH|DELETE|OPTIONS)?\s*(?P<url>/[A-Za-z0-9_./{}?=&:%-]+)", re.I)
_STACK_PATH_PATTERN = re.compile(r"[A-Za-z0-9_./\\-]+\.(?:tsx|ts|jsx|js|py|vue|go|rs)(?::\d+)?")
_EXCEPTION_PATTERN = re.compile(r"\b(?:[A-Z][A-Za-z]+Error|Exception|Traceback|Unhandled|TypeError|AttributeError)\b")
_VAGUE_DESCRIPTION = re.compile(
    r"^(it|this|something|the (?:app|code|feature|thing|project)).{0,28}"
    r"(broken|not working|doesn'?t work|fails|is failing|error)\.?$",
    re.I,
)
_SPECIFIC_MARKERS = (
    "when",
    "after",
    "instead",
    "click",
    "submit",
    "login",
    "checkout",
    "error",
    "fail",
    "page",
    "button",
    "returns",
    "shows",
    "never",
    "should",
    "expected",
    "dashboard",
    "payment",
    "timeout",
    "blank",
    "crash",
)


def redact_sensitive_text(text: str) -> str:
    """Remove common secrets and personal data before storing or prompting."""
    redacted = text or ""
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub(r"\1[REDACTED]", redacted)
    return _EMAIL_PATTERN.sub("[REDACTED_EMAIL]", redacted)


def sanitized_report(report: IssueReport) -> IssueReport:
    """Return a copy with sensitive fields redacted."""
    data = report.model_dump()
    for key in ("issue_description", "error_log", "expected_behavior", "actual_behavior", "environment"):
        data[key] = redact_sensitive_text(str(data.get(key) or ""))
    data["live_artifacts"] = [
        {"kind": artifact.kind, "content": redact_sensitive_text(artifact.content)}
        for artifact in report.live_artifacts
    ]
    return IssueReport(**data)


def extract_routes(text: str) -> list[str]:
    routes: list[str] = []
    for match in _URL_PATTERN.finditer(text or ""):
        raw_url = match.group("url")
        url = re.sub(r":\d+$", "", raw_url.split("?")[0]).rstrip("/") or "/"
        # Ignore filesystem-looking paths mistaken for routes (e.g. /src/app/foo.py).
        if re.search(r"\.(?:py|tsx|ts|jsx|js|vue|go|rs)$", url):
            continue
        if "/src/" in url or "/frontend/" in url or "/backend/" in url or url.endswith((".css", ".json", ".md")):
            continue
        looks_like_api = bool(match.group("method")) or any(
            seg in url.lower() for seg in ("/api", "/v1", "/v2", "/auth", "/billing", "/login", "/checkout", "/users")
        )
        if looks_like_api and url not in routes:
            routes.append(url)
    return routes[:10]



def extract_stack_paths(text: str) -> list[str]:
    paths: list[str] = []
    for raw in _STACK_PATH_PATTERN.findall(text or ""):
        cleaned = re.sub(r":\d+$", "", raw).replace("\\", "/").strip("/")
        if cleaned and cleaned not in paths:
            paths.append(cleaned)
    return paths[:20]


def assess_evidence(report: IssueReport) -> EvidenceAssessment:
    """Score the input before investigation and choose the workflow route."""
    score = 0
    signals: list[str] = []
    gaps: list[str] = []
    description = (report.issue_description or "").strip()
    combined = "\n".join(
        [
            description,
            report.error_log or "",
            report.expected_behavior or "",
            report.actual_behavior or "",
            "\n".join(a.content for a in report.live_artifacts),
        ]
    )

    def add(points: int, signal: str) -> None:
        nonlocal score
        score += points
        signals.append(signal)

    vague = bool(_VAGUE_DESCRIPTION.match(description))
    specific = any(marker in description.lower() for marker in _SPECIFIC_MARKERS)

    if vague or len(description) < 20:
        gaps.append("What did you click or submit, and what happened instead of what you expected?")
    else:
        add(12, "Issue description is specific enough to search the repository")
        if len(description) >= 40:
            add(14, "Issue description includes enough detail to retrieve likely files")
        if specific:
            add(16, "Description names a concrete action, screen, or failure")

    if report.feature_name.strip():
        add(15, f"Feature area provided: {report.feature_name.strip()}")

    if report.action_name.strip():
        add(10, f"Last action provided: {report.action_name.strip()}")

    if report.expected_behavior.strip() and report.actual_behavior.strip():
        add(10, "Expected and actual behavior are both present")

    if report.environment.strip() or report.branch.strip():
        add(8, "Environment or branch context is present")

    stack_paths = extract_stack_paths(combined)
    if stack_paths:
        add(24, f"Stack/file path evidence found: {', '.join(stack_paths[:3])}")

    routes = extract_routes(combined)
    if routes:
        add(16, f"Network/API route evidence found: {', '.join(routes[:3])}")

    if _EXCEPTION_PATTERN.search(combined):
        add(12, "Exception/error signature found in supplied evidence")

    if report.live_artifacts:
        add(15, f"Live runtime artifact(s) supplied: {len(report.live_artifacts)}")

    if report.error_log.strip() and len(report.error_log.strip()) > 30:
        add(18, "Console/backend log supplied")
    elif not vague and len(description) >= 40:
        gaps.append("A console error or failed request would make the diagnosis more certain — optional.")
    else:
        gaps.append("Paste the console error, stack trace, or failed request if you have one.")

    score = min(100, score)
    if score >= 70 or report.live_artifacts:
        tier = "D" if report.live_artifacts else "C"
        route = "full"
        guidance = "There is enough to search the code, name a likely cause, and suggest a fix."
    elif score >= 32:
        tier = "B"
        route = "locate"
        guidance = "The description is enough to search the repo. A log would confirm the file, but is not required."
    else:
        tier = "A"
        route = "clarify"
        guidance = "This is too vague to search the repository. Say which screen, what you did, and what went wrong."

    return EvidenceAssessment(score=score, tier=tier, route=route, signals=signals, gaps=gaps[:5], guidance=guidance)
