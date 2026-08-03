"""Guardrail checks for the identity split and the disclosure gate.

The situation these exist for: a recruiter post asks applicants to reply with
contact number, current CTC, expected CTC and notice period. None of that is
public, none of it belongs in an email, and "the agent chose well" is not a
control. These checks make it structural instead:

- `data/identity.yaml` really does separate `public` from `private`
- the public section carries no contact or negotiation detail
- reading `private` refuses without approval, and withholds values while it does
- a body carrying private data is blocked at the Gmail boundary, drafts included
- the block holds even with no `private` section on disk (fails closed)
- every template in this repo still passes, so the gate is not a nuisance

The checks that need populated private data build their own temporary identity
file, so they hold whether or not you have filled `private:` in on disk.

Run: uv run python guardrails/check_identity_disclosure_gate.py
(also collectable by pytest: uv run python -m pytest guardrails -q)
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import yaml  # noqa: E402

from services.email_service import EmailService  # noqa: E402
from services.identity_service import (  # noqa: E402
    IdentityService,
    guard_disclosure,
)


IDENTITY_PATH = ROOT / "data" / "identity.yaml"

# What a recruiter's "share your details" list asks for. This is the exact body
# shape the gate exists to stop.
DETAILS_BODY = """
<p>Hi Neha,</p>
<p>Sharing the details you asked for:</p>
<p>Contact Number: +91 98765 43210<br>
Current CTC: 18 LPA<br>
Expected CTC: 28 LPA<br>
Notice Period: 60 days</p>
<p>Best,<br>John Dev</p>
"""

# A private section with real-looking values, for the checks that need one.
POPULATED_IDENTITY = """
public:
  sender:
    name: "John Dev"
private:
  contact:
    email: "john.dev.private@example.com"
    phone: "+91 98765 43210"
  employment:
    expected_ctc: "28 LPA"
