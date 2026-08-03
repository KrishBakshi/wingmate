# AGENTS.md

> **This is the only instruction file. `CLAUDE.md` is a symlink to it.**
> Codex/Cursor read `AGENTS.md`, Claude Code reads `CLAUDE.md`; both resolve to
> these bytes. Edit `AGENTS.md`. Never replace the symlink with a real file, see
> §12.4.

Wingmate is a YAML-template-driven outbound email system with Gmail API
integration, driven entirely through a CLI. There is **no model API in this
repo**: rendering is deterministic placeholder substitution, and the
intelligence is you, the agent reading this.

Skills live in `.claude/skills/` (single source; `.agents/skills` and
`.cursor/skills` symlink to it): `wingmate`, `gmail-draft`, `template-builder`,
`notion-publisher`, `scrapling`, `find-recent-investment`.

**This repo ships as a seed.** The identity in `data/` belongs to a fictional
person, John Dev, and `templates/` holds one email and its LinkedIn counterpart.
Replacing that identity and growing that template set is the work, and §11 and
§12 are about how this file and this repo are supposed to change while you do
it. If you are an agent reading this on a fresh clone, start at §0.

| § | Covers |
|---|---|
| 0 | **First session on a fresh clone** — what to do before anything else |
| 1 | Entry point, setup, env knobs |
| 2 | Template naming, and attachment vs link per channel |
| 3 | Decision flow: single draft vs campaign |
| 4 | CLI reference |
| 5 | Picking a template |
| 6 | Safe operation rules, **the send gate** and **the disclosure gate** (code-enforced) |
| 7 | File layout; `data/` vs `runs/` |
| 8 | Outbound pipeline: scrape → store → render → track |
| 9 | Commit convention |
| 10 | End-to-end examples |
| 11 | **Learning the user** — scratchpads, the 3rd-generation review, and how this file evolves |
| 12 | Standing instructions — the seed defaults, and where the user's own go |

## 0. First session on a fresh clone

If `data/identity.yaml` still says **John Dev**, the repo has not been made
anyone's yet. Do not draft an email for a real recipient until it has been.

Say so, then offer to walk the user through it. In order:

1. **Fill the identity ledger.** Read `data/README.md`, then interview the user:
   name, one-line creds, portfolio, and three to eight projects with a real
   metric each. Write `data/identity.yaml`, `data/resume.md`, `data/projects.md`.
   Ask; never invent a metric, an employer, or a link.
2. **Rewrite the seed template in their voice.** `templates/email_intro_outbound.yaml`
   is deliberately plain. Show it to them, ask what is wrong with it, and edit
   until they would actually send it. Then update the `inmail_*` counterpart to
   match. `templates/README.md` is the guide.
3. **Set up Gmail** only when they are ready to draft: `credentials.json` per the
   README, then one `cli.py drafts list` to trigger the OAuth flow.
4. **Record what you learned about them** in §12.5 of this file, without being
   asked. That is the point of §11.

Keep it conversational. This is an interview, not a form.

## 1. Entry point & setup

Prefer the CLI over direct Python imports. All commands print JSON to stdout;
non-zero exit means failure.

```bash
uv run python cli.py <command> [subcommand] [flags]
```

Before any Gmail command: `credentials.json` at the repo root (Google OAuth
client; the first Gmail call opens a browser flow and writes `token.json`), and
`uv sync` if imports fail.

`.env` knobs:

| Key | Default / note |
|---|---|
| `TEMPLATES_DIR` | `templates/` |
| `GMAIL_CREDENTIALS_PATH` / `GMAIL_TOKEN_PATH` | `credentials.json` / `token.json` |
| `NOTION_TOKEN` / `NOTION_OUTBOUND_DB_ID` | required for Notion publish/sync |
| `TEMPLATE_MATCH_THRESHOLD` | send-gate pass mark, `0.75` (§6.1) |
| `TEMPLATE_MATCH_MIN_BLOCK` | shortest counted text run, `8` |
| `RESUME_PHONE` | phone number, kept out of every tracked file (§12.2) |

