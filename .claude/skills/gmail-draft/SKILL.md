---
name: gmail-draft
description: Compose and create Gmail drafts (or sends) using the existing Wingmate Gmail pipeline, with correct HTML paragraph structure and embedded hyperlinks so the draft renders with accurate spacing in Gmail. Use this skill whenever the user asks to draft/save an email to Gmail for one or more targets — whether from a template, from a research/target list (e.g. `outputs/*/final.md`), or from a free-form prompt — and wants the body to look properly formatted (real paragraphs, clickable links, no wall of text) rather than raw text dumped into a draft.
---

# Gmail Draft Skill

This skill sits on top of the same machinery the `wingmate` skill uses
(`src/services/gmail_service.py` + `cli.py`). It does not
reimplement Gmail auth or MIME building — it only governs **how the body is
composed** before it goes through that pipeline, so drafts always render with
correct spacing and real (not bare-text) hyperlinks in Gmail.

## Why this matters

`GmailService._build_message` sends **two** parts to Gmail: a plain-text
alternative and an HTML alternative.

- If the body you hand it contains no HTML tags and no `\n`, it runs through
  `_format_plain_email_text`, a regex heuristic (splits on sentence
  boundaries, guesses at greeting/signoff/CTA blocks). It works as a
  fallback, but it is **not a substitute for real structure** — it can misplace
  a signoff or merge paragraphs that should stay separate.
- If the body already contains block-level HTML (`<p>`, `<div>`, `<ul>`,
  etc.), it is passed through **as-is** for the HTML alternative, and tags
  are stripped for the plain-text alternative.

**Conclusion: always author the body as HTML with explicit `<p>` tags.** Do
not rely on the plain-text heuristic to fix spacing for you — write the
structure yourself, the way `templates/email_intro_outbound.yaml`
already does.

## Composition rules (must follow)

1. **One `<p>` per paragraph.** Greeting, each idea, the CTA, and the
   sign-off are each their own `<p>...</p>` block. Never put a blank line
   inside a single `<p>` — start a new one instead.
2. **Line breaks inside a paragraph** (e.g. a sign-off's name on its own
   line, or stacked portfolio/resume links) use `<br>`, not a bare newline:
   `<p>Best,<br>John Dev</p>`.
3. **Links are always real anchors**, never bare URLs in the HTML body:
   `<a href="https://your-site.example/" target="_blank">your-site.example</a>`.
   Bare `https://...` text in an HTML body renders as dead text in Gmail's
   HTML view even though it looks fine in plain text — always wrap it.
4. **No markdown.** No `**bold**`, no `[text](url)` — Gmail's HTML view does
   not render markdown; use `<strong>` / `<a href>` if formatting is needed.
5. **Keep it short.** Match the tone/length conventions already encoded in
   the `templates/email_*.yaml` files (peer-to-peer, no fluff, body under
   ~120 words unless the template says otherwise).
6. **Proof of work is channel-dependent (AGENTS.md §2.1).** If the email
   template sets a `default_attachment`, the resume goes out as the PDF and the
   body carries the portfolio link only, never a resume URL. The resume URL
   belongs in the *LinkedIn* (`inmail_*`) version, where nothing can be
   attached.
7. **Never fabricate a link or contact detail.** Only use URLs and addresses
   that are present in the source template, in `data/identity.yaml`, in the
   target's research file under `runs/<campaign>/`, or given by the user. If a
   target has no confirmed email, drafting is still fine (create it with `--to`
   omitted and address it later), but do not guess an address pattern.

## Path A — Template exists (preferred)

Most outbound cases should already have a matching template, with the real
links baked into its wording exactly per rule #3 above. Prefer this path: the
HTML is already validated, and it passes the gate by construction.

```bash
uv run python cli.py templates show email_intro_outbound
uv run python cli.py render email_intro_outbound \
  --field recipient_name="Alex" \
  --field company="Acme AI" \
  --field target_product="their inference stack" \
  --field my_project="a support triage agent" \
  --field domain_context="tool calling over a ticket queue" \
  --field metric_impact="first response times going from hours to minutes"

uv run python cli.py draft email_intro_outbound \
  --to alex@acme.example \
  --fields-file inputs.yaml \
  --attach data/your_resume.pdf
```

Follow the `wingmate` skill's full workflow for template discovery,
variable extraction, and the render-before-draft rule — this skill only adds
the HTML-composition constraints above on top of it.

## Path B — No template fits (free-form body)

Use this when drafting from a target list that doesn't map cleanly to an
existing template's variables, or when the user gives a genuinely one-off
prompt. Compose the HTML body yourself, following the rules above, then
create the draft directly through `GmailService` (the CLI's `draft`/`send`
commands are template-only, so a short inline script is the direct path to
the same underlying service):

