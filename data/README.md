# `data/` — who you are

This folder is the **only** place the agent is allowed to get facts about you.
Templates hold wording; `data/` holds truth. If a claim is not in here, the agent
is not allowed to write it into an email.

Everything in this folder ships as a **seed** for a fictional person, John Dev.
Replacing John Dev with yourself is step one of using this repo, and the rest of
this README is how to do it.

| File | Role |
|---|---|
| `identity.yaml` | Structured ledger. `public:` (sender, projects, tone rules) and a gated `private:` section. **Primary source of truth.** |
| `resume.md` | Full resume prose. Secondary source, for anything the ledger does not carry. |
| `projects.md` | Long-form backing detail for each `projects[]` entry. |
| *(your resume PDF)* | Optional. Drop it here and point a template's `default_attachment` at it. |

Order of authority for any claim about you: `identity.yaml` `public:` first, then
`resume.md`, then nothing. Not a template's example text, not a past draft, not
the model's memory of an earlier session.

## The public / private split

`identity.yaml` has exactly two top-level keys, read through two different doors
in `src/services/identity_service.py`:

| Section | Holds | Access |
|---|---|---|
| `public` | `sender`, `projects`, `logic_rules` — work history and proof of work, publicly checkable | free; this is what outbound copy is built from |
| `private` | `contact`, `location`, `employment`, `documents` — personal email, address, current/expected CTC, notice period, IDs | gated: retrieval refuses without approval, and `guard_disclosure` re-checks every outgoing body |

A recruiter asking for "your details" is not consent to send them. Adding a new
field means deciding which side of the line it falls on: **would this be true and
findable about you from the outside?** If yes it is public. If it is only known
because you know it, it is private.

Two things to be clear about:

1. **The `private:` section is not a secret store.** `identity.yaml` is tracked
   in git. The gate protects against *disclosure to a recipient*, not against
   anyone with repo access. Leave a field `null` rather than committing a value
   you would not want in history — the gate's pattern rules work with the whole
   section empty.
2. **Your phone number goes in neither.** Put it in `.env` as `RESUME_PHONE`.
   `.env` is git-ignored, the resume build reads it at build time so the PDF
   carries it, and the disclosure gate reads the same env var so it can still
   catch the number if it ever appears in a body. Do not copy it into
   `private.contact.phone`.

## How to write `identity.yaml`

Keep the two top-level sections, and under `public:` keep `sender`, `projects`,
and `logic_rules`.

### `sender`

Short, factual, and safe to quote. Contact details go under `private:`, not here.

```yaml
public:
  sender:
    name: "Your Name"
    portfolio: "your-site.example"
    creds: "how you want to be described in one clause"
    summary: "one sentence on what you build"
```

### `projects[]` — the ledger

This is the part that does the work. Each entry:

| Key | What it is for |
|---|---|
| `id` | snake_case, unique. Referenced from `projects.md` and from campaign files. |
| `title` | Human-readable name. |
| `tech` | Stack, for when a target's job post names a technology. |
| `plain_desc` | One noun phrase: *"an agent that triages support tickets"*. Drops straight into a template's project field. |
| `industrial_hook` | Why it mattered, in business terms. |
| `metric` | The number. **Never invented, never rounded up.** |
| `relevance` | Comma-separated domains this project speaks to. |
| `hook_examples` | A pre-written one-liner, so the agent does not re-improvise it every time. |
| `link` | Optional public URL. |

**`relevance` is load-bearing.** It exists so the agent picks a project by
overlap with the target's own words rather than by which project has the biggest
number. Write it generously — every domain word someone might use for that work.

Three to eight entries is a good ledger. Fewer and the agent repeats itself;
more and the selection gets noisy.

### `logic_rules`

Style constraints the agent must respect when composing or editing a template:
tone, your subject-line pattern, and `forbidden_phrases`. Short and enforceable
only — this is not a place for essays about your voice.

## How to write `projects.md`

One `##` section per `projects[]` entry, with the ledger `id` stated so the two
files stay joined. Stack, repo link, what it does, features, and the result.
This is what the agent reads when one line from the ledger is not enough.

## How to write `resume.md`

- Keep the headings stable: `PROFESSIONAL SUMMARY`, `WORK EXPERIENCE`,
  `PROJECTS`, `SKILLS`, `EDUCATION`.
- Prefer quantified outcomes (%, latency, scale, volume, accuracy).
- Keep dates, titles, and links consistent with your public profiles — the
  agent will quote them.
- No secrets, no credentials, **no phone number**.

## Iterating

The ledger is meant to move. Useful habits:

- **After a project ships**, add it to `projects[]` before you next send
  outbound. A stale ledger is how an agent ends up pitching last year's work.
- **When a metric changes**, change it in the ledger — that is the one place
  templates and skills read it from.
- **When the agent picks the wrong project**, the fix is almost always
  `relevance`, not the prompt. Add the domain words the target actually used.
- **When two sources disagree** (ledger says one number, resume says another),
  the ledger wins and the agent should tell you about the conflict rather than
  silently choosing. Fix it in both.
- **Ask the agent to do it.** "Add my new project to the ledger" is a reasonable
  instruction; it has this README and knows the shape.

## Never write operational data here

Scraped pages, prospect lists, research JSON, batch output, draft logs: those go
to `runs/<campaign>/`, which is git-ignored. `data/` is stable, tracked, personal
knowledge only.

## Checklist before you commit

- [ ] YAML parses (spaces, not tabs) — `uv run python cli.py identity show`
- [ ] Project `id` values are unique and match `projects.md`
- [ ] Every `metric` is real and checkable
- [ ] Nothing under `public:` that a recruiter form would have asked for
- [ ] No secrets, tokens, keys, or phone numbers anywhere in this folder
- [ ] `uv run python guardrails/check_identity_disclosure_gate.py` passes