**Package layout:** modules live directly under `src/` — there is no
`wingmate` package, and the project is not installed
(`[tool.uv] package = false`). `cli.py` puts `src/` on `sys.path`. Any inline
script must bootstrap it first or die with `ModuleNotFoundError`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path("src").resolve()))
from services.gmail_service import GmailService
```

## 2. Template naming = channel

The filename prefix in `templates/` declares the channel. Respect it when
selecting; never send an `email_*` body as a LinkedIn note (it will blow the
character limit and render its HTML as literal text).

- **`email_*`** — full length, HTML allowed, sign-off expected. Email via Gmail,
  or sustained chat.
- **`inmail_*`** — hard character budget (LinkedIn connection note ≈300 chars),
  plain text, no HTML, no long sign-off. Also InMail and SMS-like channels.
- **`extra_*`** — one-off campaign or event templates. Not evergreen; use only
  when the user names that event.

If a required variable is missing, ask. Never invent values.

### 2.1 Proof of work: attached for email, linked for InMail

An `email_*` template and its `inmail_*` counterpart are **channel pairs of the
same message**. The only intended difference is how proof is delivered, because
Gmail carries a PDF and LinkedIn cannot:

| Channel | Resume | Body wording |
|---|---|---|
| `email_*` | PDF attached via `default_attachment` | portfolio link only, and the body says the resume is attached |
| `inmail_*` | cannot be attached | the resume URL stays in the body |

Asked for "the LinkedIn version" of an email, produce that replica: same claims,
resume link swapped back in, trimmed to budget. Do not invent different copy.

The seed email template ships with **no** `default_attachment`, because there is
no resume PDF in a fresh clone. Once the user drops one in `data/`, add it and
change the proof line to match (`templates/README.md` has the exact steps).

## 3. Decision flow

**Single draft** — `templates list` → filter by prefix → `templates show <name>`
for variables → collect values → `render` to preview (always, before any Gmail
side effect) → check `inmail_*` length against the channel limit → `draft`
(preferred) or `send` only on explicit intent. Bulk: `batch preview` before
`batch run`.

**Campaign** (research, LinkedIn outbound, follow-up tracking) — use §8. Read
`.claude/skills/notion-publisher/SKILL.md` and `.claude/skills/scrapling/SKILL.md`
first; do not jump to `render` or `batch run` without prospect data in
`runs/<campaign>/` or Notion.

## 4. CLI reference

```bash
# Templates
uv run python cli.py templates list
uv run python cli.py templates show <name>
uv run python cli.py templates validate [<name>]
uv run python cli.py templates match [<name>] --body-file body.html   # §6.1 gate check
uv run python cli.py templates match --body "<p>Hi …</p>" [--threshold 0.6]

# Render — no side effects. Strict placeholder substitution, nothing more.
uv run python cli.py render <name> --field k=v [--field …]
uv run python cli.py render <name> --fields-file fields.json

# Gmail. --to optional for draft, required for send.
uv run python cli.py draft <name> --to a@b.com --field … [--attach f.pdf]
uv run python cli.py send  <name> --to a@b.com --field … [--attach f.pdf] [--allow-unmatched]
# both also take --allow-sensitive (§6.2), and only after the user has said yes
uv run python cli.py drafts list [--max-results 10]

# Batch — columns = template variables + an `email` column. `run` only drafts.
uv run python cli.py batch sample  --template <name> --out sample.xlsx
uv run python cli.py batch preview --file rows.xlsx --template <name> [--max 3]
uv run python cli.py batch run     --file rows.xlsx --template <name> [--attach …] [--delay 0.25]

# Identity — public section is free; private is gated (§6.2)
uv run python cli.py identity show [--private] [--allow-sensitive]
uv run python cli.py identity scan --body-file body.html [--template <name>]

# Regeneration counter (§11.2)
uv run python cli.py monitor status [--template <name>] [--to a@b.com]
uv run python cli.py monitor reset  [--template <name>] [--to a@b.com]

