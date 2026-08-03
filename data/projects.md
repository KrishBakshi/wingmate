# Projects — John Dev

Long-form descriptions of the projects listed in `identity.yaml` `public.projects[]`.
The ledger in `identity.yaml` is what outbound copy is built from; this file is
the human-readable backing detail an agent reads when it needs more than one line.

> Seed file. Replace these three with your own. Keep one `##` section per
> `projects[]` entry and keep the `id` in the ledger matching the section here.

---

## Support Triage Agent

**Stack:** Python, tool/function calling, Postgres, FastAPI
**Repo:** [johndev/support-triage-agent](https://github.com/johndev/support-triage-agent)
**Ledger id:** `support_triage_agent`

An agent that reads inbound support tickets, classifies them against a routing
taxonomy, pulls the relevant history, and drafts a reply for a human to approve.
Nothing sends without that approval.

### Features

- **Routing** — Classifies a ticket into one of 14 queues with a confidence score, and escalates anything below the threshold to a human instead of guessing.
- **Context assembly** — Pulls the customer's prior tickets and current plan from Postgres before drafting, so replies reference real account state.
- **Draft, never send** — Every reply lands in a review queue. The approval step is the product, not a safety afterthought.

### Result

Cut first-response time from hours to minutes across a 400-ticket/week queue.

---

## Documentation RAG Assistant

**Stack:** Python, embeddings, vector search, retrieval evaluation harness
**Ledger id:** `docs_rag`

Question answering over internal documentation, with citations, plus the eval
harness that makes changes to it measurable.

### Features

- **Citations by construction** — An answer that cannot cite a retrieved chunk is not returned.
- **Eval set** — 200 questions with known-correct source documents, scored on every retrieval change.
- **Chunking experiments** — The harness is what let the chunking strategy change three times without regressing quality.

### Result

Correct-citation rate went from 61% to 88% on the 200-question eval set.

---

## Agent Evaluation Harness

**Stack:** Python, pytest, structured tracing, CI integration
**Ledger id:** `agent_eval_harness`

Records real agent traces and replays them on every commit, so a prompt edit or a
tool-signature change cannot silently alter behaviour.

### Features

- **Trace replay** — 40 recorded scenarios replayed against the current prompt and tool set.
- **Behavioural assertions** — Checks which tools were called and in what order, not just the final string.
- **CI gate** — Runs on every pull request; a behaviour change has to be acknowledged in the diff.

### Result

Caught 3 behaviour regressions before release in its first month.
