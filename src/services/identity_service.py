"""Identity retrieval, and the disclosure gate that sits in front of generation.

`data/identity.yaml` carries two sections:

- `public` — who you are professionally: creds, summary, the project ledger,
  tone rules. Publicly checkable, and the only material outbound copy is built
  from.
- `private` — contact and negotiation detail: personal email, phone, current and
  expected compensation, notice period, exact location. Real, but nobody is
  owed it, and a recruiter's "share your details" list is not consent.

Three layers, and the gate is the middle one:

    retrieval (load_public / load_private)
        -> DISCLOSURE GATE (guard_disclosure)
            -> generation (render / draft / send)

`load_public` is free. `load_private` refuses without `allow_sensitive=True`,
and `guard_disclosure` re-checks the finished body on the way out, so a private
value that reached the text some other way (typed from memory, copied from a
transcript, invented by an LLM) is still caught at the Gmail boundary. Both
refusals carry `requires_confirmation` and a question to put to the user
verbatim, exactly like the template gate in `template_matcher.py`.

The gate holds on a checkout that has no `private` section at all: the value
scan is backed by pattern rules for the shapes of data that should never be
volunteered (phone numbers, CTC figures, notice periods, government IDs). It
fails closed.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

import yaml

from config.settings import IDENTITY_PATH
from services.template_matcher import normalize, static_segments


PUBLIC_SECTION = "public"
PRIVATE_SECTION = "private"

# Values shorter than this are too generic to attribute to the private section
# ("Pune", a two-digit number) and would fire on innocent copy.
MIN_SENSITIVE_VALUE = 6

# Shapes that must never be volunteered, checked even when the private section
# is absent or empty. Kept tight on purpose: a false block costs a round trip,
# but each pattern here is something no template legitimately contains.
_PATTERN_RULES: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        "phone_number",
        "a phone number",
        re.compile(r"(?<!\d)(?:\+\d{1,3}[\s.-]?)?(?:\d[\s.-]?){9,14}\d(?!\d)"),
    ),
    (
        "compensation",
        "a salary or CTC figure",
        re.compile(
            r"\b(?:current|expected)\s+ctc\b|\bctc\b|\b\d+(?:\.\d+)?\s*(?:lpa|lakhs?|lacs?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "notice_period",
        "a notice period",
        re.compile(r"\bnotice\s+period\b", re.IGNORECASE),
    ),
    (
        "government_id",
        "a government ID number",
        re.compile(r"\b(?:aadhaar|aadhar|passport\s*(?:no|number)|pan\s*(?:card|number)|ssn)\b", re.IGNORECASE),
    ),
    (
        "date_of_birth",
        "a date of birth",
        re.compile(r"\b(?:date\s+of\s+birth|d\.?o\.?b\.?)\b", re.IGNORECASE),
    ),
)

# Env-held secrets that are deliberately not in the YAML (AGENTS.md 12.2 keeps the
# phone number in .env so it reaches the resume PDF and nothing else), but that
# still must not slip into a body.
_ENV_SENSITIVE_KEYS = ("RESUME_PHONE",)


@dataclass
class Disclosure:
    """One piece of private data found in text bound for a recipient."""

    kind: str  # "value" (matched the private section) or "pattern"
    label: str  # human phrasing for the question, e.g. "a phone number"
    source: str  # dotted path in the private section, or the pattern name
    excerpt: str

    def as_dict(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "label": self.label,
            "source": self.source,
            "excerpt": self.excerpt,
        }


@dataclass
class IdentityDocument:
    path: Path
    public: dict[str, Any] = field(default_factory=dict)
    private: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


def _flatten(node: Any, prefix: str = "") -> Iterable[tuple[str, str]]:
    """Yield (dotted_path, scalar_as_text) for every leaf under `node`."""

    if isinstance(node, dict):
        for key, value in node.items():
            yield from _flatten(value, f"{prefix}.{key}" if prefix else str(key))
    elif isinstance(node, (list, tuple)):
        for index, value in enumerate(node):
            yield from _flatten(value, f"{prefix}[{index}]")
    elif node is not None and not isinstance(node, bool):
        text = str(node).strip()
        if text:
            yield prefix, text


class IdentityService:
    """Reads `data/identity.yaml`. Public is free; private is gated."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else IDENTITY_PATH

    # ----- retrieval -----------------------------------------------------

    def load(self) -> IdentityDocument:
        """Parse the file into its two sections, never raising.

        A missing or malformed file yields empty sections plus `error`. Callers
        that gate on the result must treat that as "assume sensitive", which is
        what `guard_disclosure` does via its pattern rules.
        """

        try:
            payload = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        except Exception as exc:  # noqa: BLE001 - degrade to empty, never raise
            return IdentityDocument(path=self.path, error=str(exc))

        if not isinstance(payload, dict):
            return IdentityDocument(
                path=self.path, error="identity.yaml did not parse to a mapping"
            )

        public = payload.get(PUBLIC_SECTION)
        private = payload.get(PRIVATE_SECTION)
        error = None
        if PUBLIC_SECTION not in payload:
            # Pre-split file: everything in it was written to be quotable, so
            # treat it as public rather than silently returning nothing.
            public = {k: v for k, v in payload.items() if k != PRIVATE_SECTION}
            error = (
                f"{self.path.name} has no '{PUBLIC_SECTION}:' section; treating the "
                "whole file as public. Split it (AGENTS.md 12.1)."
            )

        return IdentityDocument(
            path=self.path,
            public=public if isinstance(public, dict) else {},
            private=private if isinstance(private, dict) else {},
            error=error,
        )

    def load_public(self) -> dict[str, Any]:
        """Work history and proof of work. No gate: this is the outbound source."""

        return self.load().public

    def load_private(
        self, allow_sensitive: bool = False
    ) -> tuple[dict[str, object] | None, dict[str, Any]]:
        """Contact and negotiation detail, behind the gate.

        Returns `(None, data)` once approved. Otherwise the first element is the
        refusal to hand back verbatim, and the data is withheld — the field
        *names* are listed so the user knows what is being asked for, but no
        values are returned.
        """

        document = self.load()
        if allow_sensitive:
            return None, document.private

        available = sorted({path for path, _ in _flatten(document.private)})
        return (
            {
                "success": False,
                "requires_confirmation": True,
                "error": "Private identity fields were requested without approval.",
                "question": (
                    "This needs personal details that are not public "
                    f"({', '.join(available) or 'none recorded'}). Should we share them?"
                ),
                "fields": available,
                "message": (
                    "Retrieval blocked pending confirmation. Ask the user the question "
                    "above; only if they say yes, retry with allow_sensitive=True."
                ),
            },
            {},
        )

    # ----- the gate ------------------------------------------------------

    def sensitive_values(self) -> list[tuple[str, str]]:
        """(source, value) pairs the private section says must not leak."""

        pairs = [
            (source, value)
            for source, value in _flatten(self.load().private)
            if len(value) >= MIN_SENSITIVE_VALUE
        ]
        for key in _ENV_SENSITIVE_KEYS:
            value = (os.getenv(key) or "").strip()
            if len(value) >= MIN_SENSITIVE_VALUE:
                pairs.append((f"env.{key}", value))
        return pairs