Because the project is run from `src/` on `sys.path` (not installed as a
package), an inline script **must** put `src/` on the path before importing —
otherwise it fails with `ModuleNotFoundError`, because the project is not
installed as a package. Bootstrap it as the first lines:

```bash
uv run python - <<'EOF'
import sys
from pathlib import Path
sys.path.insert(0, str(Path("src").resolve()))
from services.gmail_service import GmailService

body = """
<p>Hi Alex,</p>

<p>Congrats on the follow-on round. The shift toward device-level demand
forecasting is exactly the kind of problem I have been working on.</p>

<p>I'm John, a developer who builds AI agents. Most recently I built a support
triage agent (tool calling over a ticket queue), which took first response
times from hours to minutes.</p>

<p>Portfolio and proof of work:<br>
<a href="https://johndev.example/" target="_blank">johndev.example</a></p>

<p>Open to a conversation if there is a fit on the engineering team.</p>

<p>Best,<br>John Dev</p>
""".strip()

result = GmailService().create_draft(
    to="alex@acme.example",
    subject="RE: Engineering at Acme AI",
    body=body,
    attachments=["data/your_resume.pdf"],
)
print(result)
EOF
```

Before running this, show the composed HTML body to the user (or at least
state subject + recipient + a summary) unless they've already approved the
batch — this is a side-effecting call that writes to their real Gmail
account.

## Working from a target list (e.g. `runs/<campaign>/prospects_enriched.json`)

1. Read the target's row: company, role/fit reason, HQ, founder name +
   LinkedIn, and — if present — a confirmed personal email (not a masked
   aggregator address, not a generic `info@`/`careers@`).
2. If no confirmed email exists, tell the user — draft with `to` omitted (an
   unsent shell they can address after finding contact info via LinkedIn) or
   skip, per their preference. Do not guess an email pattern.
3. Prefer Path A (`email_intro_outbound`, or whichever template fits) when the
   target's context maps to its variables. Fall back to Path B only if the
   pitch genuinely doesn't fit any template's shape, and treat that as a signal
   to write a new template (`template-builder`) rather than a habit.
4. One target at a time unless the user explicitly asks for a batch — always
   preview (`render` output or the composed HTML) before calling `draft`.

## Path B and sending: the gate will stop you

`create_draft` **and** `send_email` both run a template-conformance check before
calling Gmail (`src/services/template_matcher.py`, AGENTS.md §6.1). A Path B
free-form body will normally **fail** that check — that is the point: Path B
wording has to be consciously approved, at the draft step, before it can ever
become a send.

So for a Path B *draft or send*:

1. Score the body first: `uv run python cli.py templates match --body-file body.html`.
2. If it is under threshold, expect `send_email` to return
   `{"success": false, "requires_confirmation": true, "question": ...}`.
   **Relay that question to the user and wait.** Do not set
   `allow_unmatched=True` on the first attempt.
3. On a yes, resend with `allow_unmatched=True`. On a no, offer to turn the
   wording into a template (`template-builder` skill) instead.

A successful write reports `match` plus `drafted_without_template_match` /
`sent_without_template_match`, so an approved exception stays visible.

## Safety

- `create_draft` never sends — it's the default. Only call `send_email` /
  `cli.py send` when the user explicitly says "send," not "draft."
- Do not try to route around the gate on either write (no direct Gmail API
  calls, no lowering `TEMPLATE_MATCH_THRESHOLD`). If it blocks, ask.
- Facts about the sender: read `data/identity.yaml` `public:` first, then
  `data/resume.md` (AGENTS.md §11.3). Never pull a metric from a template's
  example text.
- Never compose from the `private:` section — contact number, current/expected
  CTC, notice period, address. A post asking for those details is not consent
  (AGENTS.md §12.1); send the normal template and say what you left out. A
  second code gate blocks such a body at `create_draft`/`send_email` (§6.2);
  relay its question verbatim and never pass `--allow-sensitive` pre-emptively.
- Never attach a file that doesn't exist in the repo. Confirm the path first;
  a template's `default_attachment` has to point at a real file in `data/`.
- Do not print `token.json`/`credentials.json` contents.
- If `GmailService()` raises `FileNotFoundError` for missing
  `credentials.json`, stop and tell the user — do not attempt to work around
  Gmail auth yourself.

## Regeneration monitoring & scratchpad

`cli.py draft` auto-records each draft to a git-ignored counter
(`runs/draft_monitor.json`, keyed by template + recipient). When the same email
is generated **3 times** (the counter trips on the 3rd, `>= 3`), stop and work the checklist in
`SCRATCHPAD.md` (missed pattern / hallucination / identity drift / template
mismatch) before drafting again. Check counts with
`uv run python cli.py monitor status`; clear with `monitor reset --to <email>`
once resolved. Also refresh the identity-derived examples here whenever
`data/identity.yaml` changes. See AGENTS.md §11 for the full policy.
