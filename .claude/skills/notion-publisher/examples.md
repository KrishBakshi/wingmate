# Notion Publisher — Examples

## Example A: YC job board → LinkedIn connection notes

**Goal:** Find AI startups hiring, personalize `inmail_intro_outbound`, track in Notion.

### 1. Discover

```text
runs/yc-summer-26/
  manifest.yaml
  prospects_raw.json   # 15 companies from YC jobs filter "AI"
```

### 2. Enrich one row

Input (raw):

```json
{
  "company_name": "Vector AI",
  "role_title": "Founding Engineer",
  "source_url": "https://www.ycombinator.com/companies/vector-ai/jobs",
  "source_type": "job_board"
}
```

After research (`prospects_enriched.json`):

```json
{
  "id": "vector-ai-alex-chen",
  "recipient_name": "Alex",
  "company_name": "Vector AI",
  "role_type": "founding engineer",
  "main_product": "embedding search APIs for devtools",
  "linkedin_url": "https://www.linkedin.com/in/alexchen",
  "research_notes": "W26 batch; first eng hire; blog post on hybrid search",
  "project_id": "docs_rag",
  "domain_context": "retrieval and citation evaluation over internal docs",
  "metric_impact": "citation accuracy from 61% to 88%"
}
```

### 3. Render

```bash
uv run python cli.py render inmail_intro_outbound \
  --field recipient_name="Alex" \
  --field company_name="Vector AI" \
  --field main_product="embedding search for devtools" \
  --field my_work_and_impact="I built a docs RAG agent that took citation accuracy from 61% to 88%"
```

Verify `char_count` ≤ 300. Save to `outbounds.json`.

### 4. Notion row (after publish)

| Name | Company | Status | Channel | Follow-up Due |
|------|---------|--------|---------|---------------|
| Alex @ Vector AI | Vector AI | Draft Ready | LinkedIn Connect | — |

### 5. After user sends on LinkedIn

Update Notion:

- Status → **Sent**
- Sent Date → 2026-06-16
- Follow-up Due → 2026-06-23

### 6. Follow-up query (one week later)

Filter: Status = Sent, Follow-up Sent = false, Follow-up Due ≤ today.

Bump example (manual or short render): reference the original note, one new proof point, soft ask.

---

## Example B: Company careers page → founder email

**Goal:** Email a founder when a careers page lists no public email but you have it from research.

Use `email_intro_outbound` with fields from `templates show email_intro_outbound`.

```bash
uv run python cli.py render email_intro_outbound \
  --field recipient_name="Sam" \
  --field company="Nebula Labs" \
  --field target_product="on-device LLM inference" \
  --field my_project="an agent evaluation harness" \
  --field domain_context="trace replay in CI" \
  --field metric_impact="3 behaviour regressions caught before release"
```

Notion: Channel = **Email**, attach Gmail draft id in Response Notes if useful.

```bash
uv run python cli.py draft email_intro_outbound --to sam@nebula.dev --fields-file runs/nebula/fields.yaml
```

Mark Sent only after user confirms the draft was sent or promoted.

---

## Example C: Weekly follow-up review

Agent prompt pattern:

> List all Notion outbounds where Status is Sent, Follow-up Sent is false, and Follow-up Due is on or before today. For each, show company, recipient, rendered body, and days since sent.

Output table for user; user picks which to bump; agent updates Notion checkboxes and dates.

---

## Anti-patterns

- Publishing to Notion before rendering → missing Rendered Body, can't audit what was sent
- Skipping dedup → duplicate rows for same LinkedIn profile
- Storing scrape JSON in `data/` → violates repo policy; use `runs/` only
- Adding a cal.com or calendar link to `email_intro_outbound` → the template is deliberately calendar-free per AGENTS.md §5
