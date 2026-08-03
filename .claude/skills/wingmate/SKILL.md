---
name: wingmate
description: Drive the Wingmate app (YAML templates, keyword-based variable extraction, Gmail drafts/sends, Excel batch runs) through the repo CLI. Use this skill when the user asks to list/show/validate templates, render a cold email, create or send a Gmail draft, or run a batch of drafts from a spreadsheet in this workspace.
---

# Wingmate Skill

Use the repo CLI as the single operational interface. Every command prints JSON. Non-zero exit codes indicate failure.

## When To Use This Skill

Trigger when the user asks to:

- list, show, or validate email templates in this repo
- render a subject/body from a template with given variables
- draft an email from a natural-language prompt (keyword extraction, see below)
- create a Gmail draft or send an email via the Gmail API
- preview or run a batch of drafts from an Excel/CSV
- author a new YAML template (hand off to the `template-builder` skill)

There is no model API in this repo. Draft by reading the template YAML and
substituting variables extracted from the user's prompt, as described in
"Drafting From a Natural-Language Prompt" below. You are the model.

## Template Naming Convention (Must Follow)

Templates in `templates/` use a filename prefix to indicate the channel and
constraints. Choose the right category before picking a template.

- `email_*` — Full-length message. Regular email (Gmail API) or sustained
  LinkedIn chat. HTML allowed. Sign-off expected.
- `inmail_*` — Short-form outbound with hard character limits. LinkedIn
  connection note (~300 chars), LinkedIn InMail, SMS, or any channel with
  tight budgets. Plain text, no HTML, short sign-off.
- `extra_*` — Temporary / special-event templates. One-off campaigns or
  launches. Not evergreen; may be removed later.

Rules:

1. Pick `email_*` for email and long-form chat.
2. Pick `inmail_*` for character-limited channels. Keep rendered body within
   the channel's character limit.
3. Pick `extra_*` only when the user mentions that specific event/campaign.
4. Never reuse `email_*` body as a LinkedIn connection note — it will be too long.

## Core Command Surface

Always invoke via:

```bash
uv run python cli.py <command> [subcommand] [flags]
```

Primary commands:

- `templates list`
- `templates show <name>`
- `templates validate [<name>]`
- `render <name> --field key=value ...`
- `draft <name> --to <email> --field ... [--attach <file>]`
- `send <name> --to <email> --field ... [--attach <file>]`
- `drafts list [--max-results N]`
- `batch preview --file <xlsx|csv> --template <name>`
- `batch run --file <xlsx|csv> --template <name> [--attach ...]`
- `batch sample --template <name> --out <path.xlsx>`

New templates are authored by hand and validated with `templates validate`.
See the `template-builder` skill.

## Required Workflow

1. Discover with `templates list`.
2. Filter by prefix (`email_`, `inmail_`, `extra_`) based on channel intent.
3. Inspect variables via `templates show <name>`.
4. Extract variable values from the user's prompt using the keyword
   extraction procedure below. Ask for anything you cannot extract.
   Do not invent values.
5. Preview output using `render` before any Gmail side effect.
6. For `inmail_*` output, verify rendered body stays under the channel's
   character limit before using it.
7. For batches: always run `batch preview` before `batch run`.
8. Only use `send` when the user explicitly asks to send. Prefer `draft`.
9. On failure (non-zero exit code), surface the full JSON error payload.

## Drafting From a Natural-Language Prompt (Keyword Extraction)

