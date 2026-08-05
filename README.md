<img src="assets/mark.svg" alt="" width="52" height="52">

# Wingmate

An open-source, local-first **research-led outbound agent** you drive by talking
to a coding agent.

> Relevance is a research problem, not a writing problem.

It finds a public prospect signal, verifies it (source, date, exact fact kept),
maps it against proof drawn from your own project ledger, and drafts outreach
through a template that encodes how you write. That mapped connection is a
**value hypothesis**, never a claimed pain point: Wingmate never asserts more
about a prospect than a source states.

```
find prospects → verify signals → identify credible fit → draft in your voice → review and send
```

You describe who you are once, in `data/`. You describe what you want to say
once, in `templates/`. After that, "draft an intro to the founder of Acme about
their inference work" becomes a real Gmail draft with your actual projects and
your actual numbers in it, and the parts of that sentence a language model would
otherwise be tempted to invent are the parts it is structurally prevented from
inventing.

It works with **any agent harness**: Claude Code, Codex, Cursor, or anything else
that reads `AGENTS.md`. There is no vendor lock-in in the design, and the CLI
works fine on its own if you would rather type.

Wingmate is one focused part of outbound GTM, not a full GTM platform: it does
not manage a CRM, run a sequencer, or send anything on its own.

## Why it is built this way

Cold outreach written by an LLM fails in two specific, predictable ways: it makes
things up about you, and it sounds like it was written by an LLM. Both are fixed
by the same move, which is refusing to let the model author the message.

- **Templates hold the wording.** The agent substitutes declared placeholders. It
  does not paraphrase your sentences. Your voice stays your voice because it is
  the only voice in the file.
- **`data/identity.yaml` holds the facts.** One ledger of your projects, metrics,
  and links, with a public section that outbound is built from and a private
  section that it is not. The agent is instructed to read it before composing and
  to never claim anything that is not in it.
- **Two gates enforce the dangerous parts in code, not in a prompt.** A body that
  does not reproduce a template is refused at `create_draft`, not just at `send`.
  A body containing private data (phone, CTC, notice period, government IDs) is
  refused too. Both fail closed, both sit inside the service so an inline script
  cannot route around them, and both are pinned by checks in `guardrails/`.
- **It learns.** Your edits to a draft are a signal about your voice, and the
  agent is instructed to fold them back into the template, the ledger, or its own
  standing instructions rather than making you say them again.

**Be precise about which layer does what.** The gates are code, and they hold
regardless of which model or harness you point at the repo. The rest, including
"only use facts from the ledger" and "pick the project by relevance", is
instruction in `AGENTS.md`, which a capable agent follows and a careless one can
still get wrong. Concretely: nothing stops you or an agent from passing an
invented number as a `--field` value. What the template gate guarantees is that
the *sentence around it* is one you wrote and approved, which is what makes a
wrong value easy to spot when you read the draft. Read your drafts.

The gates block the agent, not you. An override exists for every one, and it
takes the shape of the agent asking you a question and waiting for your answer.

## What you get

```
templates/     one YAML file per message. wording lives here.
data/          who you are: identity ledger, resume, projects. facts live here.
runs/          everything operational: scrapes, prospect lists, drafts. git-ignored.
guardrails/    the outbound-safety checks that keep the above honest.
src/           the CLI and services (Gmail, rendering, batch, matching, identity).
AGENTS.md      the instruction file every agent harness reads. CLAUDE.md symlinks to it.
.claude/skills six skills: wingmate, gmail-draft, template-builder,
               notion-publisher, scrapling, find-recent-investment.
```

The repo ships as a **seed**. `data/` describes a fictional developer called John
Dev, and `templates/` has one intro email plus its LinkedIn counterpart. Your
first session is replacing John Dev with yourself, and the agent knows how to
walk you through that (see §0 of `AGENTS.md`).

## Setup