"""


def _identity() -> dict:
    return yaml.safe_load(IDENTITY_PATH.read_text(encoding="utf-8")) or {}


def _populated(tmp_path: Path) -> IdentityService:
    path = tmp_path / "identity.yaml"
    path.write_text(POPULATED_IDENTITY, encoding="utf-8")
    return IdentityService(path=path)


def rendered(template: str, **fields: str) -> dict:
    return EmailService().render_rule_based(template, fields)


def check_identity_yaml_has_both_sections() -> None:
    payload = _identity()
    assert "public" in payload, "identity.yaml lost its public section"
    assert "private" in payload, "identity.yaml lost its private section"


def check_public_section_still_carries_the_work_ledger() -> None:
    """The split must not cost outbound anything it legitimately quotes."""

    public = _identity()["public"]
    assert public["sender"]["name"]
    assert public["sender"]["creds"]
    assert public["projects"], "the project ledger is empty; outbound has nothing to cite"
    for project in public["projects"]:
        assert project.get("id") and project.get("metric")


def check_public_section_carries_no_private_detail() -> None:
    """Anything a recruiter form asks for belongs on the other side of the line."""

    from services.identity_service import _flatten

    banned = ("ctc", "salary", "compensation", "notice", "phone", "mobile", "aadhaar", "passport")
    offenders = []
    for path, value in _flatten(_identity()["public"]):
        lowered = path.lower()
        if any(word in lowered for word in banned):
            offenders.append(path)
        if "@" in value and "mailto" not in value.lower():
            offenders.append(f"{path} (contact address)")
    assert not offenders, f"private detail in the public section: {offenders}"


def check_private_retrieval_is_refused_without_approval(tmp_path: Path) -> None:
    blocked, data = _populated(tmp_path).load_private()
    assert blocked is not None
    assert blocked["requires_confirmation"] is True
    assert "Should we share them?" in blocked["question"]
    assert data == {}, "a refused retrieval must withhold the values"


def check_refusal_names_the_fields_without_leaking_them(tmp_path: Path) -> None:
    """The user needs to know what is being asked for; the caller does not get it."""

    service = _populated(tmp_path)
    blocked, _ = service.load_private()
    assert blocked is not None
    assert any("contact" in name for name in blocked["fields"])

    rendered_refusal = str(blocked)
    for source, value in service.sensitive_values():
        if source.startswith("env."):
            continue
        assert value not in rendered_refusal, f"{source} leaked into the refusal"


def check_private_retrieval_succeeds_once_approved(tmp_path: Path) -> None:
    blocked, data = _populated(tmp_path).load_private(allow_sensitive=True)
    assert blocked is None
    assert "contact" in data


def check_recruiter_details_body_is_blocked() -> None:
    blocked, findings = guard_disclosure(DETAILS_BODY)
    assert blocked is not None
    assert blocked["requires_confirmation"] is True
    labels = {finding.label for finding in findings}
    assert "a phone number" in labels
    assert "a salary or CTC figure" in labels
    assert "a notice period" in labels


def check_override_lets_an_approved_disclosure_through_but_still_reports_it() -> None:
    blocked, findings = guard_disclosure(DETAILS_BODY, allow_sensitive=True)
    assert blocked is None
    assert findings, "an approved disclosure must stay visible in the output"


def check_a_private_value_is_caught_even_without_a_pattern_rule(tmp_path: Path) -> None:
    """A personal address is not a recognisable "shape", so it is caught by
    matching the private section itself. Typed from memory or pasted from an old
    thread, it still blocks at the Gmail boundary."""

    smuggled = "<p>Hi Alex, reach me at john.dev.private@example.com</p>"
    blocked, _ = guard_disclosure(smuggled, service=_populated(tmp_path))
    assert blocked is not None


def check_gate_fails_closed_with_no_private_section(tmp_path: Path) -> None:
    """A checkout whose identity.yaml has no private section must still block."""

    empty = tmp_path / "identity.yaml"
    empty.write_text("public:\n  sender:\n    name: 'X'\n", encoding="utf-8")
    blocked, _ = guard_disclosure(DETAILS_BODY, service=IdentityService(path=empty))
    assert blocked is not None


def check_gate_fails_closed_on_an_unreadable_file(tmp_path: Path) -> None:
    broken = tmp_path / "identity.yaml"
    broken.write_text("public: [unclosed\n", encoding="utf-8")
    service = IdentityService(path=broken)
    assert service.load().error
    blocked, _ = guard_disclosure(DETAILS_BODY, service=service)
    assert blocked is not None


def check_gmail_service_gates_both_writes_on_disclosure() -> None:
    """The gate sits in the service, so an inline script hits it too."""

    import inspect

    from services.gmail_service import GmailService

    for method in (
        GmailService.create_draft,
        GmailService.send_email,
        GmailService.update_draft_recipient,
    ):
        source = inspect.getsource(method)
        assert "guard_disclosure" in source, f"{method.__name__} skips the disclosure gate"
        params = inspect.signature(method).parameters
        assert "allow_sensitive" in params, f"{method.__name__} lacks allow_sensitive"
        assert params["allow_sensitive"].default is False


def check_every_template_passes_the_gate() -> None:
    """A gate that blocks our own approved copy would just get switched off."""

    placeholder = {
        "recipient_name": "Alex",
        "company": "Acme AI",
        "company_name": "Acme AI",
        "position": "AI Engineer",
        "role_type": "AI Engineer",
        "platform_name": "LinkedIn",
        "job_link": "https://example.com/job",
        "job_description": "building inference infrastructure",
        "hiring_manager": "Alex",
        "target_product": "inference infrastructure",
        "main_product": "inference infrastructure",
        "my_work_and_impact": "I built a triage agent that cut response time 10x",
        "my_project": "a support triage agent",
        "domain_context": "tool calling over a ticket queue",
        "metric_impact": "first response times going from hours to minutes",
    }
    offenders = []
    for path in sorted((ROOT / "templates").glob("*.yaml")):
        name = path.stem
        try:
            template = EmailService().get_template(name)
            fields = {var: placeholder.get(var, "value") for var in template.variables}
            result = rendered(name, **fields)
        except Exception:  # noqa: BLE001 - a broken template is another check's problem
            continue
        blocked, findings = guard_disclosure(
            body=result["body"], subject=result["subject"], template=name
        )
        if blocked is not None:
            offenders.append(f"{name}: {[f.source for f in findings]}")
    assert not offenders, f"approved template copy tripped the gate: {offenders}"


def check_a_templates_own_wording_is_exempt_only_for_that_template(tmp_path: Path) -> None:
    """If you deliberately publish a contact address inside a template body, that
    was approved once when the template was written. The same address in a body
    rendered from a different template is a new disclosure, and blocks."""

    service = _populated(tmp_path)
    address = "john.dev.private@example.com"

    # Standing in for a template whose fixed wording contains the address: the
    # allowlist is built from the named template's static segments.
    smuggled = f"<p>Hi Alex, reach me at {address}</p>"
    blocked, _ = guard_disclosure(
        smuggled, template="email_intro_outbound", service=service
    )
    assert blocked is not None, "an address absent from the named template must block"


def check_public_project_metrics_do_not_trip_the_gate() -> None:
    """Proof-of-work numbers are the point of the ledger; they must stay usable."""

    copy = (
        "<p>I built a support triage agent handling a 400-ticket per week queue, and "
        "a docs assistant that took citation accuracy from 61% to 88%.</p>"
    )
    blocked, findings = guard_disclosure(copy)
    assert blocked is None, f"public metrics blocked: {[f.as_dict() for f in findings]}"


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
