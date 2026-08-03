"""Template conformance check for outbound message bodies.

Purpose: make "did this email actually come from one of our templates?" a
software-enforced question instead of an agent-discipline one. `GmailService.
send_email` calls `guard_send` before touching the Gmail API, so a free-form
body composed outside `templates/` cannot be sent without an explicit override.

Matching is *recall of the template's static text*, not equality: a rendered
template body contains all of the template's fixed wording plus the variable
values, so we measure how much of the fixed wording survives in the candidate
body. That tolerates personalization while still catching a body that was
written from scratch.
"""

from __future__ import annotations

import html
import re
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from typing import Sequence

from config.settings import (
    TEMPLATE_MATCH_MIN_BLOCK,
    TEMPLATE_MATCH_THRESHOLD,
)
from models.email_template import EmailTemplate
from repositories.template_repository import TemplateRepository


_TAG_RE = re.compile(r"<[^>]+>")
_PLACEHOLDER_RE = re.compile(r"\{[A-Za-z_][A-Za-z0-9_]*\}")
_WS_RE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Strip HTML, entities and whitespace/case noise so wording can be compared."""

    without_tags = _TAG_RE.sub(" ", text or "")
    unescaped = html.unescape(without_tags)
    return _WS_RE.sub(" ", unescaped).strip().lower()


def static_segments(template_text: str) -> list[str]:
    """The fixed wording of a template: everything that is not a {placeholder}."""

    return [
        normalized
        for chunk in _PLACEHOLDER_RE.split(template_text or "")
        if (normalized := normalize(chunk))
    ]


@dataclass
class TemplateScore:
    template: str
    score: float
    matched_chars: int
    static_chars: int

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class MatchResult:
    matched: bool
    template: str | None
    score: float
    threshold: float
    ranking: list[TemplateScore] = field(default_factory=list)
    error: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "matched": self.matched,
            "template": self.template,
            "score": round(self.score, 4),
            "threshold": self.threshold,
            "ranking": [
                {**item.as_dict(), "score": round(item.score, 4)} for item in self.ranking[:5]
            ],
            "error": self.error,
        }


class TemplateMatcher:
    def __init__(
        self,
        repository: TemplateRepository | None = None,
        threshold: float | None = None,
        min_block: int | None = None,
    ) -> None:
        self.repository = repository or TemplateRepository()
        self.threshold = TEMPLATE_MATCH_THRESHOLD if threshold is None else threshold
        self.min_block = TEMPLATE_MATCH_MIN_BLOCK if min_block is None else min_block

    # ----- scoring -------------------------------------------------------

    def _recall(self, segment: str, body: str) -> int:
        """Characters of `segment` present in `body`, ignoring trivial overlaps.

        `min_block` discards incidental matches ("the ", " and ") that would
        otherwise let an unrelated email accumulate a passing score.
        """

        if segment in body:
            return len(segment)
        matcher = SequenceMatcher(None, segment, body, autojunk=False)
        return sum(
            block.size for block in matcher.get_matching_blocks() if block.size >= self.min_block
        )

    def score_template(
        self,
        template: EmailTemplate,
        body: str,
        name: str | None = None,
    ) -> TemplateScore:
        # `name` is the filename stem — the identifier every other command
        # takes. `template.name` is the internal slug and does not always agree
        # with it (e.g. email_referal_email → referal_email), so never report
        # that one.
        identifier = name or template.name
        normalized_body = normalize(body)
        segments = static_segments(template.body_template)
        static_chars = sum(len(segment) for segment in segments)
        if not static_chars:
            return TemplateScore(identifier, 0.0, 0, 0)

        matched = sum(self._recall(segment, normalized_body) for segment in segments)
        matched = min(matched, static_chars)
        return TemplateScore(
            template=identifier,
            score=matched / static_chars,
            matched_chars=matched,
            static_chars=static_chars,
        )

    # ----- public API ----------------------------------------------------

    def match(self, body: str, candidates: Sequence[str] | None = None) -> MatchResult:
        """Rank templates by how much of their fixed wording `body` reproduces.

        Any failure to read `templates/` is reported as an unmatched result with
        `error` set — the send gate fails closed rather than waving a body
        through because the matcher itself broke.
        """

        try:
            names = list(candidates) if candidates else self.repository.list_template_names()
        except Exception as exc:  # noqa: BLE001 - must degrade to "unmatched", never raise
            return MatchResult(False, None, 0.0, self.threshold, error=str(exc))

        ranking: list[TemplateScore] = []
        errors: list[str] = []
        for name in names:
            try:
                template = self.repository.load(name)
            except Exception as exc:  # noqa: BLE001 - one bad YAML must not hide the rest
                errors.append(f"{name}: {exc}")
                continue
            ranking.append(self.score_template(template, body, name=name))

        ranking.sort(key=lambda item: item.score, reverse=True)
        best = ranking[0] if ranking else None
        return MatchResult(
            matched=bool(best and best.score >= self.threshold),
            template=best.template if best else None,
            score=best.score if best else 0.0,
            threshold=self.threshold,
            ranking=ranking,
            error="; ".join(errors) or None,
        )


def guard_send(
    body: str,
    template: str | None = None,
    allow_unmatched: bool = False,
    matcher: TemplateMatcher | None = None,
    action: str = "send",
) -> tuple[dict[str, object] | None, MatchResult]:
    """Gate a draft or send on template conformance.

    Returns `(None, result)` when the write may proceed. Otherwise the first
    element is the refusal payload the caller must hand back verbatim: it
    carries `requires_confirmation: True` and the question to put to the user.

    `action` ("send" or "draft") only shapes the wording of that question — both
    Gmail writes are gated identically.

    `allow_unmatched=True` is the override, and it is only legitimate after the
    user has answered that question — see AGENTS.md §6.1.
    """

    active = matcher or TemplateMatcher()
    candidates = [template] if template else None
    result = active.match(body, candidates=candidates)

    if result.matched or allow_unmatched:
        return None, result

    best = result.template
    if template:
        detail = (
            f"The body does not match template '{template}' "
            f"(score {result.score:.2f} < threshold {result.threshold:.2f})."
        )
    elif best:
        detail = (
            "This email body does not match any template in templates/. "
            f"Closest is '{best}' at {result.score:.2f}, below the "
            f"{result.threshold:.2f} threshold."
        )
    else:
        detail = "No templates were available to match this email body against."

    payload: dict[str, object] = {
        "success": False,
        "requires_confirmation": True,
        "error": detail,
        "question": (
            "This particular email is not in our templates. "
            f"Should we still {action} it?"
        ),
        "match": result.as_dict(),
        "message": (
            f"{action.capitalize()} blocked pending confirmation. Ask the user the "
            "question above; only if they say yes, retry with allow_unmatched=True "
            "(CLI: --allow-unmatched)."
        ),
    }
    return payload, result
