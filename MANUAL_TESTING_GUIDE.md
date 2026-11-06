# MANUAL TESTING GUIDE: POSTMORTEM 2.0
An end-to-end, beginner-friendly operational guide for testing and demonstrating **POSTMORTEM 2.0 — AI Incident Intelligence and Long-Term Memory Resolution**.

---

## 1. Prerequisites
- **Python 3.10+** (verified working on Python 3.13)
- Modern web browser (Chrome, Edge, Firefox, Brave)
- Internet access for Groq LLM API calls

---

## 2. Starting the Application

If the server is ever stopped, restart it in PowerShell from the project folder:

```powershell
cd C:\Users\admin\Downloads\postmortem\postmortem
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --port 8000
```

Once running, navigate to:
👉 **[http://localhost:8000](http://localhost:8000)**

---

## 3. UI Overview & Layout
In the left sidebar you will see:
1. **Overview**: Executive dashboard with high-level KPIs and recent critical incidents.
2. **New Investigation**: AI triage engine, Root Cause Analysis, and memory-guided troubleshooting plan.
3. **Incidents Hub**: Central table tracking all open, investigating, and resolved incidents.
4. **Memory Intelligence**: Live inspector for the Hindsight memory bank, with search and reset controls.
5. **Recurring Patterns**: Automated pattern recognition identifying repeated failure loops.
6. **Service Topology**: Microservice dependency map displaying cascades and blast radii.
7. **Incident Analytics**: Real-time resolution metrics, MTTR, category breakdowns, and memory lift.
8. **Postmortem Reports**: Structured postmortem generator with Markdown and one-click printable PDF export.

---

## 4. Step-by-Step Hackathon Testing Workflow

### Test 1: Verify System Status
- Look at the sidebar footer and top header.
- **Hindsight Memory** should display `Online` (or green indicator).
- **Model** should display `openai/gpt-oss-120b` (via Groq).

### Test 2: Cold Start (Baseline Plan Without Memory)
1. Go to **Memory Intelligence** in the sidebar.
2. Click **Reset Bank** and confirm with `RESET` (cleans out previous tests).
3. Click **New Investigation** in the sidebar.
4. In the top dropdown, select **`payments-api: payments-api Redis pool exhaustion`**.
5. Click **Run AI Investigation**.
6. **Observe the result:**
   - The badge will show **`Cold Start (No Memory)`**.
   - The Root Cause Analysis (RCA) hypothesis identifies the Redis pool saturation.
   - The troubleshooting roadmap lists textbook steps (e.g., *Restart service pods* as Step 1 or 2).

### Test 3: Teaching Memory (Save Outcomes)
1. On the generated troubleshooting actions:
   - For **Restart service pods**, click the **`Failed`** button. In the notes box next to it, enter:
     `Restart masked the issue; pods crashed again within 10 minutes.`
   - For **Increase Redis connection pool size**, click the **`Worked`** button. In notes, enter:
     `Permanent fix: raised pool limit from 20 to 100.`
   - Leave untried actions as **`Not Tried`**.
2. Click **`Save Outcomes to Hindsight`** at the bottom of the roadmap.
3. Notice the toast: *"Outcomes committed to long-term memory!"*

### Test 4: Verify Memory Bank
1. Go to **Memory Intelligence** in the sidebar.
2. Search for `payments-api` or `restart`.
3. You will see two new memory cards:
   - One tagged with `RESULT:FAILED` indicating the restart failed.
   - One tagged with `RESULT:WORKED` confirming pool resizing resolved the issue.

### Test 5: The Memory Lift (Dynamic Improvement)
1. Return to **New Investigation**.
2. Select the same sample (**`payments-api Redis pool exhaustion`**) and click **Run AI Investigation**.
3. **Observe how the system improved:**
   - Badge now displays: **`Memory Used`** (in green).
   - Under **Troubleshooting Roadmap**:
     - The connection pool increase is promoted to **Rank 1** with a green **`⚡ Memory Effect: Ranked up: Prior WORKED outcome recorded in Hindsight`**.
     - The restart step is demoted to the bottom with a red **`⚠️ Warning`** warning against repeating the failed step.
   - Under **Cited Hindsight Memories**, click/inspect the references (`M1`, `M2`) showing the exact historical context retrieved.

### Test 6: Verify Recurring Patterns & Topology
1. Click **Recurring Patterns** in the sidebar:
   - Notice the system groups the Redis pool incidents into a single recurring failure loop with count, first seen, last seen, and the proven resolution.
2. Click **Service Topology**:
   - Inspect `payments-api` and dependent infrastructure (`payments-redis`, `payments-db`, `api-gateway`).

### Test 7: Export Postmortem Report
1. Click **Postmortem Reports** in the sidebar.
2. Find the incident you just investigated.
3. Click **Printable PDF** to open the clean executive postmortem document (ready for print / Save as PDF).
4. Or click **Markdown** to download the raw markdown report.

---

## 5. Automated Verification Checks
You can run automated tests anytime:

```powershell
.\.venv\Scripts\pytest.exe -q
```
Expected result: `37 passed, 1 skipped in ~7s`.

