---
name: template-builder
description: Author new Wingmate email/InMail templates — the `.yaml` files in `templates/` — with the correct schema, naming prefix, and declared/used variable balance, then validate and save them through the repo CLI. Use whenever the user asks to create, add, scaffold, draft, or edit a message template (email or LinkedIn/InMail), or wants a new reusable outbound format saved to `templates/`.
---

# Template Builder Skill

Creates and validates the YAML templates that the `wingmate` and `gmail-draft`
skills later render into drafts. Templates are hand-authored: there is no
generator command and no model API in this repo, so the writing is yours.

A template is a single `.yaml` file in `templates/`. Its filename stem **is**
its template name (`templates/email_intro_outbound.yaml` → `email_intro_outbound`),
which is how every other command references it.

## The schema (required, exact top-level keys)

Backed by `src/models/email_template.py` (`EmailTemplate`, pydantic). Missing
or misspelled keys fail validation.

```yaml
name: email_intro_outbound          # slug: lowercase, digits, underscores only. Must match the filename stem.
meta:
  title: Hiring Manager Outreach    # human-readable name
  description: Cold email to a named hiring manager about an open role.
variables:                          # every placeholder used below must be declared here
  - hiring_manager
  - position
  - company_name
system_instruction: |               # per-template instruction to the model (be specific to THIS template)
  You are an expert outreach writer. Keep it concise, peer-to-peer, no fluff.
subject_template: "RE: Engineering at {company_name}"
body_template: |                    # the actual message; email bodies are HTML (see gmail-draft rules)
  <p>Hi {hiring_manager},</p>
  <p>... uses {position} and {company_name} ...</p>
  <p>Best,<br>John Dev</p>
# default_attachment: data/your_resume.pdf   # optional; omit if none
```

Optional key: `default_attachment` (string path, or omit). Everything else in
the list above is required.

## Naming rule (pick the prefix by channel)

The filename/`name` prefix signals the channel, matching the existing
`templates/` files and the `wingmate` skill's Naming Rule:

- `email_<purpose>` — email / long-form chat (HTML body).
- `inmail_<purpose>` — LinkedIn notes, InMails, SMS-like channels (plain text,
  no HTML tags, and mind LinkedIn's ~300-char connection-note limit).
- `extra_<campaign_or_event>_<purpose>` — temporary / campaign-specific templates.

Slug rule: lowercase letters, digits, underscores only. Author the filename to
match the `name:` field exactly.

## The one hard validation rule: declared == used

`TemplateRepository.validate_template` enforces a **two-way** match between
`variables:` and the `{placeholders}` in `subject_template` + `body_template`:

- Every `{placeholder}` used **must** be declared in `variables:` (else:
  *"used but not declared"*).
- Every declared variable **must** appear in at least one of the three fields
  (else: *"declared but unused"*).

So: no undeclared placeholders, no dead variables. Placeholders are single
braces `{name}` (Python `str.format` style), not `{{name}}`.

## Style conventions (match the house voice)

- **Email bodies are HTML.** Follow the `gmail-draft` skill's composition
  rules: one `<p>` per paragraph, `<br>` for in-paragraph breaks, real
  `<a href="..." target="_blank">anchor</a>` for links (never bare URLs), no
  markdown. This keeps spacing/links correct when the template is later
  drafted into Gmail.
- **InMail bodies are plain text** — no HTML tags at all (a stray `<br>` in an
  inmail template renders as literal text on LinkedIn).
- **Tone:** technical peer, direct, non-generic (see `data/identity.yaml`
  `logic_rules`). Avoid the forbidden phrases there
  ("I hope this finds you well", "Dear Hiring Manager").
- **Keep bodies tight** (~120 words for email; shorter for inmail).
- **Never fabricate links or contacts** — reuse the real ones already baked
  into existing templates and `data/identity.yaml`, or values the user gives
  you.
- **Resume: attachment for `email_*`, link for `inmail_*`** (AGENTS.md §2.1).
  An `email_*` template that ships a resume sets
  `default_attachment: data/your_resume.pdf` and its body says the resume is
  attached, carrying the portfolio link only, **no resume URL**. Its `inmail_*`
  counterpart is the same message with the resume link swapped back into the
  body, because LinkedIn cannot carry an attachment.
- Skim a close existing template first (`cli.py templates show <name>`) and
  mirror its structure rather than inventing a new shape.

## Author, then validate

Write the YAML yourself: you control wording, structure, and comments. Save it
into `templates/`, then validate.

```bash
# 1. Write templates/email_<purpose>.yaml with the schema above (Write tool).
# 2. Validate it:
uv run python cli.py templates validate email_<purpose>
# 3. Confirm it loads/lists:
uv run python cli.py templates list
uv run python cli.py templates show email_<purpose>
```

`templates validate` runs the declared==used check and reports errors without
modifying the file, so your formatting and comments are preserved.

## Workflow checklist

1. Clarify with the user: channel (email vs inmail), purpose, audience/tone,
   and which variables the message needs. Ask if unclear — don't guess the
   variable set.
2. Pick the correct name prefix and a descriptive slug.
3. Author the YAML.
4. Ensure declared==used balance and HTML/plain-text rules for the channel.
5. `cli.py templates validate <name>` until clean.
6. Show the user the final template (`templates show`) and confirm before
   considering it done.

## Where this writes — templates/ is the exception

Unlike scraped/operational output (which goes to `runs/`, git-ignored),
templates are **committed source** and belong in `templates/`. This is the one
place a skill legitimately writes reusable files. Never put a template in
`data/`, `runs/`, or the repo root.

## Related

- `wingmate` skill — renders/drafts/sends templates, and holds the Naming
  Rule and env checks. See its `## Template Naming Rule`.
- `gmail-draft` skill — the HTML body-composition rules an `email_*` template's
  `body_template` must follow.
- `data/identity.yaml` `public:` — sender identity, real links, tone rules, and
  `forbidden_phrases`. Never write a value from the `private:` section into a
  template body (AGENTS.md §12.1).
