---
name: notion-publisher
description: >-
  Track personalized company research and LinkedIn/email outbound in Notion.
  Scrape job boards and company sites into runs/, enrich prospects, render
  messages via Wingmate, publish rows to a Notion pipeline database, and
  manage follow-up status. Use when the user mentions Notion tracking, outbound
  CRM, prospect pipeline, follow-up reminders, job-board research, or publishing
  scrape results to Notion.
---

# Notion Publisher

Personalized outbound (especially LinkedIn connection notes) is hard to track
because each message is bespoke and sent outside Gmail. This skill defines a
**staging → render → publish → follow-up** pipeline:

| Layer | Role |
|-------|------|
| `runs/<campaign>/` | Git-ignored staging: scrape, research, rendered drafts |
| Wingmate CLI | Render `inmail_*` / `email_*` templates from enriched fields |
| Notion database | System of record: status, sent dates, follow-up flags |
| Scrapling | Discover prospects from job boards and company career pages |

Read [schema.md](schema.md) for the Notion property list and JSON file shapes.

## When To Use

Trigger when the user asks to:

- track outbound / follow-ups in Notion
- publish scraped job-board or company-site data to a table
- run a founder or hiring outreach campaign with per-prospect personalization
- find who still needs a follow-up
- sync `runs/` prospect files into Notion

Pair with:

- **wingmate** — template render and Gmail drafts (email channel only)
- **scrapling** — job-board and careers-page discovery

## Core Workflow

Copy this checklist and track progress per campaign:

```
Campaign: <slug>
- [ ] 1. Discover prospects (scrape → prospects_raw.json)
- [ ] 2. Research & enrich (→ prospects_enriched.json)
- [ ] 3. Map project hook from data/identity.yaml
- [ ] 4. Render personalized outbound (→ outbounds.json)
- [ ] 5. Publish / upsert rows to Notion
- [ ] 6. User sends on LinkedIn or via Gmail draft
- [ ] 7. Mark Sent + set Follow-up Due in Notion
- [ ] 8. On follow-up: render bump, send, mark Follow-up Sent
```

### Step 1 — Discover

Scrape the source (YC jobs, Wellfound, company `/careers`, LinkedIn job URL, etc.).
Write to:

```text
runs/<campaign_slug>/
  manifest.yaml       # source URL, date, template, channel
  prospects_raw.json  # minimal rows from scrape
```

`prospects_raw.json` minimum fields: `company_name`, `role_title`, `source_url`,
`source_type` (`job_board` | `company_site` | `linkedin` | `manual`).

Use Scrapling for protected pages. Never write scrape output to `data/`.

### Step 2 — Research & enrich

For each row, find:

- `recipient_name` (founder, hiring manager, or best contact)
- `linkedin_url` (dedup key when present)
- `main_product` / `target_product` (one line from site or job post)
- `research_notes` (bullet facts for personalization)
- `email` (optional; only if publicly listed)

Merge into `prospects_enriched.json`. Skip or flag rows missing
`recipient_name` or `company_name`.

Pick the best project match from `data/identity.yaml` `public.projects[]` based on
`relevance` and `industrial_hook`, then map it to the template fields:
the project itself → `my_project` / `domain_context`, and its `metric`
field → `metric_impact` (or `my_work_and_impact` for `inmail_*` templates).

### Step 3 — Render outbound

Channel → template (from the AGENTS.md §5 canonical list):

| Channel | Template | Notes |
|---------|----------|-------|
| LinkedIn connection note | `inmail_intro_outbound` | ≤300 chars; verify length |
| Email | `email_intro_outbound` | Gmail draft via wingmate |

The repo ships one template per channel. As you add more (a hiring-manager
variant, a referral ask, a campaign one-off), extend this table so the campaign
workflow keeps naming a specific template rather than choosing at render time.

Preview every row before publish:

```bash
uv run python cli.py render inmail_intro_outbound \
  --field recipient_name="Alex" \
  --field company_name="Acme AI" \
  --field main_product="LLM inference infra" \
  --field my_work_and_impact="I built a triage agent that cut first response to minutes"
```

Append results to `outbounds.json` with `rendered_body`, `char_count`,
`template`, and full `render_fields`.

For `inmail_*`, **reject or shorten** any body over the channel limit before
Notion publish.

