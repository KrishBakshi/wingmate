# Notion Publisher — Schema

## Outbound Pipeline (primary database)

Create one Notion database named **Outbound Pipeline**. Properties:

| Property | Notion type | Required | Notes |
|----------|-------------|----------|-------|
| Name | Title | yes | `{recipient_name} @ {company_name}` |
| Company | Text | yes | |
| Role | Text | yes | Job title or founder role |
| Channel | Select | yes | `LinkedIn Connect`, `LinkedIn InMail`, `Email`, `Other` |
| Status | Select | yes | See status values in SKILL.md |
| Template | Text | no | e.g. `inmail_intro_outbound` |
| Main Product | Text | no | One-line product focus for personalization |
| LinkedIn URL | URL | no | **Primary dedup key** |
| Email | Email | no | Secondary dedup key |
| Source URL | URL | no | Job post or careers page |
| Source Type | Select | no | `job_board`, `company_site`, `linkedin`, `manual` |
| Campaign | Text | no | Matches `runs/<campaign_slug>/` |
| Research Notes | Text | no | Bullets used for personalization |
| Rendered Body | Text | no | Final message (plain text for inmail) |
| Char Count | Number | no | For LinkedIn limit checks |
| Sent Date | Date | no | Set when user confirms send |
| Follow-up Due | Date | no | Sent Date + N days |
| Follow-up Sent | Checkbox | no | |
| Follow-up Date | Date | no | When bump was sent |
| Response Notes | Text | no | Reply summary |
| Project | Text | no | identity.yaml project id or title |
| Notion Page ID | Text | no | Optional mirror for scripts |

### Status select options

`Prospect`, `Researched`, `Draft Ready`, `Sent`, `Replied`, `Closed`

### Channel select options

`LinkedIn Connect`, `LinkedIn InMail`, `Email`, `Other`

---

## Staging JSON schemas (`runs/<campaign>/`)

### prospects_raw.json

```json
[
  {
    "company_name": "Acme AI",
    "role_title": "Founding ML Engineer",
    "source_url": "https://example.com/jobs/123",
    "source_type": "job_board"
  }
]
```

### prospects_enriched.json

```json
[
  {
    "id": "acme-ai-jane-doe",
    "recipient_name": "Jane Doe",
    "company_name": "Acme AI",
    "role_type": "founding ML engineer",
    "main_product": "embedding search for developer tools",
    "linkedin_url": "https://www.linkedin.com/in/janedoe",
    "email": null,
    "source_url": "https://example.com/jobs/123",
    "source_type": "job_board",
    "research_notes": "Series A; hiring first ML hire; blog mentions RAG",
    "project_id": "docs_rag",
    "domain_context": "embeddings and retrieval evaluation over internal docs",
    "metric_impact": "citation accuracy from 61% to 88% on a 200-question eval set"
  }
]
```

### outbounds.json

```json
[
  {
    "id": "acme-ai-jane-doe",
    "template": "inmail_intro_outbound",
    "channel": "LinkedIn Connect",
    "render_fields": {
      "recipient_name": "Jane",
      "company_name": "Acme AI",
      "role_type": "founding ML engineer",
      "main_product": "embedding search for devtools",
      "my_work_and_impact": "I built a docs RAG agent that took citation accuracy to 88%"
    },
    "rendered_subject": "Intro: Acme AI",
    "rendered_body": "Hi Jane, I've followed...",
    "char_count": 287,
    "status": "Draft Ready",
    "notion_page_id": null
  }
]
```

### sync_log.json

```json
{
  "campaign": "yc-w26-ai-founders",
  "last_synced_at": "2026-06-16T14:30:00Z",
  "rows_upserted": 12,
  "rows_skipped_duplicate": 2
}
```

---

## Field mapping: JSON → Notion

| JSON field | Notion property |
|------------|-----------------|
| `recipient_name` + `company_name` | Name (title) |
| `company_name` | Company |
| `role_type` | Role |
| `channel` | Channel |
| `status` | Status |
| `template` | Template |
| `main_product` | Main Product |
| `linkedin_url` | LinkedIn URL |
| `email` | Email |
| `source_url` | Source URL |
| `source_type` | Source Type |
| manifest `campaign` | Campaign |
| `research_notes` | Research Notes |
| `rendered_body` | Rendered Body |
| `char_count` | Char Count |
| `project_id` | Project |
| `notion_page_id` | (stored locally only; page id returned by API) |

---

## Dedup rules

1. If `linkedin_url` present → query Notion by URL; update if found.
2. Else if `email` present → query by Email.
3. Else → match Title contains `recipient_name` AND Company equals `company_name`.
4. Never create a second row for the same person at the same company in one campaign.

---

## Optional: Companies database (phase 2)

Add later if volume grows. Relation from Outbound Pipeline → Companies.

| Property | Type |
|----------|------|
| Name | Title |
| Website | URL |
| Product Summary | Text |
| Funding Stage | Select |
| Outbounds | Relation → Outbound Pipeline |

Start with **Company** as a text field on the main table; split only when needed.
