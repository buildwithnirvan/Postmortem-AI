# Demo script (about 3 minutes)

**Setup before recording:** fresh bank (Reset memory), app open, font size large, notifications off.

**0:00 Intro (20s).** "I'm [name]. This is Postmortem, an on-call copilot that remembers which
fixes actually worked, using Hindsight for memory. It only advises; it never touches production."

**0:20 The problem (40s).** Load sample A, Generate with an empty bank. "No history, so it gives
the textbook answer: restart the pods." Mark *restart* **Failed** ("came back in 12 minutes") and
the pool-limit step **Worked**. Save. "That's the 3am lesson most teams lose."

**1:00 Memory is real (30s).** Open *Memory inspector*, search "restart". Point at the stored
facts and the `result:failed` / `result:worked` tags. "That's Hindsight, not a prompt hack."

**1:30 The improvement (60s).** Back to *Incident*, Generate sample A again. "Same incident.
Now the pool fix is first, restart is last with a warning." Click an evidence chip so it scrolls
to the recalled memory. Show the green "Memory effect" line. Untick *Use memory* and regenerate:
"Switch memory off and we're back to generic."

**2:30 Wrap (30s).** "Memory here is outcomes, not transcripts: each confirmed result changes
the next recommendation. Surprise: the most valuable memory was the failures." Show the repo.
