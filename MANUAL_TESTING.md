# Manual testing guide (beginner friendly)

You will run the app on your computer and click through it. Allow about 30 minutes.

## A. Install and configure

1. Install **Python 3.10+** (check: `python3 --version`).
2. Get your three values:
   * **Hindsight URL + API key**: sign in at https://ui.hindsight.vectorize.io, create/open an
     API key, copy the API URL and key. Add promo code `MEMHACK99` under Billing for $50 credits.
   * **Groq key**: https://console.groq.com → API Keys → create.
3. In a terminal, inside the project folder:
```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env               # Windows: copy .env.example .env
```
4. Open `.env` in an editor and replace the placeholders:

| Variable | Put here |
|---|---|
| `HINDSIGHT_BASE_URL` | the API URL from the Hindsight dashboard |
| `HINDSIGHT_API_KEY` | your Hindsight key |
| `GROQ_API_KEY` | your Groq key |
| `HINDSIGHT_BANK_ID` | keep `postmortem-demo` (or any new name) |

5. Run the automated checks first (no keys needed):
```bash
ruff check . && mypy app scripts && pytest -q
```
Expect: `All checks passed!`, `Success: no issues found`, `37 passed, 1 skipped`.

6. Start the app:
```bash
uvicorn app.main:app --port 8000
```
Open http://localhost:8000. **Stop** with `Ctrl+C`; **restart** with the same command
(plans live in `postmortem.db`; memory lives in Hindsight, so both survive restarts).

## B. Tests (do in order)

**Test 1: Health.** Top-right should show Hindsight and the model with green dots, and Hindsight's
version. *Red dot / yellow banner* = a value in `.env` is wrong (banner names what). Fix `.env`,
restart.

**Test 2: Real Hindsight integration test** (optional, ~1 min):
```bash
HINDSIGHT_INTEGRATION=1 pytest tests/test_integration_hindsight.py -s
```
Expect `1 passed` and a `RECALLED:` line. This uses a throwaway bank and deletes it.

**Test 3: Start empty.** Go to **Memory inspector** → **Reset memory…** → type `RESET`. The list
should say *Empty*.

**Test 4: BEFORE (no memory).** *Incident* tab → Load a sample → **A. payments-api…** → click
**Generate plan**. Expect: badge **"Memory empty (cold start)"**; a generic plan, most likely
starting with *restart* or *check metrics*; the recalled-memories panel says none.

**Test 5: Retain outcomes.** On that plan mark the *restart* step **Failed** (notes: `came back
after 12 minutes`), the *pool/connection limit* step **Worked**, others **Not tried**. Click
**Save outcomes to memory**. Expect: `Retained 2 in Hindsight; N not tried (not retained)`.

**Test 6: Verify Hindsight really retained it.** *Memory inspector* → search `restart`. Within a
minute you should see facts mentioning the restart FAILED and the pool fix WORKED, with tags
`outcome`, `service:payments-api`, `result:failed` / `result:worked`. (Retain runs Hindsight's
fact extraction, so click Search again if empty.) You can also see the bank in the Hindsight
dashboard. *If facts exist but have no `result:` tags*, the app falls back to a text heuristic (it looks for
"failed"/"worked" in the fact). Test 7 should still rank correctly, but tell me either way so we
know which path real Hindsight takes.

**Test 7: AFTER (with memory).** Back on *Incident*, load sample **A** again, **Generate plan**.
Expect: badge **"Memory used"**; the pool/connection fix ranked **first** with a green
*"Memory effect: Ranked up"* line; *restart* ranked **last** with a red warning and *"Ranked
down"*; evidence chips (M1, M2…) that scroll to the matching recalled memory under
**Why this plan?**

**Test 8: Same input, memory off.** Untick **Use Hindsight memory**, Generate. Expect badge
**"Memory off (baseline)"** and the generic plan again. Nothing from this run is stored.

**Test 9: Seed history.** Reset memory, then **Load synthetic history** (takes up to a minute).
Inspector shows many facts. Generate sample **A** (memory on): the plan should cite the earlier
`payments-api` incidents. Sample **B** should cite Kafka incidents (raise `max.poll.interval.ms`,
not "add partitions"). Sample **C** (DNS) has no relevant history: expect a generic plan and
little or no evidence.

**Test 10: Errors and recovery.**
| Do this | Expect |
|---|---|
| Submit with empty Title | Inline message "Please fill in: title" |
| Stop the app, start with a wrong `GROQ_API_KEY` | Generate → red message "LLM unavailable… rejected the API key". Fix `.env`, restart |
| Set `HINDSIGHT_API_KEY` wrong, restart, Generate | Plan still appears with badge **Memory unavailable** and a yellow warning (graceful degradation) |
| Type `RE` in the reset prompt | Nothing is deleted |
| Open **Past runs** | Earlier incidents listed; **Open** reloads a plan |

## C. Reproduce the demo from the command line
```bash
python -m scripts.demo --reset
```
Prints the BEFORE order, loads history, then the AFTER order. **Warning:** `--reset` deletes
the bank named in `HINDSIGHT_BANK_ID`; use a dedicated bank.

## D. Copy-paste incidents (also in the dropdown)

**A (the demo)**
* Title: `payments-api 502s with Redis connection timeouts`
* Service: `payments-api`
* Description: `Since 19:40 UTC checkout requests are failing intermittently. Traffic is about 1.6x normal because of a weekend campaign. Pods look healthy.`
* Symptoms: `502 rate around 15%, p99 latency 8s, Redis client timeouts in logs.`
* Logs:
```
redis.exceptions.TimeoutError: Timeout reading from socket
WARN pool wait timeout after 5000ms (max_connections=100, in_use=100)
ERROR POST /v1/charges 502 upstream timeout
```

**B**
* Title: `ingest-pipeline consumer lag keeps growing`; Service: `ingest-pipeline`
* Description: `Lag on events.raw is growing by about 1M messages per 10 minutes. Consumers keep leaving and rejoining the group.`
* Symptoms: `Lag climbing, repeated rebalances, almost no throughput between them.`
* Logs: `WARN Member consumer-3 sending LeaveGroup request: max.poll.interval.ms exceeded`

**C**
* Title: `data-sync cron failing with DNS resolution errors`; Service: `data-sync`
* Description: `Nightly sync job to the partner SFTP host fails since this morning.`
* Symptoms: `Temporary failure in name resolution for sftp.partner.example.`
* Logs: `ERROR socket.gaierror: [Errno -3] Temporary failure in name resolution`
