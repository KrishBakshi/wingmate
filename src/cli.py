"""Wingmate command-line interface.

Exposes all core capabilities (templates, rendering, Gmail drafts/sends,
batch processing) as CLI commands so that both humans and coding agents can
drive the app.

Rendering is deterministic string substitution. There is no model API in this
repo: the intelligence lives in whatever agent is driving the CLI.

All commands print JSON to stdout so they are easy to parse programmatically.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

import yaml


def _add_src_to_path() -> None:
    """Ensure `src/` is importable when running as a script."""

    cli_file = Path(__file__).resolve()
    src_dir = cli_file.parents[0]
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))


_add_src_to_path()


from repositories.template_repository import TemplateRepository  # noqa: E402
from services.email_service import EmailService  # noqa: E402


def _emit(payload: Any) -> None:
    print(json.dumps(payload, indent=2, default=str, ensure_ascii=False))


def _parse_fields(pairs: list[str] | None) -> dict[str, str]:
    fields: dict[str, str] = {}
    for item in pairs or []:
        if "=" not in item:
            raise SystemExit(f"Invalid --field value (expected key=value): {item}")
        key, value = item.split("=", 1)
        fields[key.strip()] = value
    return fields


def _load_fields_file(path: str | None) -> dict[str, str]:
    if not path:
        return {}
    file_path = Path(path)
    if not file_path.exists():
        raise SystemExit(f"Fields file not found: {file_path}")
    if file_path.suffix.lower() in {".yaml", ".yml"}:
        payload = yaml.safe_load(file_path.read_text(encoding="utf-8")) or {}
    else:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"Fields file must contain a mapping: {file_path}")
    return {str(key): str(value) for key, value in payload.items()}


def _collect_fields(args: argparse.Namespace) -> dict[str, str]:
    fields = _load_fields_file(getattr(args, "fields_file", None))
    fields.update(_parse_fields(getattr(args, "field", None)))
    return fields


def _render(args: argparse.Namespace) -> dict[str, str]:
    svc = EmailService()
    return svc.render_rule_based(args.template, _collect_fields(args))


def cmd_templates_list(_: argparse.Namespace) -> None:
    repo = TemplateRepository()
    _emit({"success": True, "templates": repo.list_template_names()})


def cmd_templates_show(args: argparse.Namespace) -> None:
    repo = TemplateRepository()
    template = repo.load(args.template)
    _emit({"success": True, "template": template.model_dump()})


def cmd_templates_validate(args: argparse.Namespace) -> None:
    repo = TemplateRepository()
    names = [args.template] if args.template else repo.list_template_names()
    report: list[dict[str, Any]] = []
    ok = True
    for name in names:
        try:
            template = repo.load(name)
            errors = repo.validate_template(template)
            entry = {"template": name, "valid": not errors, "errors": errors}
        except Exception as exc:
            ok = False
            entry = {"template": name, "valid": False, "errors": [str(exc)]}
        if entry["errors"]:
            ok = False
        report.append(entry)
    _emit({"success": ok, "results": report})
    if not ok:
        raise SystemExit(1)


def cmd_render(args: argparse.Namespace) -> None:
    rendered = _render(args)
    _emit({"success": True, **rendered})


def _require_gmail() -> Callable[[], Any]:
    from services.gmail_service import GmailService

    return GmailService


def cmd_draft(args: argparse.Namespace) -> None:
    from services.email_service import EmailService

    GmailService = _require_gmail()
    rendered = _render(args)
    gmail = GmailService()

    attachments = list(args.attach or [])
    if not attachments:
        template = EmailService().get_template(args.template)
        if template.default_attachment:
            attachments.append(template.default_attachment)

    result = gmail.create_draft(
        to=args.to,
        subject=rendered["subject"],
        body=rendered["body"],
        attachments=attachments or None,
        template=args.template,
        allow_unmatched=args.allow_unmatched,
        allow_sensitive=args.allow_sensitive,
    )

    # Auto-record every draft so the "same email > 3 times" counter is real,
    # not dependent on the agent remembering. Never let it break drafting.
    monitor: dict[str, Any] = {}
    try:
        from services.draft_monitor import record as _record

        monitor = _record(args.template, args.to)
    except Exception as exc:  # noqa: BLE001 - monitoring must never block a draft
        monitor = {"error": str(exc)}

    _emit({"rendered": rendered, "result": result, "monitor": monitor})
    if not result.get("success"):
        raise SystemExit(1)


def cmd_send(args: argparse.Namespace) -> None:
    GmailService = _require_gmail()
    rendered = _render(args)
    gmail = GmailService()
    result = gmail.send_email(
        to=args.to,
        subject=rendered["subject"],
        body=rendered["body"],
        attachments=args.attach or None,
        template=args.template,
        allow_unmatched=args.allow_unmatched,
        allow_sensitive=args.allow_sensitive,
    )
    _emit({"rendered": rendered, "result": result})
    if not result.get("success"):
        raise SystemExit(1)


def cmd_templates_match(args: argparse.Namespace) -> None:
    """Score a body against the templates without sending anything."""

    from services.template_matcher import TemplateMatcher

    if args.body_file:
        body = Path(args.body_file).read_text(encoding="utf-8")
    elif args.body:
        body = args.body
    else:
        body = sys.stdin.read()

    matcher = TemplateMatcher(threshold=args.threshold) if args.threshold else TemplateMatcher()
    candidates = [args.template] if args.template else None
    _emit({"success": True, **matcher.match(body, candidates=candidates).as_dict()})


def cmd_identity_show(args: argparse.Namespace) -> None:
    """Read the identity ledger. Public is free; private needs --allow-sensitive."""

    from services.identity_service import IdentityService

    service = IdentityService()
    document = service.load()
    payload: dict[str, Any] = {
        "success": True,
        "path": str(document.path),
        "public": document.public,
    }
    if document.error:
        payload["warning"] = document.error

    if args.private:
        blocked, private = service.load_private(allow_sensitive=args.allow_sensitive)
        if blocked is not None:
            _emit({**payload, **blocked})
            raise SystemExit(1)
        payload["private"] = private
        payload["disclosed_private_fields"] = True

    _emit(payload)


def cmd_identity_scan(args: argparse.Namespace) -> None:
    """Check a body for private-data disclosure without sending anything."""

    from services.identity_service import disclosures_as_dicts, guard_disclosure

    if args.body_file:
        body = Path(args.body_file).read_text(encoding="utf-8")
    elif args.body:
        body = args.body
    else:
        body = sys.stdin.read()

    blocked, findings = guard_disclosure(
        body=body, subject=args.subject or "", template=args.template
    )
    _emit(
        {
            "success": True,
            "clean": blocked is None,
            "disclosures": disclosures_as_dicts(findings),
            "question": blocked["question"] if blocked else None,
        }
    )


def cmd_drafts_list(args: argparse.Namespace) -> None:
    GmailService = _require_gmail()
    gmail = GmailService()
    _emit(gmail.list_drafts(max_results=args.max_results))


def cmd_monitor_status(args: argparse.Namespace) -> None:
    from services.draft_monitor import status

    _emit(status(template=args.template, to=args.to))


def cmd_monitor_reset(args: argparse.Namespace) -> None:
    from services.draft_monitor import reset

    _emit(reset(template=args.template, to=args.to))


def cmd_batch_preview(args: argparse.Namespace) -> None:
    from services.batch_service import BatchService

    batch = BatchService()
    result = batch.preview_batch(
        excel_path=args.file,
        template_name=args.template,
        email_column=args.email_column,
        max_preview=args.max,
    )
    _emit(result)
    if not result.get("success"):
        raise SystemExit(1)


def cmd_batch_run(args: argparse.Namespace) -> None:
    from services.batch_service import BatchService
    from services.gmail_service import GmailService

    batch = BatchService(gmail_service=GmailService())
    result = batch.process_batch(
        excel_path=args.file,
        template_name=args.template,
        email_column=args.email_column,
        attachments=args.attach or None,
        delay_seconds=args.delay,
    )
    _emit(result)
    if not result.get("success"):
        raise SystemExit(1)


def cmd_batch_sample(args: argparse.Namespace) -> None:
    from services.batch_service import BatchService

    batch = BatchService()
    result = batch.generate_sample_excel(
        template_name=args.template,
        output_path=args.out,
        email_column=args.email_column,
    )
    _emit(result)
    if not result.get("success"):
        raise SystemExit(1)


def _add_allow_sensitive(parser: argparse.ArgumentParser, verb: str) -> None:
    parser.add_argument(
        "--allow-sensitive",
        action="store_true",
        help=(
            f"{verb} even if the body discloses private identity data (phone, CTC, "
            "notice period). Only after the user has answered the confirmation "
            "question."
        ),
    )


def _add_field_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--field",
        "-f",
        action="append",
        metavar="KEY=VALUE",
        help="Template variable value. Repeatable.",
    )
    parser.add_argument(
        "--fields-file",
        help="Path to a JSON or YAML file with field values.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wingmate",
        description="Wingmate CLI: templates, rendering, Gmail drafts, batch.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    templates = sub.add_parser("templates", help="Manage YAML email templates.")
    tsub = templates.add_subparsers(dest="action", required=True)

    tsub.add_parser("list", help="List available templates.").set_defaults(
        func=cmd_templates_list
    )

    show = tsub.add_parser("show", help="Show a template's full definition.")
    show.add_argument("template")
    show.set_defaults(func=cmd_templates_show)

    validate = tsub.add_parser("validate", help="Validate one or all templates.")
    validate.add_argument("template", nargs="?", default=None)
    validate.set_defaults(func=cmd_templates_validate)

    match = tsub.add_parser(
        "match",
        help="Score a message body against the templates (what `send` gates on).",
    )
    match.add_argument(
        "template",
        nargs="?",
        default=None,
        help="Score against this template only. Default: rank all templates.",
    )
    match.add_argument("--body", help="Body text. Omit to read from --body-file or stdin.")
    match.add_argument("--body-file", help="Path to a file containing the body.")
    match.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="Override the pass threshold for this check only.",
    )
    match.set_defaults(func=cmd_templates_match)

    render = sub.add_parser("render", help="Render a template to subject + body.")
    render.add_argument("template")
    _add_field_args(render)
    render.set_defaults(func=cmd_render)

    draft = sub.add_parser("draft", help="Render and create a Gmail draft.")
    draft.add_argument("template")
    draft.add_argument("--to", required=False, default=None, help="Recipient email.")
    draft.add_argument("--attach", action="append", help="File to attach. Repeatable.")
    draft.add_argument(
        "--allow-unmatched",
        action="store_true",
        help=(
            "Draft even if the body does not match the template. Only after the "
            "user has answered the confirmation question."
        ),
    )
    _add_allow_sensitive(draft, "Draft")
    _add_field_args(draft)
    draft.set_defaults(func=cmd_draft)

    send = sub.add_parser("send", help="Render and send an email via Gmail.")
    send.add_argument("template")
    send.add_argument("--to", required=True, help="Recipient email.")
    send.add_argument("--attach", action="append", help="File to attach. Repeatable.")
    send.add_argument(
        "--allow-unmatched",
        action="store_true",
        help=(
            "Send even if the body does not match the template. Only after the "
            "user has answered the confirmation question."
        ),
    )
    _add_allow_sensitive(send, "Send")
    _add_field_args(send)
    send.set_defaults(func=cmd_send)

    identity = sub.add_parser(
        "identity", help="Read the identity ledger and scan bodies for private data."
    )
    isub = identity.add_subparsers(dest="action", required=True)
    identity_show = isub.add_parser("show", help="Show the public identity section.")
    identity_show.add_argument(
        "--private",
        action="store_true",
        help="Also request the private section (contact, CTC, notice period).",
    )
    _add_allow_sensitive(identity_show, "Show")
    identity_show.set_defaults(func=cmd_identity_show)

    identity_scan = isub.add_parser(
        "scan", help="Check a body for private-data disclosure. No side effects."
    )
    identity_scan.add_argument("--body", help="Body text. Omit to read stdin.")
    identity_scan.add_argument("--body-file", help="Path to a file holding the body.")
    identity_scan.add_argument("--subject", help="Subject line, also scanned.")
    identity_scan.add_argument(
        "--template", help="Template the body came from; its own wording is exempt."
    )
    identity_scan.set_defaults(func=cmd_identity_scan)

    drafts = sub.add_parser("drafts", help="Gmail drafts operations.")
    dsub = drafts.add_subparsers(dest="action", required=True)
    drafts_list = dsub.add_parser("list", help="List recent Gmail drafts.")
    drafts_list.add_argument("--max-results", type=int, default=10)
    drafts_list.set_defaults(func=cmd_drafts_list)

    monitor = sub.add_parser(
        "monitor", help="Regeneration counter for the same email (template + recipient)."
    )
    msub = monitor.add_subparsers(dest="action", required=True)
    monitor_status = msub.add_parser("status", help="Show regeneration counts.")
    monitor_status.add_argument("--template", default=None)
    monitor_status.add_argument("--to", default=None)
    monitor_status.set_defaults(func=cmd_monitor_status)
    monitor_reset = msub.add_parser("reset", help="Clear counters (all, or filtered).")
    monitor_reset.add_argument("--template", default=None)
    monitor_reset.add_argument("--to", default=None)
    monitor_reset.set_defaults(func=cmd_monitor_reset)

    batch = sub.add_parser("batch", help="Batch operations over a spreadsheet.")
    bsub = batch.add_subparsers(dest="action", required=True)

    batch_preview = bsub.add_parser("preview", help="Preview rendered rows.")
    batch_preview.add_argument("--file", required=True, help="Excel/CSV file.")
    batch_preview.add_argument("--template", required=True)
    batch_preview.add_argument("--email-column", default="email")
    batch_preview.add_argument("--max", type=int, default=3)
    batch_preview.set_defaults(func=cmd_batch_preview)

    batch_run = bsub.add_parser("run", help="Create drafts for every row.")
    batch_run.add_argument("--file", required=True)
    batch_run.add_argument("--template", required=True)
    batch_run.add_argument("--email-column", default="email")
    batch_run.add_argument("--attach", action="append")
    batch_run.add_argument("--delay", type=float, default=0.25)
    batch_run.set_defaults(func=cmd_batch_run)

    batch_sample = bsub.add_parser("sample", help="Generate a sample Excel for a template.")
    batch_sample.add_argument("--template", required=True)
    batch_sample.add_argument("--out", required=True)
    batch_sample.add_argument("--email-column", default="email")
    batch_sample.set_defaults(func=cmd_batch_sample)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