def _template_allowlist(template: str | None) -> str:
    """Fixed wording of a template, normalized.

    Anything already written into a template has been read and approved once
    (a referral template may publish a contact address on purpose), so it is not
    a new disclosure. Only text outside the template's own wording is.
    """

    if not template:
        return ""
    try:
        from repositories.template_repository import TemplateRepository

        loaded = TemplateRepository().load(template)
    except Exception:  # noqa: BLE001 - no allowlist is the safe direction
        return ""
    return " ".join(static_segments(loaded.body_template))


def _digits(text: str) -> str:
    return re.sub(r"\D", "", text)


def guard_disclosure(
    body: str,
    subject: str = "",
    template: str | None = None,
    allow_sensitive: bool = False,
    service: IdentityService | None = None,
) -> tuple[dict[str, object] | None, list[Disclosure]]:
    """Gate recipient-bound text on personal-data disclosure.

    Returns `(None, findings)` when the write may proceed — `findings` is empty
    unless `allow_sensitive` waved something through, in which case it stays
    populated so an approved disclosure remains visible in the output.

    `allow_sensitive=True` is the override, and it is only legitimate after the
    user has answered the returned question (AGENTS.md 12.1).
    """

    active = service or IdentityService()
    haystack = normalize(f"{subject}\n{body}")
    allowed = _template_allowlist(template)
    findings: list[Disclosure] = []

    for source, value in active.sensitive_values():
        needle = normalize(value)
        if not needle or needle in allowed:
            continue
        hit = needle in haystack
        if not hit and len(_digits(value)) >= 7:
            # Phone numbers survive reformatting, so compare digits too.
            hit = _digits(value) in _digits(haystack)
        if hit:
            findings.append(
                Disclosure(
                    kind="value",
                    label=source.split(".")[-1].replace("_", " "),
                    source=source,
                    excerpt=value,
                )
            )

    for name, label, pattern in _PATTERN_RULES:
        for match in pattern.finditer(haystack):
            excerpt = match.group(0).strip()
            if not excerpt or normalize(excerpt) in allowed:
                continue
            if name == "phone_number" and len(_digits(excerpt)) < 10:
                continue
            findings.append(
                Disclosure(kind="pattern", label=label, source=name, excerpt=excerpt)
            )
            break  # one finding per rule is enough to ask the question

    if not findings or allow_sensitive:
        return None, findings

    labels = sorted({finding.label for finding in findings})
    payload: dict[str, object] = {
        "success": False,
        "requires_confirmation": True,
        "error": (
            "This body would disclose personal details that are not part of the "
            f"public identity: {', '.join(labels)}."
        ),
        "question": (
            f"This email would share {', '.join(labels)}, which is private. "
            "Should we still include it?"
        ),
        "disclosures": [finding.as_dict() for finding in findings],
        "message": (
            "Blocked pending confirmation. Ask the user the question above; only if "
            "they say yes, retry with allow_sensitive=True (CLI: --allow-sensitive)."
        ),
    }
    return payload, findings


def disclosures_as_dicts(findings: Sequence[Disclosure]) -> list[dict[str, str]]:
    return [finding.as_dict() for finding in findings]