Requires Python 3.11, 3.12, or 3.13 (`pyproject.toml` pins `>=3.11,<3.14`)
and [uv](https://docs.astral.sh/uv/).

```bash
git clone <your-fork> wingmate && cd wingmate
uv sync
cp .env.example .env
```

Then open the folder in your agent and say:

> Read AGENTS.md and set this repo up for me.

It will interview you for the identity ledger and rewrite the seed template in
your voice. If you would rather do it by hand, read `data/README.md` and
`templates/README.md`, in that order.

**There is no model API key, anywhere.** Wingmate does not call an LLM provider
and has no place to configure one. Rendering is deterministic placeholder
substitution, and every judgement call, which template fits, which project to
cite, how to word a new template, is made by the agent you are already talking
to, using whatever model that agent runs on. Nothing in this repo is tied to a
particular model or vendor.

## Gmail setup

Gmail access uses your **own** Google Cloud OAuth client. No credentials ship
with this repo, and none should ever be committed to it: `.gitignore` excludes
`*credentials.json`, `*token.json`, and `.env`.

1. Go to the [Google Cloud Console](https://console.cloud.google.com/) and create
   a project (or pick an existing one).
2. **APIs & Services → Library → Gmail API → Enable.**
3. **APIs & Services → OAuth consent screen.** Choose *External*, fill in the app
   name and your email, and add yourself under **Test users**. You do not need to
   publish or get the app verified; a test user can use it indefinitely for their
   own account.
4. **APIs & Services → Credentials → Create Credentials → OAuth client ID →
   Desktop app.**
5. Download the JSON and save it as `credentials.json` in the repo root (or set
   `GMAIL_CREDENTIALS_PATH` in `.env` to wherever you keep it).
6. Trigger the consent flow once:

   ```bash
   uv run python cli.py drafts list
   ```

   A browser window opens, you approve the scopes, and `token.json` is written
   next to `credentials.json`. Delete `token.json` to re-authenticate. The
   consent flow binds **localhost:8080**, so free that port before running it.
   An expired token refreshes silently; a refresh that fails deletes
   `token.json` and re-runs the browser flow.

**What you are granting.** The requested scopes are `gmail.compose` and
`gmail.modify`. Be clear-eyed about what that means: together they allow
creating, sending, reading, and modifying mail in the account you authorize.
They are broader than "drafts only", because `create_draft` needs compose and
attaching/updating a draft needs modify.

So the guarantee that nothing goes out unasked is **not** enforced by the OAuth
scope. It comes from the code path: `draft` is the default verb everywhere,
`send` is a separate command that requires you to say the word, and both are
gated by the template and disclosure checks described above. If you want a
stronger boundary than that, authorize a dedicated Google account rather than
your primary one.

If you want Notion tracking as well, the `notion-publisher` skill explains the
one-time integration setup; set `NOTION_TOKEN` and `NOTION_OUTBOUND_DB_ID` in
`.env`. Note that there are no `notion` CLI subcommands: the agent drives the
Notion API directly, following the schema in that skill. Notion is optional and
nothing else depends on it.

## Using it

Talk to your agent. It reads `AGENTS.md`, picks the template, pulls the right
project out of your ledger, previews, and creates the draft.

```
draft an intro to Alex at Acme AI, they build inference infrastructure
give me the LinkedIn version of that
add a template for replying to recruiters who reach out first
show me my recent drafts
```

Or use the CLI directly:

```bash
uv run python cli.py templates list
uv run python cli.py templates show email_intro_outbound

uv run python cli.py render email_intro_outbound \
  --field recipient_name="Alex" \
  --field company="Acme AI" \
  --field target_product="LLM inference infrastructure" \
  --field my_project="a support triage agent" \
  --field domain_context="tool calling over a ticket queue" \
  --field metric_impact="first response times going from hours to minutes"

uv run python cli.py draft email_intro_outbound --to alex@acme.example --field ...
```

Full command surface: §4 of `AGENTS.md`.

## Running the guardrails

```bash
uv run python guardrails/check_send_template_gate.py
uv run python guardrails/check_identity_disclosure_gate.py
# or both, through pytest:
uv run python -m pytest guardrails -q
```

Run them after editing a template, the matcher, or `identity.yaml`. They are
fast, and they are the thing that tells you a change quietly opened a hole.

## A note on your data

`data/identity.yaml` is **tracked in git**. Its `private:` section protects
against *disclosure to a recipient*, not against anyone who can read your
repository. If you fork this publicly, leave those fields `null` — the gate's
pattern rules work with the whole section empty. Your phone number belongs in
`.env` as `RESUME_PHONE` and nowhere else.

## Contributing

Templates and skills are the interesting surface. If you write a template shape
that generalizes (a referral ask, an inbound-recruiter reply, a conference
follow-up), or a skill worth sharing, a PR is welcome. Keep personal data out of
it: examples use John Dev and `example.com` addresses.

Commit convention is in §9 of `AGENTS.md`.

This repo is made and maintained by [Krish Bakshi](https://krishb.tech).
