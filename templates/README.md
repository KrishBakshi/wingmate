# `templates/` — what gets said

One `.yaml` file per message. The filename stem **is** the template name
(`templates/email_intro_outbound.yaml` → `email_intro_outbound`), which is how
every CLI command refers to it.

Templates are the source of truth for **wording**. `data/` is the source of truth
for **facts**. An agent working in this repo fills placeholders and does not
rewrite the sentences around them, which is what makes outbound from this repo
consistent enough to be worth reviewing.

This is also the gate: `create_draft` and `send_email` refuse a body that does
not reproduce a template's fixed wording (see AGENTS.md §6.1). So "write a
better email" here means "write a better template", not "write around it".

## What ships

| File | Channel | Use |
|---|---|---|
| `email_intro_outbound.yaml` | email | The seed. A short introduction to someone at a company you want to work with. |
| `inmail_intro_outbound.yaml` | LinkedIn | The same message under a 300-character budget. |

Two files on purpose. They demonstrate the channel-pair pattern (below) and
nothing more, so your second template has an obvious shape to copy.

## The naming prefix is the channel

| Prefix | Means |
|---|---|
| `email_*` | Full length. HTML body, sign-off expected. Gmail, or sustained chat. |
| `inmail_*` | Hard character budget (LinkedIn connection note ≈300). **Plain text, no HTML.** |
| `extra_*` | One-off campaign or event templates. Not evergreen. |

Never send an `email_*` body as a LinkedIn note. It will blow the limit, and the
HTML will render as literal `<p>` text.

## Channel pairs, and the attachment rule

An `email_*` template and its `inmail_*` counterpart should be the **same
message**. The one intended difference is how proof is delivered, because Gmail
carries a PDF and LinkedIn cannot:

| Channel | Proof | Body wording |
|---|---|---|
| `email_*` | PDF attached via `default_attachment` | link to the portfolio only, and say the resume is attached |
| `inmail_*` | nothing can be attached | the resume URL stays in the body |

Asked for "the LinkedIn version" of an email, produce that replica. Do not invent
different copy.

**To attach your resume:** drop the PDF into `data/`, then add to the email
template:

```yaml
default_attachment: data/your_resume.pdf
```

`cli.py draft` and `cli.py send` append it automatically. Point it at a file that
exists, or the draft call fails.

## The schema

Backed by `src/models/email_template.py` (pydantic). Missing or misspelled keys
fail validation.

```yaml
name: email_intro_outbound        # slug: lowercase, digits, underscores. Must match the filename stem.
meta:
  title: Introduction — Outbound  # human-readable
  description: |                  # why this template exists and when to pick it
    ...
variables:                        # every placeholder used below must be declared here
  - recipient_name
  - company
system_instruction: |             # guidance to the agent, specific to THIS template
  ...
subject_template: "RE: Engineering at {company}"
body_template: |                  # the message. email = HTML, inmail = plain text.
  <p>Hi {recipient_name},</p>
# default_attachment: data/your_resume.pdf   # optional; omit if none
```

`meta.description` and `system_instruction` are internal notes. The recipient
never sees them, so write them for the agent, at length if it helps. There is no
model API in this repo, so `system_instruction` is read by whatever agent is
composing, not sent to a provider.

## The one hard validation rule: declared == used

`TemplateRepository.validate_template` enforces a **two-way** match between
`variables:` and the `{placeholders}` in `subject_template` and `body_template`:

- Every `{placeholder}` used must be declared (else: *used but not declared*).
- Every declared variable must appear somewhere (else: *declared but unused*).

Placeholders are single braces, `{name}`, not `{{name}}`.

```bash
uv run python cli.py templates validate email_intro_outbound
```

## Writing a new one

1. **Copy the closest existing template.** `cli.py templates show <name>`, then
   start from that file. Inventing a new shape each time is how a template set
   stops being a template set.
2. **Pick the prefix by channel**, and a slug that says the situation:
   `email_hiring_manager`, `email_referral_ask`, `inmail_short_interested`.
3. **Choose the variable set deliberately.** Every variable is a question
   someone has to answer before the email can go out. Six is comfortable, ten is
   a chore, and any variable you find yourself filling with the same value every
   time belongs in the fixed wording instead.
4. **Write the body in the channel's format.** HTML with one `<p>` per paragraph
   for email, real `<a href>` anchors (a bare URL renders as dead text in Gmail's
   HTML view), plain text for inmail.
5. **Respect `logic_rules` in `data/identity.yaml`** — the tone, the subject
   pattern, and `forbidden_phrases`.
6. **Validate, render, read it out loud.**

```bash
uv run python cli.py templates validate email_your_template
uv run python cli.py render email_your_template --field recipient_name="Alex" --field ...
```

7. **Add the `inmail_*` counterpart** if the message has a LinkedIn life.

There is a `template-builder` skill that does all of this with you. Templates
are hand-authored, by you or by the agent, and then validated. There is no
generator command, and no model is called to write one.

## Iterating

Templates are meant to be edited, and the honest signal for editing them is
repetition:

- **If you correct the same sentence in Gmail twice, fix the template.** That
  correction is the template being wrong, not the draft.
- **If you overrode the gate to send something off-template, write that wording
  down as a template.** A block usually means the right fix is a new template,
  not a wider override.
- **If a variable is always the same value, hard-code it.** If a fixed sentence
  keeps needing to change, make it a variable.
- **When `identity.yaml` changes**, check whether any template's example values
  or embedded links went stale with it.
- **Prune.** A template you have not picked in three months is one more thing the
  agent has to choose between. Delete it; git remembers.

Ask the agent to do this work. "The intro email is too long, tighten the third
paragraph and keep everything else" is a normal instruction, and it knows to
validate afterwards.

## House rules that are enforced in code

- **No em dashes** in `subject_template` or `body_template`. They read as machine
  written. Pinned by `guardrails/check_send_template_gate.py`. Internal fields
  are exempt. If you disagree, that check is one function and deleting it is a
  legitimate choice, just make it deliberately.
- **Never invent** a link, an email address, a metric, or a product fact in a
  template body. Real values only, from `data/` or from the user.
- **Templates are committed source.** Never write a template into `data/`,
  `runs/`, or the repo root.