When the user gives a free-form prompt (e.g. "email Alex at Acme about the AI Engineer role I saw
on LinkedIn"), you — not an external model — read the template YAML and fill
its variables from keywords in the prompt.

### How to read the template YAML

Each file in `templates/` has this shape:

- `variables:` — the list of placeholder names the template expects. This is
  the source of truth for what must be extracted; its length is the total
  expected keyword count.
- `subject_template:` / `body_template:` — the text to render, with
  `{variable}` placeholders. Substitute values only; never rewrite the
  surrounding wording.
- `system_instruction:` — per-template guidance written for you, the agent
  composing the message. Read it; it is not sent anywhere.

### Extraction procedure

1. Read the chosen template's YAML (`templates/<name>.yaml`) and note its
   `variables` list.
2. Scan the user's prompt and classify each piece of information against a
   variable name: person names → `recipient_name`, company names → `company` /
   `company_name`, what the company builds → `target_product` /
   `main_product`, and so on. Use only what the prompt states or clearly
   implies.
   The project fields (`my_project`, `domain_context`, `metric_impact`) are the
   exception: they do not come from the prompt, they come from
   `data/identity.yaml` `public.projects[]`. Pick the entry whose `relevance`
   overlaps the target's own words, not the one with the biggest number.
3. Verify completeness with a small Python check — count the classified
   keywords against the template's expected total:

   ```bash
   uv run python - <<'EOF'
   import json, yaml

   template = yaml.safe_load(open("templates/email_intro_outbound.yaml"))
   expected = template["variables"]

   # keywords classified from the user's prompt
   extracted = {
       "recipient_name": "Alex",
       "company": "Acme AI",
       "target_product": "inference infrastructure",
       "my_project": "a support triage agent",
       "domain_context": "tool calling over a ticket queue",
       # metric_impact not yet mapped from identity.yaml
   }

   found = [v for v in expected if extracted.get(v)]
   missing = [v for v in expected if not extracted.get(v)]
   print(json.dumps({
       "expected_total": len(expected),
       "extracted_total": len(found),
       "complete": len(found) == len(expected),
       "missing": missing,
   }, indent=2))
   EOF
   ```

4. Compare the counts. If `extracted_total < expected_total`, the prompt was
   insufficient: stop and follow up with the user, listing the exact
   `missing` variables and asking for that context. Do not guess, do not
   substitute placeholders, and do not render until every variable has a
   user-provided or prompt-derived value.
5. Once complete, pass the values to the CLI with `--field key=value` (or a
   `--fields-file`) and continue the normal render → draft flow.

## Template Naming Rule

When creating a template file, use the correct prefix:

- `email_<purpose>` for email / long-form chat
- `inmail_<purpose>` for LinkedIn notes, InMails, or SMS-like channels
- `extra_<campaign_or_event>_<purpose>` for temporary campaign templates

## Environment Checks

Before Gmail commands:

- `credentials.json` at repo root (OAuth client); `token.json` is written on first use.
- No API key is needed for anything in this repo.
- If imports fail, run `uv sync`.

## Safety Rules

- Do not print or log secrets (contents of `credentials.json`, `token.json`, `NOTION_TOKEN`).
- Do not modify template wording when rendering; only substitute placeholders.
- Do not auto-send. `send` requires explicit user intent.
- For batch operations, summarize preview before running.
- Stop and ask when a required template variable is missing.

## Data vs Runs — Where to Write Output

**Never write scraped, generated, or operational data into `data/`. Use `runs/`.**

- `data/` — stable personal knowledge (`resume.md`, `identity.yaml`, `projects.md`). Tracked in git. `identity.yaml` is split into `public:` (compose from this) and a gated `private:` section (AGENTS.md §6.2, §12.1).
- `runs/` — all operational output: scraped contacts, research JSONs, outbound drafts, batch results. **Git-ignored — never committed.**

When producing any output file (scrape result, draft list, batch export):
1. Write to `runs/<campaign_slug>/` or directly to `runs/`.
2. Never write to `data/`, `templates/`, or repo root.
3. Do not attempt to `git add` anything from `runs/`.

## Minimal Example

```bash
uv run python cli.py templates show email_intro_outbound

# target fields from the prompt; project fields from data/identity.yaml
uv run python cli.py render email_intro_outbound \
  --field recipient_name="Alex" \
  --field company="Acme AI" \
  --field target_product="inference infrastructure" \
  --field my_project="a support triage agent" \
  --field domain_context="tool calling over a ticket queue" \
  --field metric_impact="first response times going from hours to minutes"

uv run python cli.py draft email_intro_outbound \
  --to alex@acme.com \
  --fields-file inputs.yaml

# LinkedIn connection note (character-limited channel: check the rendered length)
uv run python cli.py render inmail_intro_outbound \
  --field recipient_name="Alex" \
  --field company_name="Acme AI" \
  --field main_product="inference infrastructure" \
  --field my_work_and_impact="I built a triage agent that cut first response to minutes"
```

Reference: see `AGENTS.md` at the repo root for full documentation
(`AGENTS.md` is a symlink to the same file).
