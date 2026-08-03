"""Guardrail checks for the send-time template conformance gate.

These are not unit tests of incidental behaviour. Each one pins a property the
gate must hold for outbound safety: an off-template body is refused, the refusal
carries the question to ask, the override does not misreport conformance, and an
unreadable `templates/` blocks rather than allows.

They are written against the seed templates. If you rename or delete
`email_intro_outbound`, update `SEED_TEMPLATE` below rather than deleting the
check: the point is that *some* real template in this repo still round-trips
through the matcher at 1.0.

Run: uv run python guardrails/check_send_template_gate.py
(also collectable by pytest: uv run python -m pytest guardrails -q)
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from services.email_service import EmailService  # noqa: E402
from services.template_matcher import (  # noqa: E402
    TemplateMatcher,
    guard_send,
    normalize,
    static_segments,
)


SEED_TEMPLATE = "email_intro_outbound"
SEED_FIELDS = {
    "recipient_name": "Alex",
    "company": "Acme AI",
    "target_product": "inference infrastructure",
    "my_project": "a support triage agent",
    "domain_context": "tool calling over a ticket queue",
    "metric_impact": "first response times going from hours to minutes",
}

# A body written from scratch instead of from a template. This is the exact
# shape the gate exists to stop.
FREE_FORM_BODY = """
<p>Hi Alex,</p>
<p>I came across your post about the AI team expansion and would like to apply
for the AI Engineer role.</p>
<p><strong>Education:</strong> BSc Computer Science, Example University</p>
<p><strong>Skills:</strong> Python, PyTorch, FastAPI</p>
<p>Best,<br>John Dev</p>
"""


def rendered(template: str, **fields: str) -> str:
    return EmailService().render_rule_based(template, fields)["body"]


def check_normalize_strips_html_and_case() -> None:
    assert normalize("<p>Hello   <a href='x'>There</a></p>") == "hello there"
    assert normalize("A &amp; B") == "a & b"


def check_static_segments_drop_placeholders() -> None:
    segments = static_segments("Hi {recipient_name}, welcome to {company}!")
    assert segments == ["hi", ", welcome to", "!"]


def check_rendered_template_body_matches_its_own_template() -> None:
    result = TemplateMatcher().match(rendered(SEED_TEMPLATE, **SEED_FIELDS))
    assert result.matched
    assert result.template == SEED_TEMPLATE
    assert result.score == 1.0


def check_reported_template_is_the_filename_stem() -> None:
    """The identifier must be loadable by every other command, not the inner slug."""

    name = TemplateMatcher().match(rendered(SEED_TEMPLATE, **SEED_FIELDS)).template
    assert name is not None
    assert (ROOT / "templates" / f"{name}.yaml").exists()


def check_free_form_body_does_not_match() -> None:
    result = TemplateMatcher().match(FREE_FORM_BODY)
    assert not result.matched
    assert result.score < result.threshold


def check_draft_and_send_are_gated_identically() -> None:
    """Drafting is where the wording is decided, so it is gated too. Only the
    question's verb differs."""

    blocked_send, _ = guard_send(FREE_FORM_BODY, action="send")
    blocked_draft, _ = guard_send(FREE_FORM_BODY, action="draft")
    assert blocked_send is not None and blocked_draft is not None
    assert "still send it?" in blocked_send["question"]
    assert "still draft it?" in blocked_draft["question"]
    assert blocked_draft["message"].startswith("Draft blocked")


def check_gmail_service_gates_both_writes() -> None:
    """The gate must sit in GmailService, not only in the CLI. An inline script
    that imports the service directly has to hit it too."""

    import inspect

    from services.gmail_service import GmailService

    for method in (GmailService.create_draft, GmailService.send_email):
        source = inspect.getsource(method)
        assert "guard_send" in source, f"{method.__name__} does not call guard_send"
        params = inspect.signature(method).parameters
        assert "allow_unmatched" in params, f"{method.__name__} lacks allow_unmatched"
        assert params["allow_unmatched"].default is False


def check_guard_blocks_free_form_send() -> None:
    blocked, result = guard_send(FREE_FORM_BODY)
    assert blocked is not None
    assert blocked["success"] is False
    assert blocked["requires_confirmation"] is True
    assert "Should we still send it?" in blocked["question"]
    assert not result.matched


def check_guard_allows_template_send() -> None:
    body = rendered(SEED_TEMPLATE, **SEED_FIELDS)
    blocked, result = guard_send(body, template=SEED_TEMPLATE)
    assert blocked is None
    assert result.matched


def check_override_lets_a_free_form_body_through() -> None:
    blocked, result = guard_send(FREE_FORM_BODY, allow_unmatched=True)
    assert blocked is None
    # The override bypasses the block but must not misreport conformance.
    assert not result.matched


def check_empty_body_is_blocked() -> None:
    blocked, _ = guard_send("")
    assert blocked is not None


def check_fails_closed_when_no_templates_are_available(tmp_path: Path) -> None:
    """A broken or empty templates dir must block sends, not wave them through."""

    from repositories.template_repository import TemplateRepository

    matcher = TemplateMatcher(repository=TemplateRepository(tmp_path / "empty"))
    blocked, result = guard_send("anything", matcher=matcher)
    assert blocked is not None
    assert not result.matched


def check_wrong_named_template_is_reported_against_that_template() -> None:
    """Naming a template scores against it alone, so the error names it."""

    blocked, _ = guard_send(FREE_FORM_BODY, template=SEED_TEMPLATE)
    assert blocked is not None
    assert SEED_TEMPLATE in blocked["error"]


def check_every_template_declares_and_uses_the_same_variables() -> None:
    """The two-way check in TemplateRepository, applied to the whole folder."""

    from repositories.template_repository import TemplateRepository

    repository = TemplateRepository()
    offenders = []
    for path in sorted((ROOT / "templates").glob("*.yaml")):
        errors = repository.validate_template(repository.load(path.stem))
        if errors:
            offenders.append(f"{path.stem}: {errors}")
    assert not offenders, f"invalid template(s): {offenders}"


def check_no_em_dashes_in_recipient_facing_copy() -> None:
    """House rule: em dashes read as machine written, so they are banned from the
    subject and body. Internal fields (description, instructions) are exempt.

    This is a style choice, not a safety property. If you disagree, delete this
    one function rather than leaving it failing."""

    import yaml

    offenders = []
    for path in sorted((ROOT / "templates").glob("*.yaml")):
        try:
            payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:  # noqa: BLE001 - a malformed template is another check's problem
            continue
        for field in ("subject_template", "body_template"):
            if "—" in str(payload.get(field, "")):
                offenders.append(f"{path.name}:{field}")
    assert not offenders, f"em dash in recipient-facing copy: {offenders}"


if __name__ == "__main__":
    import tempfile
    import traceback

    failures = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith("check_") or not callable(fn):
            continue
        try:
            if "tmp_path" in fn.__code__.co_varnames[: fn.__code__.co_argcount]:
                with tempfile.TemporaryDirectory() as tmp:
                    fn(Path(tmp))
            else:
                fn()
            print(f"HELD    {name}")
        except Exception:  # noqa: BLE001 - guardrail runner reports, never raises
            failures += 1
            print(f"VIOLATED {name}")
            traceback.print_exc()
    print(f"\n{failures} guardrail violation(s)")
    raise SystemExit(1 if failures else 0)