### Step 4 — Publish to Notion

Upsert one Notion page per prospect. Use `linkedin_url` or
`company_name|recipient_name` as the dedup key — update existing rows instead
of duplicating.

Required env (add to `.env`, never commit):

```text
NOTION_TOKEN=<integration secret>
NOTION_OUTBOUND_DB_ID=<database id>
```

Notion setup (one-time, user):

1. Create an internal integration at https://www.notion.so/my-integrations
2. Duplicate or create the **Outbound Pipeline** database (see schema.md)
3. Share the database with the integration (••• → Connections)
4. Copy database ID from the URL

Publish via Notion API (`notion-client` Python package or REST). Map JSON
fields to Notion properties per schema.md.

On success, write `notion_page_id` back to `outbounds.json` and
`sync_log.json` with `last_synced_at`.

### Step 5 — Send (human step)

LinkedIn notes are sent manually in the LinkedIn UI. Email can use:

```bash
uv run python cli.py draft email_intro_outbound --to ... --field ...
```

After the user confirms send, update Notion:

- `Status` → **Sent**
- `Sent Date` → today
- `Follow-up Due` → Sent Date + 5–7 business days (user preference)

### Step 6 — Follow-up

Query Notion (or filter view **Follow-up due**):

- `Status` = Sent
- `Follow-up Sent` = false
- `Follow-up Due` ≤ today

For each row: draft a short bump (new render or manual), user sends, then set
`Follow-up Sent` = true and `Follow-up Date` = today. If no reply after second
touch, set `Status` = **Closed**.

## Status Model

Use exactly these Notion select values:

```text
Prospect → Researched → Draft Ready → Sent → Replied
                                      ↘ Closed (no response)
```

| Status | Meaning |
|--------|---------|
| Prospect | Scraped, not yet researched |
| Researched | Company/contact facts captured |
| Draft Ready | Rendered message in outbounds.json |
| Sent | User sent on LinkedIn or email |
| Replied | Got a response |
| Closed | No reply after follow-up window |

## Notion Views (create in UI)

| View name | Filter |
|-----------|--------|
| Inbox | Status = Prospect or Researched |
| Ready to send | Status = Draft Ready |
| Awaiting follow-up | Status = Sent AND Follow-up Sent = false AND Follow-up Due ≤ today |
| Active conversations | Status = Replied |

## Campaign manifest

`runs/<campaign_slug>/manifest.yaml` example:

```yaml
campaign: yc-w26-ai-founders
channel: linkedin_connect
template: inmail_intro_outbound
source_url: https://www.ycombinator.com/jobs/role/...
source_type: job_board
created_at: 2026-06-16
follow_up_days: 7
```

## Safety Rules

1. Never commit `NOTION_TOKEN`, page content with private emails, or `runs/` files.
2. Do not invent `recipient_name`, product facts, or metrics — use scrape + identity.yaml.
3. Do not auto-send LinkedIn messages; user sends manually.
4. Do not use `send` for email unless the user explicitly asks.
5. Dedup before insert: prefer `linkedin_url`, else `email`, else name+company slug.
6. Staging lives in `runs/` only; Notion is the tracking layer on top.

## Minimal End-to-End

```bash
# 1. Render after enrichment (preview)
uv run python cli.py render inmail_intro_outbound \
  --field recipient_name="Jane" \
  --field company_name="Vector AI" \
  --field main_product="embedding search for devtools" \
  --field my_work_and_impact="I shipped a docs RAG agent that took citation accuracy to 88%"

# 2. (Future) Sync staging file to Notion
# uv run python cli.py notion sync --campaign yc-w26-ai-founders

# 3. User sends on LinkedIn → agent updates Notion row Status=Sent
```

## Future CLI (not yet implemented)

When added to this repo, prefer:

```bash
uv run python cli.py notion sync --campaign <slug> [--dry-run]
uv run python cli.py notion follow-ups [--due-before YYYY-MM-DD]
uv run python cli.py notion mark-sent --page-id <id> [--follow-up-days 7]
```

Until then, use Notion API directly or MCP if available, following schema.md.

## Additional Resources

- Notion property definitions: [schema.md](schema.md)
- Campaign walkthrough: [examples.md](examples.md)
- Email/render commands: wingmate skill + `AGENTS.md`