# New templates are hand-authored, then validated. Use the template-builder
# skill; name with the channel prefix (§2). There is no generator command.
```

`send` is gated (§6.1); `--allow-unmatched` is legitimate only after the user
answers the confirmation question a blocked send returns.

## 5. Picking a template

The seed ships two: `email_intro_outbound` and its LinkedIn counterpart
`inmail_intro_outbound`. Until more exist, the choice is just the channel.

As the set grows, keep a table here, one row per use case, naming the **one**
canonical template for it. That table is what stops an agent from picking a
near-miss template six months from now. Add a row whenever you add a template,
and say what makes it the right choice:

| Use case | Template | Notes |
|---|---|---|
| First contact by email | `email_intro_outbound` | Short introduction, portfolio CTA, no calendar ask. |
| LinkedIn connection note | `inmail_intro_outbound` | ≤300 chars, plain text. Sent **manually by the user**, never automated. |

## 6. Safe operation rules

1. Never commit or print API keys, credentials, or `token.json` contents.
2. Do not `send` unless the user explicitly asks to send.
3. "Draft" is an instruction to act, not to propose. Create it, then report
   (§12.1).
4. `batch preview` before `batch run`, and surface the results.
5. On non-zero exit, surface the JSON error payload.
6. `templates/*.yaml` is the source of truth for wording. Substitute declared
   placeholders only; do not paraphrase a template body.
7. Never invent recipient names, product facts, metrics, links, or emails.
8. Facts about the sender come from `data/identity.yaml` first, then
   `data/resume.md` — read them before composing (§11.3). Only the `public`
   section is outbound material; the `private` section is gated (§6.2, §12.1).

### 6.1 The template gate on drafts and sends (enforced in code, not by you)

**Both** `GmailService.create_draft` and `GmailService.send_email` refuse a body
that does not match a template in `templates/`. The gate lives in the service,
not the CLI, so it also holds for an inline script that imports `GmailService`
directly — which is exactly the path that lets an off-template email slip out.
Drafting is where the wording is decided, so it is gated first; by the time a
body reaches `send_email` it has usually already been read and approved.

How `src/services/template_matcher.py` scores: the body is normalized (HTML
stripped, whitespace and case flattened) and measured against each template's
**fixed wording** — the text outside `{placeholders}`. The score is how much of
that wording the body reproduces, so personalization does not hurt it but writing
from scratch does. A rendered template scores `1.0`; free-form text usually lands
under `0.5`. Pass mark: `TEMPLATE_MATCH_THRESHOLD` (default `0.75`). Runs shorter
than `TEMPLATE_MATCH_MIN_BLOCK` (8) chars do not count, so incidental words
cannot add up to a pass.

Below the mark nothing is sent; `send_email` returns
`{"success": false, "requires_confirmation": true, "question": "This particular
email is not in our templates. Should we still send it?", "match": {…}}` with the
closest template and score. It **fails closed** — an unreadable or empty
`templates/` blocks rather than allows.

When a draft or send comes back blocked:

1. Put the `question` to the user **verbatim** and wait. Do not decide for them.
   (The verb matches the action: "still draft it?" vs "still send it?".)
2. On yes, retry with `allow_unmatched=True` / `--allow-unmatched`.
3. On no, stop — or better, offer to make the wording a template
   (`template-builder` skill) so the next one matches by construction.

A successful write reports `match` plus `drafted_without_template_match` /
`sent_without_template_match`, so an approved exception stays visible in the
output. A body you composed yourself rather than rendering will normally fail
this check, which is the point: check it with `templates match` first, and treat
a block as a prompt to write a template, not as a nuisance.

Behaviour is pinned by `guardrails/check_send_template_gate.py`. Run it after
touching the matcher, the templates, or `send_email`:

```bash
uv run python guardrails/check_send_template_gate.py
```

### 6.2 The disclosure gate on private identity data

Retrieval and generation are separate layers, and the gate sits between them:

```text
retrieval (identity.yaml public / private)
    -> DISCLOSURE GATE (guard_disclosure)
        -> generation (render / draft / send)
```

`src/services/identity_service.py` reads the two sections of
`data/identity.yaml`. `load_public()` is free. `load_private()` refuses without
`allow_sensitive=True` and **withholds the values while it refuses** — it returns
the field *names* so the user knows what is being asked for, nothing more.

`guard_disclosure` then re-checks the finished body, so a private value that
reached the text another way (typed from memory, copied from an old thread,
invented by the model) is still caught at the Gmail boundary. It fires on two
things: exact values from the `private` section (digits compared separately, so a
reformatted phone number still trips it) and pattern rules for shapes that are
never volunteered — phone numbers, CTC/LPA figures, notice periods, government
IDs, dates of birth. The patterns hold with no `private` section on disk, so the
gate **fails closed** on a fresh clone.

A template's own fixed wording is exempt: if a template deliberately publishes a
contact address, that was approved once when the template was written. The same
address in a body from another template is a new disclosure and blocks.

Blocked writes behave exactly like §6.1: put the `question` to the user verbatim,
wait, and only on yes retry with `allow_sensitive=True` / `--allow-sensitive`. A
successful write reports `disclosures` plus `drafted_with_private_data` /
`sent_with_private_data`.

```bash
uv run python cli.py identity show [--private] [--allow-sensitive]
uv run python cli.py identity scan --body-file body.html [--template <name>]
uv run python guardrails/check_identity_disclosure_gate.py
```

## 7. File layout

| Path | Role |
|---|---|
| `cli.py` → `src/cli.py` | entry point / CLI logic |
| `src/services/` | business logic (email, gmail, batch, template_matcher, identity) |
| `templates/` | YAML templates (schema and guide: `templates/README.md`) |
| `data/` | stable personal knowledge — `identity.yaml`, `resume.md`, `projects.md` (tracked; guide: `data/README.md`) |
| `runs/` | all operational output (git-ignored) |
| `guardrails/` | outbound-safety checks, `check_*` naming, pytest configured in `pyproject.toml` |
| `assets/` | repo artwork. `mark.svg` is the Wingmate mark, shared with the site favicon |
| `.claude/skills/` | **single source for every skill** (`.agents/skills`, `.cursor/skills` symlink here) |

**Never write operational or scraped data into `data/`.** It goes to
`runs/<campaign_or_task>/`: scraped pages, contact research, `prospects_*.json`,
`outbounds.json`, batch output, draft logs. `runs/` is git-ignored and never
committed — do not commit from it, and never write to `data/`, `templates/`, or
the repo root instead.

## 8. Outbound pipeline — scrape → store → render → track

For scraping job boards and company sites, building prospect lists,
personalizing outbound, tracking sends, and follow-ups. Four layers, fixed order,
defined data shape per layer. Do not skip ahead.

**Read first:** `notion-publisher/SKILL.md` (schemas: `schema.md`, walkthroughs:
`examples.md`) and `scrapling/SKILL.md`.

| Layer | Tool | Output |
|---|---|---|
| 1 Scrape | Scrapling | `runs/<campaign>/scrape/`, `prospects_raw.json` |
| 2 Store | `runs/` + Notion API | `prospects_enriched.json`, Notion **Outbound Pipeline** rows (Status `Researched`) |
| 3 Render | `cli.py render` | `outbounds.json`, Notion `Rendered Body` (Status `Draft Ready`) |
| 4 Track | Notion | status, sent dates, follow-up flags |

Campaign folder:

```text
runs/<campaign_slug>/
  manifest.yaml            # source URL, channel, template, follow_up_days
  scrape/listing.md, scrape/companies/*.md
  prospects_raw.json       # layer 1
  prospects_enriched.json  # layer 2 — canonical render input
  outbounds.json           # layer 3
  sync_log.json
```

**Layer 1 — Scrape.** Escalate as needed: `scrapling extract get` (static) →
`fetch` (JS) → `stealthy-fetch` (anti-bot). Always pass `--ai-targeted`. Parse
scrape files into `prospects_raw.json`; never leave data only in markdown.
Extract only what is on the page; missing contact info is `null`.

```json
{ "company_name": "Acme AI", "role_title": "Founding ML Engineer",
  "company_url": "https://acme.example", "source_url": "https://example.com/jobs/123",
  "source_type": "job_board", "scrape_notes": "seed stage; mentions RAG in JD" }
```

`source_type` ∈ `job_board` | `company_site` | `linkedin` | `manual`.

**Layer 2 — Store.** `prospects_enriched.json` is the working copy for agents;
Notion is the system of record for status and follow-up.

```json
{ "id": "acme-ai-jane-doe", "recipient_name": "Jane", "company_name": "Acme AI",
  "role_type": "founding ML engineer", "main_product": "embedding search for devtools",
  "linkedin_url": "https://linkedin.com/in/janedoe", "email": null,
  "source_url": "…", "source_type": "job_board",
  "research_notes": "Series A; first ML hire; blog mentions hybrid search",
  "project_id": "docs_rag", "my_project": "a documentation RAG assistant",
  "domain_context": "embeddings and retrieval evaluation over internal docs",
  "metric_impact": "citation accuracy from 61% to 88% on a 200-question eval set" }
```

- `recipient_name`, `company_name`, `main_product` come from the scrape or the
  user. Never invented.
- `my_project` / `domain_context` / `metric_impact` map from
  `data/identity.yaml` `projects[]` via `relevance` and `industrial_hook`. Never
  invent metrics.
- `id` = `{company-slug}-{contact-slug}` for cross-file joins.
- Dedup Notion on `linkedin_url` → `email` → name+company.
- Reading back: if the user says "generate outbound for prospects in Notion",
  query Notion, map rows to this shape, then go to layer 3.

**Layer 3 — Render.** `render` does not read Notion or scrape files; the agent
maps a prospect record to `--field` values. Confirm variables with
`templates show <name>`. Standard mapping for the seed templates:

| Template | Mapping |
|---|---|
| `email_intro_outbound` | `company`←`company_name`, `target_product`←`main_product`, `my_project`/`domain_context`/`metric_impact` direct |
| `inmail_intro_outbound` | `company_name`←`company_name`, `main_product`←`main_product`, `my_work_and_impact`← one short clause from `my_project`+`metric_impact` |

Append each result to `outbounds.json` (`id`, `template`, `channel`,
`render_fields`, `rendered_subject`, `rendered_body`, `char_count`, `status`,
`notion_page_id`), then update the Notion row: Status `Draft Ready`,
`Rendered Body`, `Char Count`, `Template`. Email channel only:
`cli.py draft <template> --to <email> --fields-file …`.

**Layer 4 — Track.** Status flow: `Prospect` → `Researched` → `Draft Ready` →
`Sent` → `Replied` | `Closed`. On user send: Status `Sent`, `Sent Date`,
`Follow-up Due`. On bump: `Follow-up Sent` = true, `Follow-up Date`. Follow-up
query: Status `Sent` AND `Follow-up Sent` false AND `Follow-up Due` ≤ today.

**Channel routing:** LinkedIn notes are sent **manually by the user in the
LinkedIn UI, never automated**. Email goes through Gmail `draft`/`send`. Do not
use `batch run` for LinkedIn campaigns; it only creates Gmail drafts.

**Notion setup (one-time, user):** create an integration at
notion.so/my-integrations, create the **Outbound Pipeline** DB per `schema.md`,
share it with the integration, set `NOTION_TOKEN` + `NOTION_OUTBOUND_DB_ID`.
Until `notion` CLI subcommands exist, use the API directly per the skill docs.
Never commit `NOTION_TOKEN` or anything from `runs/`.

## 9. Commit convention

Capitalized action prefix + colon + short imperative summary, ≤~72 chars, no
trailing period. One logical change per commit; never bundle unrelated changes.
Use the body for bullets when a commit touches several things.

`Add:` new file/template/skill/feature · `Update:` change something existing ·
`Fix:` bug or wrong behaviour · `Remove:` delete · `Refactor:` restructure
without behaviour change · `Docs:` documentation only · `Chore:` tooling, deps,
housekeeping.

```text
Add: hiring-manager email template
Update: reframe the intro template's opening hook
Fix: template path resolution after flattening src layout
Remove: deprecated founder outbound variant
```

## 10. End-to-end examples

```bash
# Single intro email: discover → preview → draft
uv run python cli.py templates show email_intro_outbound
uv run python cli.py render email_intro_outbound \
  --field recipient_name="Alex" --field company="Acme AI" \
  --field target_product="LLM inference infrastructure for enterprise" \
  --field my_project="a support triage agent" \
  --field domain_context="tool calling over a 400-ticket per week queue" \
  --field metric_impact="first response times going from hours to minutes"
# same fields, plus --to, to create the draft:
uv run python cli.py draft email_intro_outbound --to alex@acme.example --field …

# LinkedIn connection note (≤300 chars — check the rendered length)
uv run python cli.py render inmail_intro_outbound \
  --field recipient_name="Alex" --field company_name="Acme AI" \
  --field main_product="LLM inference infrastructure" \
  --field my_work_and_impact="I built a triage agent that cut first response to minutes"

# Campaign (§8): scrape → enrich → publish → render → track
scrapling extract get "https://example.com/jobs" \
  runs/example-campaign/scrape/listing.md --ai-targeted
# → prospects_raw.json → enrich w/ data/identity.yaml → prospects_enriched.json
# → publish to Notion (Researched) → render per row → outbounds.json (Draft Ready)
# → user sends → Notion (Sent, Follow-up Due)
```

## 11. Learning the user

This repo is supposed to get better at sounding like its owner. That does not
happen by accident, so it has three mechanisms, and using them is part of the
job rather than an optional extra.

### 11.1 Pay attention to how they write, not just what they ask for

Every message the user sends is a sample of their voice. Their edits to a draft
are a stronger sample, and their edits to a **template** are the strongest one.

- **Notice the diff.** When the user rewrites something you produced, the
  difference between your version and theirs is the lesson. Sentence length,
  contractions, whether they hedge, how they open, how they sign off, what they
  refuse to claim about themselves. Name the pattern to yourself before moving
  on.
- **Ask once, not every time.** A single clarifying question about voice
  ("shorter and blunter, or is it the specific phrasing you didn't like?") is
  worth more than five more rejected drafts.
- **Write it down, in the right place.** A correction about *wording* belongs in
  the template. A correction about *facts* belongs in `data/identity.yaml`. A
  correction about *how you should work* belongs in §12.5 of this file. A
  one-off observation not yet worth committing to belongs in the relevant
  skill's `SCRATCHPAD.md`.
- **Apply it up front next time.** A preference you had to be told twice is a
  preference you failed to encode the first time.

Do this without being asked. "Should I remember that?" is the wrong question.
Write it down, tell the user in one line where you put it, and move on.

### 11.2 The 3rd-time rule

`cli.py draft` auto-records every draft to `runs/draft_monitor.json` keyed by
`template + recipient`; the draft output carries a `monitor` block that sets
`over_threshold` on the **3rd** generation (`count >= 3`) of the same email. At
that point STOP and work the checklist in the relevant `SCRATCHPAD.md`
(`gmail-draft` or `wingmate`):

1. **Missed pattern** — is the user repeating a correction? Encode it as a
   default instead of being corrected again.
2. **Hallucination** — inventing links, metrics, facts, contacts?
3. **Identity drift** — does it still match the mapped `projects[]` entry?
4. **Template mismatch** — right template for the channel and intent?

Record the incident and fix, then `monitor reset --to <email>`. `SCRATCHPAD.md`
files are git-ignored living memory, not committed artifacts. If one is missing,
create it from the structure the skill describes.

Three regenerations of the same email is the system telling you something is
wrong upstream. Do not just try harder on the fourth.

### 11.3 Source of truth, and keeping examples fresh

Order of authority for any claim about the sender — a metric, a project, a
credential, an employer:

1. **`data/identity.yaml`**, `public` section. `sender.creds` for how to describe
   them, `projects[]` for `metric`, `industrial_hook`, `relevance`, `link`. The
   `private` section is not composition material (§12.1).
2. **`data/resume.md`**, for anything the ledger does not carry.
3. Nothing else. Never a template's example text, never a past draft, never
   memory of an earlier session.

Read the ledger *before* composing, not after. Where two sources disagree, use
the ledger and **tell the user about the conflict** rather than silently picking
one.

**Pick the project by `relevance`, not by size.** Extract the domain words from
the target's own posting, match them against every `projects[].relevance`, and
use the entry that actually overlaps. A bigger metric on a less relevant project
is the wrong trade; `relevance` exists to make this decision for you.

**Keep skill examples fresh.** The `--field` example values in `SKILL.md` files
derive from `data/identity.yaml` `projects[]`. When the ledger changes, refresh
them and log it in that skill's `SCRATCHPAD.md`. Never invent example metrics.

## 12. Standing instructions

§12.1 to §12.4 are the defaults this repo ships with. They exist because each one
is a mistake that is easy to make and expensive to make. §12.5 is empty on
purpose: it is where **the user's own** durable instructions go.

### 12.1 Personal data is never volunteered — being asked is not consent

The situation this exists for: a recruiter post asks applicants to reply with
contact number, current CTC, expected CTC, notice period and location. The right
move is to send none of it and say so. Generalized: **only work information goes
out.** Work information is publicly checkable — employers, projects, metrics,
proof of work. Personal information is what only the user knows, and a form
asking for it does not make it shareable.

- `data/identity.yaml` has a `public` section and a `private` section. Compose
  from `public` only. Never quote, summarize, or paraphrase anything under
  `private` into a body, a subject, an attachment, or a Notion row.
- A post that requests a details block gets the normal template. Say in your
  report that you left the block out and why. Do not fill it partially.
- If the user wants those details sent, they say so, and then the values come
  from `private` via `--allow-sensitive`. Not from your memory of an old thread,
  and never estimated or inferred. An empty field stays empty; ask.
- The gate (§6.2) enforces this at the Gmail boundary. Relay its question
  verbatim, never pre-emptively pass the override, never edit the pattern rules
  to get a body through.

### 12.2 The phone number stays out of `.md` files and outbound copy

A phone number must not appear in any `.md` file or template: not
`data/resume.md`, not a skill example, not a rendered body or sign-off.

- **The resume PDF may keep it, and should.** That is the intended channel:
  recruiters get it from the attachment.
- **How it reaches the PDF:** keep it in `.env` as `RESUME_PHONE` (git-ignored)
  and inject it into the contact line at build time. That keeps the number out
  of every tracked file while the PDF still carries it.
- Contact details you write into outbound copy: email, portfolio link, LinkedIn.
  **No phone number**, even when a post asks for "your details".
- If something genuinely requires it, ask. Never recover it from git history or
  an old transcript.

### 12.3 No em dashes in anything a recipient reads

Em dashes read as machine written.

- Banned in every `subject_template` and `body_template`, in any free-form body
  you compose, and in a document you attach.
- Use a comma, a colon, parentheses, or start a new sentence. A comma is almost
  always the right substitute, and it is what a person would have typed.
- `meta.description` and `system_instruction` are internal notes, not
  recipient-facing, so an em dash there is harmless. The guardrail checks the
  recipient-facing fields only.
- Pinned by `check_no_em_dashes_in_recipient_facing_copy` in
  `guardrails/check_send_template_gate.py`. This one is a style default rather
  than a safety property: if the user disagrees, delete that check deliberately
  rather than leaving it failing.

### 12.4 One instruction file, one skills tree — nothing is mirrored by hand

Two instruction files kept in sync manually will drift, so both filenames resolve
to one document, and the same applies to skills:

| Path | Kind |
|---|---|
| `AGENTS.md` | the real file — edit this |
| `CLAUDE.md` | symlink → `AGENTS.md`, for Claude Code |
| `.claude/skills/` | the real skills tree |
| `.agents/skills`, `.cursor/skills` | symlinks → `../.claude/skills` |

1. **Edit `AGENTS.md` and `.claude/skills/` only.** One edit reaches every
   harness. Never write a second copy "for" another harness.
2. **Never replace a symlink with a real file or directory.** That re-creates the
   drift this removes.
3. If a Windows checkout or `core.symlinks=false` clone materializes a symlink as
   a text file containing a path, fix the clone (`git config core.symlinks true`,
   re-checkout). Do not commit copies.
4. **Record any new standing instruction under §12.5 without being asked.**
   "From now on…", "stop doing X", "don't ask me again about…" — those are
   durable, and one file means once is enough.
5. Keep this file tight. It is auto-loaded into every session, so when adding a
   rule, compress or replace what it supersedes instead of appending
   indefinitely.

### 12.5 The user's standing instructions

*Empty on a fresh clone. This is yours.*

Everything above is a default someone else chose. What goes here is what **you**
have told the agent, and it overrides the defaults where they conflict.

An agent working in this repo adds an entry here when the user says something
durable: a preference stated twice, a correction that clearly generalizes, a
"from now on", a rule about tone or timing or what never to claim. Write it as a
short subsection with the rule, one line of *why* (the why is what makes it
survive being re-read in six months), and how to apply it. Then say in one line
that you added it.

Delete entries that stop being true. This section is meant to be edited, not
appended to forever.
