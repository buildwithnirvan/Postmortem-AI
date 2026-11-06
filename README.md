# Postmortem — incident response that learns from outcomes

An on-call decision-support agent. You describe an incident; it recalls similar past incidents
from **Hindsight** memory and proposes a prioritized troubleshooting plan with cited evidence.
You mark each step *worked / failed / not tried*; confirmed outcomes are retained in Hindsight,
so the **next** similar incident ranks proven fixes up and known-bad "fixes" down.

> Decision support only. Nothing is executed against any system. Use synthetic data only.

## Why memory is the core
Without memory the agent suggests the generic "restart it". With memory it knows that restarting
`payments-api` only masked a Redis pool leak twice, and that raising the pool limit is what
actually worked. Remove Hindsight and the product collapses back into a generic chatbot.

## Memory lifecycle

| Step | When | What | Hindsight call |
|---|---|---|---|
| Recall | A new incident is submitted (before it is stored) | Query built from service, title, symptoms and key log lines | `recall` |
| Plan | After recall | LLM sees memories as M1, M2…, must cite them; a deterministic guard enforces recorded outcomes | — |
| Retain incident | After the plan is made | Redacted incident report, tags `incident`, `service:<x>` | `retain` |
| Retain outcome | User saves outcomes | One memory per **worked/failed** action, tags `outcome`, `service:<x>`, `result:<x>`. *Not tried is never retained.* | `retain_batch` |
| Inspect | Memory inspector tab, plan's "why" panel | Lists stored facts / recalled memories with scores | `list_memories` |
| Reset | User types `RESET` | Deletes the bank | `delete_bank` |

All Hindsight access lives in `app/memory/service.py`. What is written is decided in
`app/memory/formatting.py`. Secrets and emails are redacted before anything leaves the app.

### How outcomes change recommendations
1. The prompt marks each memory `[recorded outcome: FAILED|WORKED]` (read from the `result:*` tags).
2. `apply_outcome_guard` (`app/agent/planner.py`) then enforces it: actions backed by a WORKED memory
   rank first, actions past FAILED outcomes warn against rank last, a "supports" citation pointing
   at a FAILED memory is corrected to "warns", and invented citations are dropped. Each moved
   action shows a "Memory effect" line in the UI.

## Architecture
```
Browser UI (app/static) ──> FastAPI (app/api.py)
                              ├─ MemoryService ──> Hindsight (retain / recall / list / delete)
                              ├─ planner + GroqClient ──> Groq LLM (JSON plan, retries)
                              └─ Store (SQLite) — session state only (plans, outcomes), NOT memory
```
| Path | Role |
|---|---|
| `app/api.py` | Routes; orchestrates recall → plan → retain |
| `app/memory/service.py` | The only Hindsight integration |
| `app/memory/formatting.py` | What is retained / queried; redaction; tags |
| `app/agent/planner.py` | Prompt, plan validation, outcome guard |
| `app/agent/llm.py` | Groq client with JSON repair + retry |
| `app/data/seed_incidents.py` | 8 synthetic incidents with outcomes |
| `app/storage.py` | SQLite session state |
| `scripts/demo.py` | Repeatable before/after demo (real services) |
| `tests/` | Unit + flow tests; real SDK against a local stub server; opt-in real-Hindsight integration test |

Dependencies: `fastapi`+`uvicorn` (API/server), `httpx` (Groq calls), `python-dotenv` (.env),
`hindsight-client` (official SDK). No frontend build step.

## Setup
Requires Python 3.10+.
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env          # then edit .env (see MANUAL_TESTING.md)
uvicorn app.main:app --port 8000
# open http://localhost:8000
```
Required: `HINDSIGHT_BASE_URL`, `HINDSIGHT_API_KEY` (Cloud; may be empty if self-hosted without auth),
`GROQ_API_KEY`. Hindsight Cloud: https://ui.hindsight.vectorize.io (promo code `MEMHACK99` in billing).

## Checks
```bash
ruff check . && mypy app scripts && pytest -q
HINDSIGHT_INTEGRATION=1 pytest tests/test_integration_hindsight.py -s   # needs real .env
python -m scripts.demo --reset                                          # needs real .env
```

## Known limitations
* Retain/recall against a real Hindsight server has **not** been verified by the author of this
  code in the build environment (no credentials there). What *was* verified: calls bind to the
  installed SDK signatures, and the real SDK runs end-to-end over HTTP against a local stub server
  (`tests/test_sdk_over_http.py`), including 8-thread concurrency. The stub is not Hindsight, so
  the integration test and `MANUAL_TESTING.md` still verify the real thing.
* All Hindsight calls run on one dedicated worker thread (the SDK's sync wrapper is not thread-safe
  across FastAPI's worker pool), so memory calls are serialized. Fine for a single-user demo.
* Hindsight extracts facts with its own LLM, so recalled text may be reworded. The worked/failed
  signal is read from the `result:*` tags when present (exact). If Hindsight drops the tags, a
  **heuristic text fallback** (`outcome_from_text`) infers the verdict, but only for untagged
  memories that mention an action/outcome and express exactly one verdict; ambiguous text is
  left unlabeled. Verify which path you get in the inspector (Test 6).
* Band AI desktop is required by the hackathon rules; it is not integrated into this app.
  Confirm with the organizers what "use" must mean.
* Single-user, no auth. Synthetic data only.
