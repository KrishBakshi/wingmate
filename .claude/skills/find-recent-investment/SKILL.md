---
name: find-recent-investment
description: >-
  Look up a target company's most recent funding/investment news (round,
  amount, date, lead investors, source) for use as an outbound personalization
  hook. Use when the user gives a company name and asks about its funding,
  investment, or recent raise, or asks to research a company before drafting
  an email/LinkedIn note.
---

# Find Recent Investment

Given a target company, find its **most recent** funding round and return a
few clean facts other skills can drop straight into personalization fields
(`research_notes` in [[notion-publisher]], or any template variable that
references funding/context).

## When To Use

Trigger when the user asks things like:

- "find <company>'s most recent funding"
- "has <company> raised any money recently?"
- "research <company> before I email them"
- as a research step inside a notion-publisher or wingmate campaign

## Workflow

1. **Clarify the target.** Get the company name or domain (e.g. `aampe.com`).
2. **Search broad, not narrow.** Use `WebSearch` with one wide query:

   `<company/domain> recent investment activity <current year>`

   e.g. `aampe.com recent investment activity 2026`

   Keep it broad on purpose — a narrow query (specific round type, specific
   investor) tends to surface old or unrelated results. The broad form
   naturally surfaces the newest activity across news, Crunchbase,
   LinkedIn, and the company's own posts.
3. **Confirm with the primary source.** `WebFetch` the most promising
   result(s) to pull exact figures rather than trusting the search snippet.
4. **Pick the most recent activity only** — ignore older rounds unless the
   user asks for funding history. Note the date explicitly; if nothing
   turns up newer than ~12-18 months old, say so rather than presenting
   stale news as "recent."
5. **Report facts, not guesses.** If no funding news is found, say so
   plainly — do not invent an amount, investor, or date.

## Output Format

Return a short summary plus a structured block the user (or another skill)
can paste into `research_notes` / a template field:

```json
{
  "company_name": "Acme AI",
  "round": "Series A",
  "amount": "$14M",
  "date": "2026-03",
  "lead_investors": ["Example Ventures"],
  "other_investors": ["Angel Name"],
  "source_url": "https://techcrunch.com/...",
  "notes": "raised to expand engineering team; first ML hire mentioned in post"
}
```

If nothing recent is found:

```json
{
  "company_name": "Acme AI",
  "round": null,
  "notes": "No funding news found in the last 18 months as of 2026-07-11."
}
```

## Safety Rules

1. Never fabricate amounts, dates, or investor names — every figure must
   trace back to a fetched source URL.
2. State the source and its publish date alongside every fact so the user
   can judge recency themselves.
3. If sources conflict (e.g. Crunchbase vs. a news article), report the
   discrepancy instead of silently picking one.
4. Don't write results into `data/` — this is research output; if the user
   is running a campaign, hand facts off to `runs/<campaign>/` per
   [[notion-publisher]] conventions.
