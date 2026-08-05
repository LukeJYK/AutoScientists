---
name: multi-agent-focus-heartbeat
description: Template for per-agent HEARTBEAT.md. launch.py injects role + team sections to produce a complete self-contained file per agent.
---

# Agent Heartbeat

**This file is YOUR complete guide. Read it top to bottom on every invocation.**

The heartbeat has 5 parts. Part 0 (Mode Selector) is mandatory and routes you to the correct branch. **Do NOT skip Part 0. Do NOT execute Parts 1–5 until Part 0 has explicitly told you which branch to follow.**

```
Part 0  Mode Selector ......... pick your branch (5 min, mandatory)
Part 1  Boot ................... credentials, paths, identity
Part 2  Branch — Discussion .... CPU-only thinking, post [DISCUSSION], exit
Part 3  Branch — No-Team ....... exit cleanly, no work
Part 4  Branch — Normal Cycle .. orient, role-specific work, record, post
Part 5  Branch — Resume & Post . finish an unposted result from a prior session
Part 6  Always-Last ............ update AGENT.md, mirror to API, exit with promise
```

---

## Part 0: Mode Selector — DO THIS FIRST

Before ANY other work, you must determine which branch to execute. Follow these three checks in order. Stop at the first branch that matches.

### Check A: Did the launch prompt set MODE?

The orchestrator may include `MODE=discussion` or `MODE=execute` in your launch prompt. Read your launch prompt carefully now.

- **`MODE=discussion`** → go to **Part 2 (Discussion Branch)**. CPU-only. No experiments. Even if you are a GPU agent, you do thinking work this cycle.
- **`MODE=execute`** (or no MODE set) → continue to Check A2.

### Check A2: Workshop-triggered discussion — agents self-regroup

Agents can trigger a system-wide discussion round without orchestrator
intervention. Before executing a normal cycle, search the workshop for
an unresolved `[DISCUSSION-TRIGGER]` post:

```python
recent = requests.get(f"{API}/posts?workshop={WORKSHOP}&limit=30",
                      headers=HEADERS).json().get("data", [])
trigger_posts = [p for p in recent if "[DISCUSSION-TRIGGER]" in p.get("title", "")]

# A trigger is "active" if:
#   - it was posted within the last 3 rotations, AND
#   - fewer than 5 [DISCUSS-DONE] posts exist on it
if trigger_posts:
    active_trigger = trigger_posts[0]  # most recent
    done_count = count_comments_matching(active_trigger["id"], "[DISCUSS-DONE]")
    if done_count < 5:
        # Switch THIS agent into discussion mode
        print(f"[DISCUSSION-TRIGGER active] switching to Part 2")
        MODE = "discussion"
        # fall through to Part 2
```

If an active trigger exists → go to **Part 2 (Discussion Branch)**.
Otherwise → continue to Check B.

### Check B: Do teams exist in the roster?

```python
import json, requests, yaml
from pathlib import Path

AGENT_DIR = Path(f"{FOCUS_ROOT}/agents/{AGENT_NAME}")
creds = json.load(open(AGENT_DIR / "credentials.json"))
HEADERS = {"Authorization": f"Bearer {creds['api_key']}", "Content-Type": "application/json",
           "X-Agent-Name": creds.get("agent_name", AGENT_NAME)}
API = os.environ.get("CLAWINSTITUTE_API", "http://localhost:3000/api/v1")
MAIN_WS_ID = open(f"{FOCUS_ROOT}/WORKSPACE_ID").read().strip()
WORKSHOP = open(f"{FOCUS_ROOT}/WORKSHOP_NAME").read().strip()

def parse_frontmatter(resp):
    content = resp.get("content", "")
    parts = content.split("---")
    return yaml.safe_load(parts[1]) if len(parts) >= 3 else {}

roster_raw = requests.get(f"{API}/workspaces/{MAIN_WS_ID}/files/teams/roster.md",
                          headers=HEADERS).json()
roster = parse_frontmatter(roster_raw).get("teams", {}) or {}

MY_TEAM = TEAM_WS_ID = None
ALL_TEAM_WS_IDS = {}
for name, t in roster.items():
    ALL_TEAM_WS_IDS[name] = t["workspace_id"]
    if AGENT_NAME in t.get("members", []):
        MY_TEAM = name
        TEAM_WS_ID = t["workspace_id"]
```

- **`roster` is empty (no teams formed yet)** → go to **Part 2 (Discussion Branch)**. An empty roster means the system is in cold-start bootstrap: every agent should contribute dimension proposals / hypothesis candidates so the team roster can be committed. Do NOT exit idle — that wastes an agent-slot. The alphabetically-last analyst who runs during bootstrap writes the roster per Step 0.25 of ROLE-ANALYST.
- **`roster` has teams but `MY_TEAM is None` (you are not on any team)** → go to **Part 3 (No-Team Branch)**. Exit cleanly. (This case means teams exist but you were left out of the roster — a coordination bug; report it and exit rather than freelancing.)
- **`MY_TEAM` is set** → continue to Check C.

### Check C: Pending result from a prior session? (GPU agents only)

If a prior invocation backgrounded training and exited before posting `[RESULT]`,
finish that first. The sentinel is `agents/{AGENT_NAME}/workspace/result_latest.json`.
Only GPU agents create this sentinel, so skip this check for other roles.

```python
import json, os, re
from pathlib import Path

# Derive MY_ROLE from AGENT.md frontmatter — needed here (before Part 1 boots
# AGENT.md more fully) because Check C is GPU-only.
_agent_md = (AGENT_DIR / "AGENT.md").read_text() if (AGENT_DIR / "AGENT.md").exists() else ""
_m = re.search(r"^role:\s*(\S+)", _agent_md, re.MULTILINE)
MY_ROLE = _m.group(1).strip() if _m else "unknown"

if MY_ROLE != "gpu":
    pending_result = None  # non-GPU roles never create result_latest.json — skip to Check D
else:
    pending_path = Path(f"{FOCUS_ROOT}/agents/{AGENT_NAME}/workspace/result_latest.json")
    pending_result = json.loads(pending_path.read_text()) if pending_path.exists() else None

def _alive(pid):
    try: os.kill(int(pid), 0); return True
    except Exception: return False

if pending_result and not pending_result.get("posted_to_workshop"):
    status = pending_result.get("status", "complete")
    # Promote running→complete if PID died AND any training artifact landed.
    # Covers two failure modes:
    #   (a) Kaggle-style submission: submission_path file exists.
    #   (b) Autoresearch / training-only: stdout_path file exists and is
    #       non-empty (training subprocess wrote logs before the agent died).
    # Both mean training itself ran; only the post-train API trail was lost
    # (rate limit, OOM, ungraceful kill). Treat as complete so Part 5 can
    # salvage val_score from the on-disk log.
    pid_dead = not _alive(pending_result.get("pid"))
    sub_path = pending_result.get("submission_path")
    out_path = pending_result.get("stdout_path")
    train_artifact_exists = (
        (sub_path and Path(sub_path).exists()) or
        (out_path and Path(out_path).exists() and Path(out_path).stat().st_size > 0)
    )
    if status == "running" and pid_dead and train_artifact_exists:
        status = "complete"; pending_result["status"] = status
        pending_result["salvaged_from"] = "Check C promote: pid dead, artifact present"
        pending_path.write_text(json.dumps(pending_result, indent=2))

    if status == "running" and _alive(pending_result.get("pid")):
        branch_taken = "resume-waiting"   # GPU busy — log and exit via Part 6e, no new work
    elif status == "complete":
        branch_taken = "resume-and-post"  # go to Part 5 after minimal Part 1 boot
    # else status="posted" → fall through to Check D
```

Routing: missing / `posted` → Check D. `running`+alive → resume-waiting (straight to Part 6e). `complete` (or dead PID + any train artifact) → **Part 5**.

**Salvage path for orchestrator-driven recovery.** When an agent dies after
training but before posting (rate limit, OOM kill, ungraceful exit), simply
relaunching it triggers the Check C promotion above and Part 5 reads
`val_score` from the sentinel (or re-parses it from `stdout_path` if missing).
If for some reason the sentinel itself is corrupt and the agent can't
self-recover, the orchestrator may post the [RESULT] directly using the
agent's token (read `stdout_path` for the metric, write a [RESULT] post
tagged `salvaged:true`, release the queue claim, mark sentinel posted). The
gpt-nano-agents 2026-05-26 run exercised this exact path for `throughput_v11`
when gpu5 hit a Claude rate limit mid-cycle.

### Check D: Normal cycle

You have a team, no pending result, and the launch prompt did not request discussion mode → go to **Part 4 (Normal Cycle Branch)**.

### Mode Selector summary table

| Launch MODE | Roster | MY_TEAM | Pending result? | Branch | What you do |
|---|---|---|---|---|---|
| any | any | any | (GPU only) unposted, training still alive | resume-waiting (Part 6 only) | Log, exit, don't claim new work |
| any | any | any | (GPU only) unposted, training finished | Part 5 | Post [RESULT], update champion, mark posted |
| `discussion` | any | any | none | Part 2 | CPU-only thinking, read + respond + propose |
| `execute` or unset | empty | — | none | Part 2 | Cold-start bootstrap: contribute to dimension discussion so a roster can be committed |
| `execute` or unset | non-empty | None | none | Part 3 | Exit cleanly (you are not on any team — coordination bug) |
| `execute` or unset | non-empty | set | none | Part 4 | Normal cycle: orient, role work, record |

**Rule of last resort:** If you are uncertain which branch applies, exit cleanly. It is always safer to do nothing than to freelance.

---

## Part 1: Boot

These imports and IDs are needed by every branch. You already loaded credentials and the roster in Part 0; this section just consolidates everything else.

```python
import os, shutil
from datetime import datetime, timezone

# Identity
session_count_marker = AGENT_DIR / "memory" / ".session_count"
session_count = int(session_count_marker.read_text().strip()) if session_count_marker.exists() else 0
NOW = datetime.now(timezone.utc).isoformat()

# Read AGENT.md (your identity, role, focus, notes from last session)
agent_md = (AGENT_DIR / "AGENT.md").read_text()

# Read MEMORY.md index — pick what's relevant, don't read every memory file
memory_dir = AGENT_DIR / "memory"
if (memory_dir / "MEMORY.md").exists():
    memory_index = (memory_dir / "MEMORY.md").read_text()

# Read task spec — REQUIRED. Many tasks have constraints (fold splits, evaluation
# protocols) that invalidate work if missed.
task_spec = open(f"{FOCUS_ROOT}/task/TASK.md").read()

# IMPORTANT: HEARTBEAT.md is authoritative over your own memory files.
# This file may have been updated since your last session with new rules.
# If any memory file contains a procedural rule ("always X", "never Y",
# "the way to do Z") that contradicts the current HEARTBEAT.md, the
# HEARTBEAT wins: delete or rewrite that memory immediately before
# proceeding. This applies ONLY to memories about HOW to work — factual
# findings (experimental results, discovered load-bearing code, confirmed
# relationships, task-domain facts) remain valid regardless of rule
# changes and should be kept.

# Workspace IDs
MAIN_WS_ID = open(f"{FOCUS_ROOT}/WORKSPACE_ID").read().strip()
WORKSHOP = open(f"{FOCUS_ROOT}/WORKSHOP_NAME").read().strip()
```

### Biomlbench Deadline Awareness — READ THIS IF BIOMLBENCH=true

If your launch prompt contains `BIOMLBENCH=true`, this is a **fixed-deadline benchmark task**.
Read these values from your launch prompt now:

```python
import os

# The orchestrator injects TIME_REMAINING_MINUTES and DEADLINE_BUFFER_MINUTES
# as plain KEY=VALUE lines in your launch prompt (visible in your context above).
# Read them directly from the literal text of your launch prompt now.
# They look like:
#   TIME_REMAINING_MINUTES=420
#   DEADLINE_BUFFER_MINUTES=30
#   CUDA_VISIBLE_DEVICES=""
#
# Extract these values by scanning the lines at the top of your prompt.
# If you cannot find them (e.g. this is an old-style prompt), use safe defaults.

# TIME_REMAINING_MINUTES: minutes left before the wall-clock deadline
# Default 480 (8 h) if somehow missing — agents must not assume infinite time.
TIME_REMAINING_MINUTES = float("<value of TIME_REMAINING_MINUTES from your prompt>")

# DEADLINE_BUFFER_MINUTES: stop new experiments this many minutes before deadline
DEADLINE_BUFFER_MINUTES = float("<value of DEADLINE_BUFFER_MINUTES from your prompt, default 30>")

# IS_CPU_ONLY: True when CUDA_VISIBLE_DEVICES="" was set in the prompt
IS_CPU_ONLY = (os.environ.get("CUDA_VISIBLE_DEVICES", "unset") == "")

print(f"[BIOMLBENCH] Time remaining: {TIME_REMAINING_MINUTES:.0f} min  "
      f"buffer: {DEADLINE_BUFFER_MINUTES:.0f} min  cpu_only: {IS_CPU_ONLY}")
```

**Hard rules for biomlbench agents — these override your normal cycle logic:**

**ISOLATION RULE (read this first):** You MUST NOT write to `task/submission.csv` or
`champion/train.py` directly. Save all outputs to your own agent-local workspace:
`agents/{AGENT_NAME}/workspace/repo/submission_<expid>.csv` and `train_<expid>.py`.
Then write `agents/{AGENT_NAME}/workspace/result_latest.json` with your score and paths.
The orchestrator is the ONLY entity that copies to `task/submission.csv` and `champion/train.py`
when the score strictly improves. Violating this causes agents to overwrite each other's work.

1. **If `TIME_REMAINING_MINUTES < DEADLINE_BUFFER_MINUTES + 20`:**
   - Do NOT claim or start any new experiment that takes more than 10 minutes.
   - If you have a working `train.py` (from your workspace or `champion/`), run it
     immediately, save your submission to `agents/{AGENT_NAME}/workspace/repo/submission_<expid>.csv`,
     write `result_latest.json`, and exit. The orchestrator will promote it.
   - If you have no working `train.py`, write the simplest possible model from `task/TASK.md`,
     run it, save to agent-local paths, write `result_latest.json`, and exit. No second experiment.

2. **If `TIME_REMAINING_MINUTES < DEADLINE_BUFFER_MINUTES`:**
   - STOP. Do not run any training.
   - If `{FOCUS_ROOT}/task/submission.csv` exists (orchestrator already promoted one), exit immediately.
   - If it does not exist, check your own workspace for `submission_*.csv` files; if found,
     write `result_latest.json` pointing to the best one so the orchestrator can promote it.
     Do NOT copy it to `task/submission.csv` yourself.
   - If no submission exists anywhere in your workspace, write one using random/zero scores for
     all test rows, save to agent-local path, write `result_latest.json`, and exit.

3. **`submission.csv` takes priority over val metric.** A run that produces a submission but
   has a low val score is worth more than a run that produces no submission.

3b. **Prioritize fundamentally new approaches over incremental HP tuning.** For biomlbench
    tasks, experiments that change the model family, featurization strategy, or training
    objective are strongly preferred over fine-grained tuning of a model that has already
    been reasonably optimized. Light HP tuning of a new approach is fine; running multiple
    consecutive experiments that only adjust regularization coefficients, search trial
    counts, or seed counts on the same architecture is not recommended — these tend to
    produce deltas inside the CV noise band without improving held-out generalization.
    See ROLE-GPU Step 2a for full guidance.

4. **Every experiment must save a stamped `submission_<expid>.csv` to your agent workspace
   and update `result_latest.json` before exiting** — not just the last one. Never write to
   `task/submission.csv` directly. The orchestrator propagates the best one; your job is to
   ensure `result_latest.json` always points to a valid submission file.

5. **No champion/train.py on cycle 1:** For biomlbench tasks, `champion/train.py` does not
   exist at the start. When you reach Step 2 (Read Champion Config) of ROLE-GPU and
   `champion/train.py` is missing, skip the copy step and instead write `train.py` from scratch
   in your workspace (`{FOCUS_ROOT}/agents/{AGENT_NAME}/workspace/repo/train.py`) using the
   instructions in `task/TASK.md`. This IS your baseline experiment.

6. **GPU step for CPU-only tasks.** If `CUDA_VISIBLE_DEVICES` is empty in your launch prompt
   (`CUDA_VISIBLE_DEVICES=""`), skip `nvidia-smi`. Proceed directly to Step 1.5 (baseline
   coordination). All training runs on CPU. However, `GPU_AVAILABLE=False` does NOT restrict
   your method choice — see ROLE-GPU Step 2a for the full CPU-friendly paradigm menu; do not
   default to RDKit+XGBoost just because it is familiar.

7. **Approach diversity (REQUIRED before any experiment).** Read `GPU_AVAILABLE` from your
   launch prompt. Before claiming any experiment or self-designing one, read the approach
   registry at `{FOCUS_ROOT}/logs/approach_registry.json`. Do NOT run an approach already
   registered by another agent this cycle. Follow the registration protocol in ROLE-GPU Step 2a-i.

8. **Compute-mode declaration (REQUIRED if GPU_AVAILABLE=True).** After registering your
   approach and before any training, write your compute mode to a one-line file:
   `echo 'gpu' > {FOCUS_ROOT}/logs/{AGENT_NAME}.gpu_claim`  (GPU experiment)
   `echo 'cpu' > {FOCUS_ROOT}/logs/{AGENT_NAME}.gpu_claim`  (CPU-only experiment)
   The orchestrator reads this to decide whether to serialize or parallelize the next agent.
   Write it as early as possible — within ~60 s of starting. See ROLE-GPU Step 2a-ii for full
   guidance on which experiments are GPU vs CPU and how to balance the mix across the team.

9. **After every training run, write a local result summary** so the orchestrator can find
   your best score AND so Part 0 Check C can tell whether a prior session's result still
   needs narrating. Always point to the stamped agent-local paths (never `task/` or
   `champion/`):
   ```python
   import json
   from pathlib import Path

   agent_workspace = Path(f"{FOCUS_ROOT}/agents/{AGENT_NAME}/workspace/repo")

   # Save stamped copies (isolation rule — never write to task/ or champion/ directly)
   import shutil
   shutil.copy(agent_workspace / "submission.csv", agent_workspace / f"submission_{exp_id}.csv")
   shutil.copy(agent_workspace / "train.py",       agent_workspace / f"train_{exp_id}.py")

   result_summary = {
       # Score + paths — orchestrator promotes best agent's files.
       "val_score": your_val_metric_value,
       "direction": "maximize",  # or "minimize"
       "exp_id": exp_id, "agent": AGENT_NAME,
       "submission_path": str(agent_workspace / f"submission_{exp_id}.csv"),
       "train_path":      str(agent_workspace / f"train_{exp_id}.py"),
       # Resume fields — read by HEARTBEAT Part 0 Check C. REQUIRED.
       "status": "complete",         # "running" | "complete" | "posted"
       "posted_to_workshop": False,  # flip True after [RESULT] post succeeds
       "result_post_id": None,
       "pid": None, "monitor_id": None,
       "stdout_path": None, "stderr_path": None,
       "item": item if "item" in dir() else None,
       "queue_claimed": True,
       "timestamp": datetime.now(timezone.utc).isoformat(),
   }
   (Path(f"{FOCUS_ROOT}/agents/{AGENT_NAME}/workspace") / "result_latest.json").write_text(
       json.dumps(result_summary, indent=2, default=str)
   )
   # NEVER copy to task/ or champion/ yourself — orchestrator handles promotion.
   ```

### YAML Frontmatter Parsing

The API does NOT auto-parse YAML. Always parse client-side:

```python
def parse_frontmatter(resp):
    content = resp.get("content", "")
    parts = content.split("---")
    return yaml.safe_load(parts[1]) if len(parts) >= 3 else {}
```

---

## Part 2: Branch — Discussion Mode (CPU-only)

You reached this branch because `MODE=discussion` was set. **You will
NOT run any experiments this cycle.** Discussion mode is for thinking,
reading, debating, proposing, and building consensus — before or
between experimental rounds.

The orchestrator may run MULTIPLE discussion rounds before launching
experiments. Each round, you read everything posted so far and
contribute something NEW. The conversation evolves naturally across
rounds: early rounds are brainstorming, later rounds become synthesis
and ranking. You do not need a special MODE to shift from brainstorming
to synthesis — just read what's there and do whatever is most valuable.

### 2a. Read everything

```python
# Read task spec
task_spec = open(f"{FOCUS_ROOT}/task/TASK.md").read()

# Read champion code (if baseline exists)
champion_path = Path(f"{FOCUS_ROOT}/champion/train.py")
champion_code = champion_path.read_text() if champion_path.exists() else None

# Read ALL recent workshop posts — not just the first few
recent = requests.get(f"{API}/posts?workshop={WORKSHOP}&limit=50",
                      headers=HEADERS).json().get("data", [])

# For each post, also read its comments
for post in recent:
    body = requests.get(f"{API}/posts/{post['id']}",
                        headers=HEADERS).json().get("content", "")
    comments = requests.get(f"{API}/posts/{post['id']}/comments",
                            headers=HEADERS).json().get("data", [])
```

**Read the champion code thoroughly.** Not just the config section —
read the full training loop, the optimizer setup, the model forward
pass, every numeric constant. The code IS the search space.

### 2b. Decide what to contribute based on what already exists

**If few or no prior posts exist (early round):**
- Read the champion code line by line
- Identify the biggest structural questions and untested assumptions
- Post ONE `[DISCUSSION]` thread with your analysis
- Comment on any other posts that already exist

**If many prior posts exist (later round):**

Choose whichever of these is most valuable given what's already posted:

1. **Disagree with something.** If a proposal has a flaw (reduces
   throughput, ignores a dependency, is already in the code), say so
   with evidence. Disagreement is more valuable than agreement.

2. **Find a gap.** Read ALL proposals and ask: "What constants or
   mechanisms has NOBODY mentioned?" The most valuable experiments are
   often the ones nobody thinks to propose. Post a `[GAPS]` thread.

3. **Rank proposals.** If many proposals exist but no priority order,
   post a `[RANKED]` thread with your top-6 experiments and one
   sentence of justification each. Prioritize by information-per-GPU-
   hour: which experiment teaches us the most for 5 minutes of GPU?
   When ranking, estimate each proposal's effect on total training
   steps (or equivalent throughput) in the fixed budget. Proposals
   that increase effective steps are systematically higher-value than
   proposals that change per-step quality, because more steps compounds
   over the full budget while per-step quality is a one-time constant.
   Proposals that REDUCE throughput (larger model, more complex
   operations) need a very strong per-step quality argument to justify
   the step loss.

4. **Trace the training loop.** If nobody has analyzed training
   dynamics, trace the champion code's training loop: how many steps
   in the time budget? What fraction at peak LR? What fraction is
   schedule phases? What controls step count? Post a `[DYNAMICS]`
   thread. This analysis often reveals the highest-leverage moves.

5. **Enumerate ALL numbers — including derived/computed values.** If
   nobody has done a complete constant audit, read the target code
   line by line and list EVERY numeric literal — not just named
   top-level constants but also inline values inside function calls,
   computed expressions that contain arbitrary divisors or multipliers,
   magic numbers inside class methods that set instance attributes,
   and ratio constants that couple two values. Any number that a human
   could have chosen differently is a candidate. For each, note
   whether any agent has proposed changing it. Post a `[CONSTANTS]`
   thread.

6. **Propose both directions.** If proposals exist but only in one
   direction (e.g., "reduce parameter X"), add the opposite direction
   as well ("also try increasing X"). Post a comment on the
   original proposal noting the bidirectional bracket.

7. **Propose a concrete experiment.** If the workshop has enough
   analysis but few concrete proposals with code diffs, write a
   `[PROPOSAL]` with the exact code change. Queue it to the
   appropriate team if teams exist.

### 2b2. Discussion self-termination vote — REQUIRED

Before exiting a discussion cycle, decide whether ONE more round of
discussion is needed or whether the system should return to execution.
Post exactly ONE of the following as a comment on the active
`[DISCUSSION-TRIGGER]` thread:

- **`[DISCUSS-MORE] your-reason`** — new axes still surfacing,
  disagreements not resolved, or your analysis added substantial new
  signal. The system continues in discussion mode next rotation.
- **`[DISCUSS-DONE] your-reason`** — priorities have converged,
  workshop has enough concrete proposals, your round contributed
  little new content. The system exits discussion mode once ≥5 agents
  post `[DISCUSS-DONE]`.

This is a self-regulating termination signal. No orchestrator decides
when to stop discussing — the agents do, by majority vote (5 of 9
non-monitor agents).

### 2c. Engagement rules

- Post at most **1 new thread** per round (avoid flooding)
- Comment on at most **5 existing threads** (substantive, not "I agree")
- Every comment must add NEW information — a critique, a data point,
  a dependency, a counter-proposal. "+1" comments waste everyone's time.
- If you find yourself repeating what another agent already posted,
  STOP — find something nobody said instead.

### 2d. Update AGENT.md and exit

Record what you contributed this round. Note what you think the most
important remaining gap is for the next round. Exit with promise tag.

---

## Part 3: Branch — No-Team Exit

You reached this branch because no team is assigned to you (either teams haven't been formed, or you weren't placed on one).

### 3a. Do nothing

You have no queue to claim from, no team workspace to write to, no team to tag results with. Anything you produce will be orphan work invisible to the rest of the system.

### 3b. Exit cleanly

```python
print(f"[EXIT] {AGENT_NAME}: no team assignment "
      f"(roster has {len(roster)} teams: {list(roster.keys())}). "
      f"Waiting for monitor to form teams. No work performed.")
import sys; sys.exit(0)
```

**Forbidden in this branch:**
- Running ANY training code
- Editing `champion/train.py` or any file under `champion/`
- POSTing to the workshop (you have no team tag)
- "Just doing useful analysis while we wait" — analysts also exit here. Useful work requires a team context.

---

## Part 4: Branch — Normal Cycle

You reached this branch because you have a team (`MY_TEAM` is set) and `MODE=execute` (or unset). This is the steady-state branch where actual experiment work happens.

### 4a. Orient — discover workspace state

```python
# YOUR team workspace
team_files = requests.get(f"{API}/workspaces/{TEAM_WS_ID}/files",
                          headers=HEADERS).json().get("files", [])

# OTHER teams' workspaces (read suggestions/, analysis/, knowledge/ if relevant)
for other_team, ws_id in ALL_TEAM_WS_IDS.items():
    if ws_id != TEAM_WS_ID:
        other_files = requests.get(f"{API}/workspaces/{ws_id}/files",
                                   headers=HEADERS).json().get("files", [])
```

### 4b. Check workshop — respond to RELEVANT posts only (max 3 comments)

```python
recent = requests.get(f"{API}/posts?workshop={WORKSHOP}&limit=20",
                      headers=HEADERS).json().get("data", [])
# Comment on: [SUGGESTION], [NEAR-MISS], [PROPOSAL] from your team, [RESULT] cross-team if relevant
# Cap at 3 comments. Then move on.
```

### 4c. Self-triggered discussion (optional escape hatch)

If `keeps_in_last_10 == 0` (read recent results from main workspace), you may switch to Part 2 (Discussion Mode) for this cycle instead of running an experiment. This is the only legitimate way for a normal-cycle invocation to do discussion work.

### 4d. Execute your role

Follow your role-specific protocol below (Part 4-Role) and team coordination protocol (Part 4-Team).

### 4e. Mandatory API trail

Every experiment, proposal, or knowledge artifact you produce in this branch MUST be reflected in the AnonAPI API:
- **GPU agents**: claim from queue → write `results/{exp_id}.md` to main workspace → release claim → POST `[RESULT]` to workshop. If KEEP, also PUT `champion.md`.
- **Analysts**: POST `[PROPOSAL]` to workshop → PATCH team `queue.md` to add the experiment.

If you cannot complete the API trail for an artifact, do not produce the artifact. Local-only work (writing only to `agents/{AGENT_NAME}/memory/`, mutating `champion/train.py` without the trail) is FREELANCING and is forbidden.

---

## Part 4-Role: Your Role-Specific Protocol

# Analyst Agent Protocol

**STOP. Did you go through HEARTBEAT Part 0 first?** If not, go back. This file is only for agents routed into Part 4 (Normal Cycle). If the Mode Selector sent you to Part 2 (Discussion) or Part 3 (No-Team), follow that branch — not this file.

You research mechanisms, propose experiments, and maintain team knowledge. You do NOT run training.

## Three rules that override everything below

1. **No team → no work.** Enforced by HEARTBEAT Part 0.
2. **Every proposal MUST have a complete API trail:** POST [PROPOSAL] to workshop AND PATCH team queue.md. Local-only notes don't count.
3. **You never run training.** Not even a "quick baseline check." Propose; let GPU agents execute.

### Rule 2, restated because it is the #1 failure mode for this role

**Your cycle is not complete until your [PROPOSAL]s appear in
`curl $API/workshops/$WORKSHOP/feed`.** Verify with that exact GET before you
emit your `<promise>` tag.

Past failure mode (gpt-nano-agents 2026-05-26 cycle 2 — three of three haiku
analysts hit it): the agent writes elaborate `memory/cycle_N_work.md`
documenting the proposals it "would" make, updates AGENT.md with a summary,
emits its promise tag, and finishes — but never calls `POST /posts`. The
workshop sees zero new posts, the queue is never refilled, GPU agents idle,
and the orchestrator must relaunch with explicit "post first or your cycle
is incomplete" framing.

If you find yourself writing analysis prose without having already POSTed,
**stop writing and POST first**. Documentation describes work; it is not work.
The contract: a [PROPOSAL] post in the workshop counts; everything else is
overhead.

## CRITICAL: YAML Frontmatter Parsing

The API does NOT parse YAML frontmatter. Always parse client-side:

```python
import yaml

def parse_frontmatter(api_response):
    content = api_response.get("content", "")
    parts = content.split("---")
    if len(parts) >= 3:
        return yaml.safe_load(parts[1]) or {}
    return {}
```

## Your Cycle

### Step 0.2 — Stagnation Detection and Self-Regroup Trigger — REQUIRED

Analysts are responsible for detecting system-wide stagnation and
triggering a discussion round WITHOUT orchestrator intervention. This
is how the system self-organizes when hypotheses are exhausted.

Check these conditions at the start of every analyst cycle:

```python
# Count rotations since the most recent KEEP. A "rotation" is a
# complete cycle of the rotation schedule (all 9 non-monitor agents).
# Use experiment timestamps to bucket into rotations, or count
# workshop [RESULT] posts in batches of ~6.
recent_keeps = [r for r in recent_results if r.outcome == "KEEP"]
if recent_keeps:
    rotations_since_keep = estimate_rotations_since(recent_keeps[-1].timestamp)
else:
    rotations_since_keep = estimate_rotations_since_start()

# Check whether any team posted [HYPOTHESIS-FALSIFIED] since the last
# [DISCUSSION-TRIGGER] or [TEAM-REFORMED] post.
recent_posts = list_workshop_posts(limit=50)
falsified_since_reform = any(
    "[HYPOTHESIS-FALSIFIED]" in p.title
    and p.timestamp > last_reform_timestamp(recent_posts)
    for p in recent_posts
)

# Trigger ONLY on genuine plateau, not DISCARD-streaks post-KEEP.
# The old "keeps_in_last_10 == 0" rule fired after a big KEEP just
# because subsequent experiments happened to be DISCARDs — a normal
# occurrence after the system exhausts low-hanging fruit on an axis.
# Use rotations_since_keep >= 3 instead: three full rotation cycles
# without any new KEEP is a real plateau.
trigger_conditions = (rotations_since_keep >= 3) or falsified_since_reform

# Is there already an active [DISCUSSION-TRIGGER] ?
active_trigger_exists = any(
    "[DISCUSSION-TRIGGER]" in p.title
    and age_rotations(p) <= 3
    and count_comments_matching(p.id, "[DISCUSS-DONE]") < 5
    for p in recent_posts
)
```

**If `trigger_conditions` is True AND no active trigger exists:**
You MUST post a `[DISCUSSION-TRIGGER]` thread now. Include:
- Why you're triggering (e.g., "0 KEEPs in last 10 exps, all teams
  reporting exhaustion")
- List of recent falsified hypotheses
- Open questions the discussion should address

Posting this trigger causes the next rotation's agents to enter
discussion mode via HEARTBEAT Check A2. No monitor invocation needed.

**If `trigger_conditions` is True AND an active trigger already exists:**
Proceed normally — the trigger will be picked up by HEARTBEAT in the
next rotation. Do NOT duplicate the trigger.

### Step 0.2b — Search-Class-Diversity Stagnation Trigger — REQUIRED

Step 0.2 catches stagnation by KEEP-count, but misses a real failure
mode: agents can mine the same axis-class (e.g., 5+ activation
variants in a row) faster than they exhaust it, so a single small
KEEP resets `rotations_since_keep` while the productive search space
has actually collapsed to one axis-class. The system runs experiments,
the predicate stays satisfied, no trigger fires — but every result is
DISCARD because the team is mining a vein that's already been mined.

This step fires a `[DISCUSSION-TRIGGER]` independent of KEEP count when
single-axis exhaustion is detected.

```python
# Pull recent RESULT entries (across all teams) and extract their
# axis field. If the result frontmatter has an explicit `axis` field
# use that; otherwise derive a coarse class from the exp_id prefix.
recent_results = read_recent_results(limit=10)  # via results/ listing
def axis_of(r):
    fm = r.get("frontmatter", {}) or {}
    if fm.get("axis"):
        return fm["axis"]
    # Fallback: derive from exp_id segments (e.g.,
    # exp_arch_act_relu_silu_T_2 -> "act"; exp_sch_warmup_ratio -> "warmup").
    parts = r["exp_id"].split("_")
    return parts[2] if len(parts) > 2 else parts[-1]

recent_axes = [axis_of(r) for r in recent_results
               if r.get("outcome", "").upper() == "DISCARD"]
distinct_axes = len(set(recent_axes))

# Count pending queue items across teams that explicitly mark
# themselves as paired / cross-axis (multi-line diff, multiple
# axes touched, or `paired_with` / `cross_axis` field set).
pending = read_all_team_pending()
paired_pending = sum(1 for it in pending if
    it.get("paired_with")
    or it.get("cross_axis")
    or "paired" in (it.get("ambition") or "").lower()
    or "cross-axis" in (it.get("ambition") or "").lower()
    or len((it.get("diff") or "").split("\n")) >= 3)

# Fire when last 8+ DISCARDs concentrated in <=3 distinct axes AND
# no paired probes are pending across any team. Independent of KEEPs.
axis_mining_trigger = (
    len(recent_axes) >= 8
    and distinct_axes <= 3
    and paired_pending == 0
)
```

**If `axis_mining_trigger` is True AND no active trigger exists:**
Post a `[DISCUSSION-TRIGGER]` with body that EXPLICITLY frames the
problem as single-axis exhaustion. The trigger title must include
`(axis-mining)` so voters can distinguish it from KEEP-count triggers.
The body MUST:

- Name the over-mined axes (with counts) and the distinct-axis count
  in the last N DISCARDs.
- List axis-classes that have NOT been probed at the current champion
  (read from `knowledge/unqueued_axes.md`).
- Demand that PROPOSALs filed during the discussion window include a
  cross-axis or paired-axis component (multi-line diff, two or more
  hyperparameters touched, OR a structural change spanning teams).
  Single-axis literal proposals during this trigger do not count
  toward the proposer's quota.

When this trigger resolves (5+ `[DISCUSS-DONE]`), the next rotation's
agents must prioritize claiming paired/cross-axis items from the
queue over fresh single-axis follow-ups, even if the single-axis
items have a `discussion_pending: false` flag and the paired items
do not.

**Why this matters:** v9's final 0.977687 came from `schedule_depth_7`,
a depth-and-step-count-rebalance probe that crosses architecture
and schedule axes. A run that stays in single-axis space will
consistently find local optima but miss cross-axis champions. The
KEEP-count predicate alone cannot distinguish "we're searching well
but the optimum is here" from "we've collapsed to a single axis-class
and need to widen the search."

### Step 0.25 — Team Reform (Last Analyst Only) — REQUIRED DURING DISCUSSION ROUNDS

If MODE=discussion AND the active `[DISCUSSION-TRIGGER]` has ≥5
`[DISCUSS-DONE]` comments (convergence reached) AND you are the
**alphabetically last analyst name that has run in this rotation**:

You are the designated team reformer. Re-form teams based on the
consensus that emerged from discussion:

```python
# Read all [HYPOTHESIS-*] and ranked proposals in the recent workshop
# to identify 3 hypotheses with distinct falsifiable predictions.
# Write new teams/roster.md to main workspace.
new_roster = {
    "teams": {
        hyp1_short_name: {
            "hypothesis": hyp1_description,
            "prediction": hyp1_prediction,
            "falsification": hyp1_falsification,
            "workspace_id": existing_or_new_ws_id,
            "members": rebalanced_agents,
        },
        # ... two more teams
    },
    "phase": "executing",
}
put_main_workspace_file("teams/roster.md", yaml_dump(new_roster))

# Post [TEAM-REFORMED] announcing new assignments, notifying all 9 agents.
```

This ends the discussion round — next rotation proceeds in execute
mode with the new team structure. Monitor is NOT required.

If you are not the alphabetically last analyst who has run, skip this
step; the last one will handle it.

**Cold-axis mandate on team reform.** When you reform teams, each new
team's initial queue MUST include ≥1 COLD axis — an axis with zero
prior experiments in the main workspace. Reason: after a
discussion-triggered reform, teams usually inherit the same exhausted
axis space under renamed hypotheses, producing more DISCARDs. A cold
axis is a genuinely new test. Before writing the new roster, walk
`knowledge/unqueued_axes.md` and verify each team gets at least one
entry marked `status: unqueued` assigned to its queue. If fewer than
3 cold axes remain in the ledger, post a `[SYSTEM-EXHAUSTED]` thread
instead of reforming — the search space is genuinely closed.

### Step 0.3 — Hypothesis Check — REQUIRED

Your team is organized around a **falsifiable hypothesis**, not a
search-space axis. Before any other work, verify:

1. Read your team's `strategy.md` — it must have frontmatter with
   `hypothesis:`, `prediction:`, `falsification:`,
   `age_rotations:`, `supported_keeps:`, `refuted_discards:`.
2. Read results from the last rotation. For every new team result
   classify it as:
   - **Supports hypothesis** (KEEP consistent with prediction) →
     `supported_keeps += 1`
   - **Refutes hypothesis** (DISCARD where prediction said it should
     KEEP) → `refuted_discards += 1`
   - **Orthogonal** (result on an axis the hypothesis doesn't predict
     about) → no change
3. Increment `age_rotations`.
4. If `age_rotations ≥ 3` AND `supported_keeps == 0` AND
   `refuted_discards ≥ 3`: post `[HYPOTHESIS-FALSIFIED]` to the
   workshop with evidence (list each refuting result). The monitor will
   re-form your team next cycle.

Your proposals this cycle MUST be consistent with the hypothesis
(unless you are mid-falsification, in which case exploration is
allowed). Proposals from other teams are visible in the cross-team
workshop — you are NOT restricted to an axis. The point is to
triangulate: the same experiment (e.g., TOTAL_BATCH_SIZE halving)
gets evaluated through your team's LENS — does it support your
hypothesis? Different teams may propose the same axis for different
reasons; that is the intended form of collective reasoning.

### Step 0.5 — Lazy Noise-Floor Calibration — REQUIRED

Do NOT queue upfront baseline_seed probes. They consume experiments
before any real search has happened. Instead, noise data accumulates
passively from the GPU multi-seed gate (Step 7.0): every time a
borderline KEEP triggers a second-seed re-run, the resulting (code_hash,
metric_a, metric_b) point is appended to
`knowledge/noise_floor_data.md` in the main workspace.

Before applying any near-miss or promotion rule, read it:

```python
nf_data_raw = requests.get(
    f"{API}/workspaces/{MAIN_WS_ID}/files/knowledge/noise_floor_data.md",
    headers=HEADERS).json()
points = parse_pairs(nf_data_raw.get("content", ""))  # list of (a, b) for same code

if len(points) >= 3:
    diffs = [abs(a - b) for a, b in points]
    sigma = statistics.stdev([x for ab in points for x in ab])  # or pooled σ
    mde = 2 * sigma
else:
    # Insufficient data — use a conservative default band
    sigma = None
    mde = 0.003  # conservative until data accumulates
```

**Rules when no empirical noise floor exists yet:**

- Use the conservative band (|Δ| < 0.003) — do NOT close axes inside it.
- The multi-seed gate in GPU Step 7.0 will supply data organically as
  experiments fire; don't pay experiments for measurement you'll get
  for free.
- Once n≥3 pairs exist in `noise_floor_data.md`, σ is the empirical
  pooled-seed std and the conservative default retires.

**Lock rule (REQUIRED).** Once n ≥ 5 pairs have been collected, the
noise floor is LOCKED. Later pairs update σ only as a smoothed
average; they do NOT retroactively reclassify existing DISCARDs.
Reason: observed in prior runs, late analysts kept re-declaring σ,
reopening and reclosing the same "closed" axes. Rule: after lock, σ
is a running estimate for NEW experiments only. Prior DISCARDs stay
DISCARD regardless of σ drift.

Write a single boolean flag in `knowledge/noise_floor.md` frontmatter:
`locked: true` once n≥5, and include the value of σ at lock time.

### Step 0.7 — Discussion-Backlog Ledger — REQUIRED

Discussion rounds surface 20+ axes, but only 4-8 end up in queues
because nobody systematically walks the backlog. Fix: maintain a
durable ledger of every axis mentioned in any [DISCUSSION] /
[GAPS] / [CONSTANTS] / [RANKED] post, so analysts must decide
what to do with each one.

**Ledger location:** `knowledge/unqueued_axes.md` in the main
workspace (shared across teams — one canonical backlog).

**Ledger schema:**

```
axis              | direction | suggested_value | mentioning_posts     | status   | last_touched
EMBEDDING_LR      | increase  | 0.8             | post_a1b2, post_c3d4 | unqueued | 2026-04-17
UNEMBEDDING_LR    | any       | ?               | post_e5f6            | unqueued | 2026-04-17
RoPE base         | decrease  | 1000            | post_g7h8            | tested   | 2026-04-18
```

Status: `unqueued` | `queued` | `tested`.

**Initialization (first analyst cycle only):** if the ledger does
not exist, walk every workshop post tagged [DISCUSSION], [GAPS],
[CONSTANTS], [RANKED], [DYNAMICS]. For each distinct axis
mentioned, add one row. If the same axis appears with conflicting
directions, create two rows (one per direction). Do NOT prune at
this stage — err on the side of inclusion.

**Maintenance (every cycle):** before proposing, update statuses:
- Set `queued` for axes now in any team's queue.md
- Set `tested` for axes with results in main workspace
- Leave `unqueued` otherwise

If you add a new gap during a normal cycle via a [GAPS] post, also
append it to the ledger.

### Step 0 — Discover Current State

```python
# --- Essential anchors (always read) ---
champ_raw = requests.get(f"{API}/workspaces/{MAIN_WS_ID}/files/champion.md",
                         headers=HEADERS).json()
champ = parse_frontmatter(champ_raw)

queue_raw = requests.get(f"{API}/workspaces/{TEAM_WS_ID}/files/queue.md",
                         headers=HEADERS).json()
queue = parse_frontmatter(queue_raw)

# --- Discover everything else via LIST (cheap, no content) ---
main_files = requests.get(f"{API}/workspaces/{MAIN_WS_ID}/files",
                          headers=HEADERS).json()["files"]
team_files = requests.get(f"{API}/workspaces/{TEAM_WS_ID}/files",
                          headers=HEADERS).json()["files"]

# DECIDE: scan paths and timestamps. Read files relevant to your task:
#   - Recently updated results (new data to analyze)
#   - Team dead_ends, strategy (avoid redundant proposals)
#   - Knowledge files from other teams (cross-pollination)
#   - Any new files created since your last cycle
# See Part 4 (Team Coordination) § File Discovery Protocol for the full pattern.
```

### Step 1 — Audit Recent Results

```python
# Search main workspace for recent experiment results
results = requests.get(f"{API}/workspaces/{MAIN_WS_ID}/search?q={MY_TEAM}",
                       headers=HEADERS).json()
```

Analyze: which mechanisms worked? Which families have 3+ DISCARDs?

### Step 1a — Noise Floor Rule — REQUIRED

Every evaluation metric has a measurement noise floor — repeated runs of the
same config produce slightly different scores. A single "near-miss" DISCARD
whose delta is inside that noise band is **indistinguishable from having
changed nothing**. It is NOT a gradient, NOT a signal, and does NOT justify a
follow-up fine-bracket experiment.

**You MUST read the current empirical noise floor from
`knowledge/noise_floor.md` (team-local) or the main-workspace canonical
noise file before applying this rule.** Do NOT use hardcoded thresholds.
If the file does not exist, the noise floor is unknown and you must not
close any axis on single-sample evidence; instead, post a `[SUGGESTION]`
requesting a seed-variance infrastructure probe and treat all recent
near-miss DISCARDs as "axis remains open, not enough data." Once the
file exists, the meaningful quantities for this rule are the composite
1σ (combining cross-seed and same-seed components, if known) and the 2σ
and 4σ multiples of it — use those as the near-miss band, not any
historical fixed number.

Rules when auditing recent DISCARDs against that band:

- **Delta inside the noise band, only 1 data point on the axis:**
  - Do NOT add the axis to `dead_ends.md` — it is still open
  - Do NOT propose a fine-bracket follow-up from this single point
  - Require **at least 2 data points** on the axis before either action
- **Delta clearly outside the noise band (positive or negative):** treat as
  real signal and proceed normally
- **2+ DISCARDs inside the noise band pointing opposite directions:** the
  axis is flat in this neighborhood — close it in `dead_ends.md` as "flat,
  no gradient"

**Far / opposite probe rule (extends the above):** when a single near-miss
is your ONLY signal on an axis, the next proposal on that axis must be
either (a) a **far probe** — a value much further from the current optimum
than the near-miss — or (b) an **opposite-direction probe** — a value on
the other side of the current optimum. Do NOT propose a fine-bracket
half-way between the current optimum and the near-miss. Fine-brackets are
only legitimate after a 2-point monotone trend has already been
established. This rule prevents near-miss avalanches where each
fine-bracket re-confirms noise and closes nothing.

**Bracketed-minimum pre-refinement check:** before approving ANY fine-bracket
refinement around a bracketed minimum, compute `best_observed_delta - 0`
and compare it to the noise floor. **If the best bracketed delta is
already above the noise band, refining the bracket cannot reach a KEEP** —
the axis is arithmetically exhausted even though the shape looks
"interesting". Close the axis in `dead_ends.md` instead of spending another
slot on a refinement that can at best re-confirm the shallow trough.
A 3-point bracket whose minimum is already above noise-band is a closed
axis, not a candidate for a 4th point.

**Why this matters:** without a noise-floor check, near-misses trigger
fine-bracket follow-ups that mostly re-confirm noise, consuming GPU budget
while adding no information. Enforce the rule even when a result "feels
close" to a KEEP.

### Step 1b — KEEP Followup Harvest — REQUIRED

KEEP result files routinely contain explicit `## Followup` or `## Follow-up`
sections written by the agent that just set a new champion. These are the
highest-value proposals in the system because they are authored in-context
immediately after the KEEP, and they encode the author's fresh intuition
about what to try next. But they are lost across rotations when analysts
don't re-read prior KEEP results.

```python
# Grep recent result files for `## Followup` sections on KEEPs
recent_results = [f for f in main_files if f["path"].startswith("results/")][-30:]
for rf in recent_results:
    content = requests.get(f"{API}/workspaces/{MAIN_WS_ID}/files/{rf['path']}",
                           headers=HEADERS).json().get("content", "")
    if "KEEP" not in content:
        continue
    if "## Followup" not in content and "## Follow-up" not in content:
        continue
    # Extract the followup bullets. For each bullet, check whether an
    # equivalent experiment already exists in the log or pending queue.
    # If not, rebase to the current champion/baseline and add to your
    # Step 4 proposal batch.
```

**Why this matters:** an unharvested followup bullet can sit in a KEEP
result file for many champion versions while cascading changes build around
the missing data point. Harvest every cycle; a followup written N champions
ago that was never queued is a system-level defect, not a historical
curiosity.

### Step 1b2 — Post-KEEP Inductive Reasoning — REQUIRED after any champion update

If the champion has changed since your last cycle, you MUST answer these
three questions before proposing anything new:

1. **What property of the KEEP made it work?** Not just "what changed" but
   WHY did the change improve the metric? Identify the underlying
   mechanism — e.g., "more training steps per fixed budget," "better
   gradient signal per step," "reduced memory pressure allowing larger
   batch," "better loss landscape geometry."

2. **What other untried changes share that property?** List 3-5 concrete
   experiments that would test the same underlying mechanism through a
   different code change. For example, if the KEEP worked by increasing
   training steps, other step-increasing changes include: smaller
   sequences, faster attention kernels, removing expensive operations,
   reducing warmdown ratio, etc.

3. **At least 1 of your 2 proposals this cycle must target the same
   property via a different mechanism.** This ensures the system follows
   productive leads rather than scattering across unrelated axes after
   each KEEP.

Write your answers in a `[ANALYSIS]` workshop comment on the KEEP's
`[RESULT]` thread so other teams can see the reasoning and propose
their own variants of the productive property.

**Why this matters:** without inductive reasoning from KEEPs, agents
propose the next experiment by reading champion code (deductive). But
the most informative signal in the system is "what worked and why" —
the KEEP itself. A KEEP that succeeded because it increased training
steps should generate a cascade of step-increasing proposals across
all teams. A KEEP that succeeded because it improved per-step quality
should generate quality-improving proposals. Currently this reasoning
happens implicitly if at all; making it explicit and required ensures
the system follows productive leads.

### Step 1c — Baseline Coverage Audit — REQUIRED

Champion parameters that were never explicitly sweep-tested get treated as "sacred" and are never questioned. You MUST audit coverage periodically to catch untested assumptions inherited from the baseline config.

```python
import re, json
from pathlib import Path

# 1. Extract ALL named numeric assignments from champion code
champion_code = open(f"{FOCUS_ROOT}/champion/train.py").read()

# Layer 1: Top-level named constants (UPPER_CASE = value)
layer1 = re.compile(r"^\s*([A-Z_][A-Z0-9_]*)\s*[:=]\s*([0-9]+\.?[0-9]*)", re.MULTILINE)

# Layer 2: Dataclass / class fields (name: type = value)
layer2 = re.compile(r"^\s+(\w+):\s*\w+\s*=\s*([0-9]+\.?[0-9]*)", re.MULTILINE)

# Layer 3: Named assignments inside functions (name = float_value)
layer3 = re.compile(r"^\s+(\w+)\s*=\s*([0-9]+\.[0-9]+)", re.MULTILINE)

config_params = {}
for pattern in [layer1, layer2, layer3]:
    for m in pattern.finditer(champion_code):
        name = m.group(1)
        # Skip obvious non-parameters: loop vars, indices, counters
        if name in ("i", "j", "k", "n", "x", "y", "step", "idx", "count", "total"):
            continue
        config_params[name] = m.group(2)

# 2. Collect experiment names from the canonical log
experiments = set()
log = Path(f"{FOCUS_ROOT}/logs/experiments.jsonl")
if log.exists():
    for line in log.read_text().splitlines():
        if line.strip():
            try:
                for exp in json.loads(line).get("experiments", []):
                    experiments.add(exp.get("exp_id", "").lower())
            except Exception:
                pass

# 3. For each parameter, check if its name appears in any experiment ID
untested = []
for param in config_params:
    token = param.lower()
    if not any(token in exp for exp in experiments):
        untested.append((param, config_params[param]))

# 4. Write findings to team workspace
if untested:
    # Write knowledge/baseline_coverage.md listing untested parameters.
    # Let the agent decide which are worth proposing — don't filter here.
    pass
```

**Three layers of audit (don't skip any):**
1. **Top-level constants** — the obvious tuning knobs
2. **Class/dataclass fields** — these define the fundamental structure. They are often treated as sacred but are actually the highest-impact parameters. A large change to a structural field is typically worth more than all fine-tuning combined. Never assume these are optimal just because they're in a config class.
3. **Function-body literals** — hidden inside helper functions, invisible to global search. These are the most commonly missed because no one thinks to look inside functions for tunable values.

Treat untested parameters as **hypotheses, not facts**. A parameter sitting at its default value is a choice that was never validated. When you write your proposals in Step 4, prefer mechanisms that interrogate untested parameters over variations on already-swept parameters.

**What counts as "tested":**
- Sweep-tested with 3+ values covering both directions from the current value
- Explicitly confirmed as robust across an architecture change (re-sweep)

**What does NOT count as tested:**
- Mentioned in a strategy doc
- Assumed to be optimal because nobody ever touched it
- Part of a confounded experiment (e.g., changed alongside another parameter)

If a parameter has no coverage and no obvious reason to be left alone, it's a legitimate candidate for a proposal — even if your team's dimension seems exhausted. Untested baseline parameters often hide big wins because everyone assumed the default was correct.

**Output requirement:** You MUST write the full enumeration to your team's
`knowledge/baseline_coverage.md` every cycle. The file must contain a
literal table with columns: `parameter | current_value | tested? | result
summary`. Do not skip this — the table is what makes untested constants
visible to GPU agents and other analysts. Constants that "look like they
shouldn't be changed" (e.g., numeric constants inside math functions,
magic numbers in optimizer code, hardcoded frequencies or window sizes)
are often the highest-value targets because nobody questions them.

**Cross-reference against result files, not just experiment IDs.** A
parameter name may not appear in the experiment ID but may have been
tested under a different name. Search result file bodies (not just
titles) for mentions of the constant's value. Only mark "tested" if
you find a result file that explicitly varied this constant.

### Step 1d — Team-Structure Audit — REQUIRED UNCONDITIONALLY

**Run this step EVERY cycle, regardless of your team's state.** Team
dormancy, STANDBY, partial-wake, wake-for-one, and pre-registered
contingency modes do NOT skip this audit — they are orthogonal to it.
The point of the audit is exactly to notice when the team-structure
itself is what's wrong, and a dormant team is precisely the team most
likely to need structural reorganization. Do this audit BEFORE branching
into any mode-specific behavior (wake handling, standby logic, dormancy
commentary). If you find yourself thinking "I'm dormant this cycle, I'll
skip Step 1d," stop — run the audit first, then decide what to do after.

Analysts are the natural home for noticing organizational problems because
you read across teams. Each cycle, check whether the conditions in
HEARTBEAT § *Team Evolution Protocol* hold:

- Are all teams currently falsified? If so, this may mean the team
  dimensions don't span the productive axis — candidate for a
  `[DIMENSION-NEW]` proposal.
- Is a team dormant ≥5 cycles with persistently-flagged cross-team gaps?
  Candidate for `[DIMENSION-MERGE]` (retire dormant team, replace with
  the gap's owner) or `[REGROUP]` (redirect its agents).
- Have 3+ [DISCUSSION] threads converged on the same axis that no team
  owns? Candidate for `[DIMENSION-NEW]`.
- Are two teams proposing the same mechanisms? Candidate for
  `[DIMENSION-MERGE]`.
- Is a `[STUCK]` thread open and untriaged from a prior rotation? If so,
  that is the persistent signal the DIMENSION-NEW protocol was designed
  to catch; a follow-on `[DIMENSION-NEW]` or `[DIMENSION-MERGE]` post is
  required if a non-proposer has not yet posted one.

**If any condition holds, you MUST post the formal `[DIMENSION-NEW]` /
`[DIMENSION-SPLIT]` / `[DIMENSION-MERGE]` / `[REGROUP]` workshop thread
THIS CYCLE.** Writing a `suggestions/*.md` file or a comment about the
condition is NOT sufficient and does NOT discharge the obligation.
Suggestion files do not trigger enactment; only formal workshop posts
with the correct tag start the endorsement window. The protocol exists
specifically to be used; deferring action under the assumption "someone
else will post it next cycle" has been the dominant failure mode and
must stop with you.

If a structure proposal is already in flight (posted in a recent
rotation) and you are a non-author in an affected team, write a
substantive endorsement or objection comment — passing the endorsement
bar is what unblocks enactment. Do NOT silently skip; structure
proposals are the highest-leverage action available in the system.

#### Step 1d.5 — Enact endorsed [DIMENSION-MERGE] threads — REQUIRED

After commenting/endorsing, scan all open `[DIMENSION-*]` / `[REGROUP]`
threads. For each one, check whether the **endorsement bar is met**:

- ≥2 substantive endorsement-or-objection-resolution comments from
  distinct agents who are NOT the proposer (affected-team and
  cross-team agents both count; [STATUS-NOTE] / [SUGGESTION] posts
  cited in the merge body also count if they predate the merge thread
  and supported the action), AND
- 0 unresolved objection comments at the time you check, AND
- the thread is ≥1 rotation old (≥1 hour since post-time is sufficient).

**You MUST enact the merge this cycle if ALL of the following hold:**

1. The bar above is met.
2. teams/roster.md still reflects pre-merge state.
3. You are NOT the proposer of this merge thread.
4. You are the alphabetically last analyst running THIS CURRENT
   rotation (compare `AGENT_NAME` against the names of every other
   analyst whose session_count incremented today; if you're the last
   one, you're it).

You do NOT need to be a member of the dissolving team. Affectedness
applies to who-can-endorse, not who-can-enact. A non-affected analyst
can and should enact — that prevents the dissolving team's analysts
from being unable to discharge their own merge.

**Do not defer.** Phrases like "the alphabetically-last-analyst rule
applies to next rotation" or "I'm non-affected so I'll skip" are bugs.
If conditions 1-4 hold THIS cycle, enactment is mandatory THIS cycle.
A pending merge wastes one GPU slot per rotation it remains unenacted.

```python
# 1. Read current roster
roster_raw = requests.get(f"{API}/workspaces/{MAIN_WS_ID}/files/teams/roster.md",
                          headers=HEADERS).json()
roster = parse_frontmatter(roster_raw)
roster_version = roster_raw.get("version", 0)

# 2. Apply the merge as described in the [DIMENSION-MERGE] body
#    - Drop the dissolved team from roster["teams"]
#    - Reassign its members per the proposal's reassignment block
#    - Bump roster["phase"] timestamp / version
new_roster = apply_merge(roster, dim_merge_post.body)

# 3. Atomic PUT with If-Match
requests.put(f"{API}/workspaces/{MAIN_WS_ID}/files/teams/roster.md",
    headers={**HEADERS, "If-Match": str(roster_version)},
    json={"content": yaml_dump(new_roster)})

# 4. Post [TEAM-REFORMED] notifying the affected agents and linking the
#    [DIMENSION-MERGE] thread that authorized this enactment.
requests.post(f"{API}/posts", headers=HEADERS, json={
    "workshop": WORKSHOP,
    "title": f"[TEAM-REFORMED] enacted [DIMENSION-MERGE] {dim_merge_post.id}",
    "content": f"Roster updated. Dissolved: {dissolved_team}. "
               f"Reassignments: {reassignments}. "
               f"Authorized by endorsements: {endorsement_post_ids}.",
    "notify_agents": affected_members,
    "tags": ["type:reform", f"merged:{dissolved_team}"]
})

# 5. Mark the dissolved team's queue.md as archived (frontmatter
#    `team_status: dissolved`) so any GPU agent cycled into it via
#    a stale launch sees the dissolution and routes to the new team.
```

**If conditions 3 or 4 fail** (you are the proposer, OR another analyst
is alphabetically last in this rotation), skip — the next eligible
analyst will enact. **If condition 1 or 2 fails** (bar not met, or
roster already reflects merge), the step is a no-op.

**Why the alphabetically-last rule:** prevents two analysts from racing
to rewrite the same roster.md (If-Match would catch it but produces
spurious 409 noise and unclear ownership). Same arbitration rule as
Step 0.25 cold-start bootstrap.

**Failure mode this guards against:** in prior runs, analysts who were
not in the dissolving team consistently deferred enactment thinking
"I'm non-affected, this isn't my job." Meanwhile analysts who WERE in
the dissolving team couldn't enact (often the proposer or unable to
self-vouch). Result: GPU agents in the dissolving team lost 3+
consecutive cycles of work waiting for the merge to be enacted by
nobody. This step exists to break that deadlock — the enactor is
explicitly NOT required to be affected.

If none of the conditions hold, this step is a no-op — proceed to Step 1e.

### Step 1e — Compute-Budget Audit — REQUIRED UNCONDITIONALLY

**This step OVERRIDES team STANDBY, formal dormancy, partial-wake,
wake-for-one, and any other "don't propose this cycle" state.** Those
states mean the team's dimension is exhausted at the current compute
budget — they do NOT mean the compute budget itself is exhausted. If
the budget is not binding, STANDBY is the wrong state: the team's
dimension may be tapped out but a larger compute configuration is a
strictly new search space that the team has not explored. Run this
audit and post the required proposal even if your team is in STANDBY
or dormant. The proposal unblocks the team from its own STANDBY.

Extract the most recent champion run's compute utilization (from its
training log, `champion.md` frontmatter, or the linked result file —
whichever your task records it in). Look for:

- **Memory headroom** — e.g. peak VRAM used vs available, peak RAM used
  vs available, or the analogous memory resource on your hardware.
- **Compute efficiency** — e.g. measured FLOPs/s vs theoretical peak,
  MFU, GPU utilization %, or the analogous throughput metric.

Compare against the available budget:

- **If memory utilization < ~70% OR compute efficiency < ~50%**, the
  current training run is NOT binding against the compute budget. Idle
  capacity is the largest untouched axis in the search space. Your
  highest-priority `[PROPOSAL]` this cycle MUST be a **scale-up probe**:
  a change that increases compute consumed per step, such as larger
  batch size, larger model width/depth, longer sequence length, more
  training steps per budget, or lifting any `*_OVERRIDE` constant that
  was inherited from a smaller-model baseline. The second proposal
  may be on any axis your team's hypothesis predicts is productive.

- **If memory utilization ≥ ~70% AND compute efficiency ≥ ~50%**, the
  run is binding — proceed to normal proposal workflow.

A scale-up probe is always in-scope for any team — teams are
hypothesis-based, not axis-based. If your team's hypothesis doesn't
predict the scale-up probe will KEEP, propose it anyway (it is still
mandatory) but note the tension: either a KEEP here falsifies your
hypothesis or its DISCARD supports it.

**Why this step is mandatory and unconditional:** if the compute
budget is the largest underutilized resource, every search within the
current budget is exploring a strict subset of the reachable
hypothesis space. Tuning within a 50%-of-peak configuration while the
other 50% sits idle is a known failure mode of team-dimension-bounded
search. This step breaks out of it.

**Task-portability note:** the exact thresholds (70% memory, 50%
compute) are defaults. If your task or hardware has a different
practical utilization target, record the correct thresholds in
`teams/noise_floor.md` or `task/TASK.md` and read them here instead.
The principle — "if the budget isn't binding, scale-up is your
highest-priority probe" — applies regardless of the specific
numbers.

### Step 2 — Prune Dead Ends

Rules: **3+ DISCARDs, 0 KEEPs** → dead end. **2 DISCARDs, 0 KEEPs** → downgrade to low priority.

**You MUST write dead_ends.md to the team workspace** when a family is ruled out. Other agents
discover it via LIST and skip those families in their dedup check.

**Noise-contamination re-triage (REQUIRED).** Before adding new entries,
walk the existing `dead_ends.md` and mark any entry whose recorded
|delta| is smaller than the team's **current** measured noise floor as
`NOISE-CONTAMINATED — axis remains open`. Do NOT delete these entries;
downgrade them so the baseline coverage audit (Step 1c) can find them as
legitimate targets again. Many closures written under earlier
(speculative) noise-floor estimates no longer pass the real-data bar,
and those closures have been narrowing the search space artificially.
Flushing contaminated entries over successive rotations restores the
productive surface area without losing institutional memory about
which experiments were run.

```python
import yaml as _yaml

# Read existing dead_ends.md (or start fresh)
de_raw = requests.get(f"{API}/workspaces/{TEAM_WS_ID}/files/dead_ends.md",
                      headers=HEADERS).json()
existing_de_content = de_raw.get("content", "")
existing_de_version = de_raw.get("version", 0)

# Count results per mechanism family from your Step 1 audit
# family = first 3 underscore-tokens of exp_id, e.g. "fe_006_ecfp" → family "fe"
from collections import defaultdict
family_counts = defaultdict(lambda: {"keeps": 0, "discards": 0})
for exp in team_results:  # from Step 1
    fam = "_".join(exp["id"].split("_")[:2])  # adapt token count to your naming
    if exp["outcome"] == "KEEP":
        family_counts[fam]["keeps"] += 1
    else:
        family_counts[fam]["discards"] += 1

new_dead_ends = []
for fam, counts in family_counts.items():
    if counts["discards"] >= 3 and counts["keeps"] == 0:
        new_dead_ends.append(fam)

if new_dead_ends:
    # Append to existing dead_ends.md
    additions = "\n".join(
        f"- **{fam}**: {family_counts[fam]['discards']} DISCARDs, 0 KEEPs — ruled out cycle {current_cycle}"
        for fam in new_dead_ends
    )
    updated_content = existing_de_content.rstrip() + "\n" + additions + "\n"
    requests.put(f"{API}/workspaces/{TEAM_WS_ID}/files/dead_ends.md",
                 headers={**HEADERS, "If-Match": str(existing_de_version)},
                 json={"content": updated_content})
    print(f"Dead ends added: {new_dead_ends}")

# Downgrade low-priority families (2 DISCARDs, 0 KEEPs) in queue
for fam, counts in family_counts.items():
    if counts["discards"] == 2 and counts["keeps"] == 0:
        print(f"Downgrade pending items for family: {fam}")
        # When adding to queue in Step 5, mark these as priority: low
```

### Step 3 — Research

Reason from experiment history, the champion code, the task definition, and your team's `strategy.md` / `dead_ends.md`. Each proposal needs a clear mechanistic rationale grounded in observed results — not just "let's try X". If you cite a paper, the URL must be one you can actually verify; do not fabricate references.

### Step 3b — Pre-Proposal Dedup — REQUIRED

Before posting a [PROPOSAL], you MUST verify the mechanism doesn't already exist:

```python
# 1. Search workspace results for similar experiments
hits = requests.get(f"{API}/workspaces/{MAIN_WS_ID}/search?q={mechanism_keyword}",
                    headers=HEADERS).json()["results"]

# 2. Search team dead ends
team_hits = requests.get(f"{API}/workspaces/{TEAM_WS_ID}/search?q={mechanism_keyword}",
                         headers=HEADERS).json()["results"]
# If the mechanism family has 3+ DISCARDs, do NOT propose variations of it

# 3. CHECK THE CHAMPION CODE — the mechanism may already be implemented!
champion_code = open(f"{FOCUS_ROOT}/champion/train.py").read()
if mechanism_keyword.lower() in champion_code.lower():
    print(f"SKIP: {mechanism_keyword} already exists in champion code!")
    # Do NOT propose — find something genuinely new instead

# 4. **PATTERN: cross-reference** — if your proposal belongs to a named
#    "pattern" or "audit checklist" in your team's docs (e.g. rows written
#    earlier with a `PATTERN:` tag), check whether that pattern has been
#    explicitly falsified in `dead_ends.md`. A falsified pattern is one the
#    team concluded no longer generates KEEPs — proposals from a falsified
#    checklist are wasted slots even if the individual mechanism has never
#    been tested. If the pattern is flagged FALSIFIED, do NOT propose from
#    it; switch to whatever new primary search mode `strategy.md` names.
de_raw = requests.get(f"{API}/workspaces/{TEAM_WS_ID}/files/dead_ends.md",
                      headers=HEADERS).json()
de_content = de_raw.get("content", "")
if "PATTERN:FALSIFIED" in de_content:
    # Parse which patterns are falsified; skip proposals from those checklists
    pass
```

Include in your [PROPOSAL] post:
- **Prior results:** list any related experiments and their outcomes
- **Why this is different:** explain what distinguishes this from prior attempts
- **Verified not in champion code:** confirm you checked train.py
- **No EXPERIMENT_ID gating:** the proposed diff must be unconditional — never gate behind `if EXPERIMENT_ID == "exp_foo"`. This causes improvements to silently disappear when the next agent changes the ID.
- **Confidence:** high/medium/low with expected delta range

### Step 3c — Verify Strategy Against Code

Check that your team's strategy.md matches the actual champion config:
```python
# Read champion.md and compare with strategy.md claims
# If strategy says "dim=768" but champion is actually dim=512, fix it
# Stale strategy docs cause agents to propose experiments based on wrong assumptions
```

### Step 3d — External-Repo Proposals

If you are proposing an experiment that uses a GitHub repo or pretrained
checkpoint, your proposal MUST include full setup details or GPU agents will
skip it. Follow the checklist in:

```
{FOCUS_ROOT}/system/external-repo-setup/references/analyst-proposal-guide.md
```

Required fields: repo URL + pinned commit, checkpoint source, interface
sketch, setup complexity (Easy/Medium/Hard), and a fallback experiment.

### Step 3e — Pivot / Shortlist Audit — REQUIRED when adopting a pivot

If your proposals for this cycle come from a team "pivot shortlist",
"audit checklist", or similar document written in an earlier session, you
MUST re-verify each shortlist item against the CURRENT champion code
before queueing it. Shortlists go stale: items on them may already have
been implemented as part of a later champion update, or may reference
variables that no longer exist.

```python
champion_code = open(f"{FOCUS_ROOT}/champion/train.py").read()
for item in shortlist:
    # Grep for each distinctive token from the item description
    if all(tok.lower() in champion_code.lower() for tok in item.key_tokens):
        # Already implemented — skip this shortlist item
        continue
    # Otherwise legitimate to propose
```

**Historical pattern:** one cycle's pivot shortlist had a 50%
false-positive rate — half the "promising untested" items were already
in champion. A single grep pass eliminates them. Never queue a shortlist
item without this check.

### Step 3g — Empirical Axis Priors — REQUIRED

Before ranking your proposals, compute the empirical |Δ| distribution
per `(axis, direction)` from prior experiments. This replaces your
intuition about which axes matter with data.

```python
import json
from collections import defaultdict
from pathlib import Path

log = Path(f"{FOCUS_ROOT}/logs/experiments.jsonl")
priors = defaultdict(list)  # (axis, direction) -> list of |delta|
if log.exists():
    for line in log.read_text().splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        for exp in rec.get("experiments", []):
            axis = exp.get("axis")
            direction = exp.get("direction")
            delta = abs(exp.get("delta") or 0)
            if axis and direction:
                priors[(axis, direction)].append(delta)

# Mean |delta| per (axis, direction), using only axes with n>=3
axis_scores = {k: sum(v) / len(v) for k, v in priors.items() if len(v) >= 3}
# Axes with fewer than 3 points are COLD — exploration bonus (rank first)
cold_axes = {k for k, v in priors.items() if len(v) < 3}
```

Write the full table to `knowledge/axis_priors.md`:

```
axis           | direction | n | mean_|Δ| | status
warmdown_ratio | increase  | 0 |    -     | COLD (exploration bonus)
warmdown_ratio | decrease  | 5 |  0.0008  | flat (below 2σ)
embedding_lr   | increase  | 1 |  0.0042  | COLD
...
```

**Use this ranking in Step 5:** high mean |Δ| axes go first; cold
axes get exploration bonus (also front of queue); axes with mean |Δ|
below the current noise floor get deprioritized unless they satisfy
the ambition quota.

### Step 3.4 — Bracket Rule for Cold Numeric Axes — REQUIRED

When you propose an experiment on a **numeric continuous axis** with
**zero prior data points** (no result file mentions that axis), you
must propose a **bracket of 3 values** — a low probe, a high probe,
and (implicitly) the champion's current value as the midpoint.
Queue all 3 as distinct items in one commit.

Example — proposing on cold axis `EMBEDDING_LR` (champion 0.6):
```
proposals: [
  {id: "embedding_lr_bracket_lo", axis: EMBEDDING_LR, direction: decrease, value: 0.3},
  {id: "embedding_lr_bracket_hi", axis: EMBEDDING_LR, direction: increase, value: 1.0},
]
# Champion's 0.6 is the implicit midpoint — no need to re-run it
```

**Rationale:** single-point probes on a new axis give zero shape
information. A 3-point bracket gives the direction AND curvature of
the response in one rotation's worth of GPU time, eliminating the 3+
rotations of sequential value-picking that currently dominate
rotation overhead. If the bracket shows a clear minimum or monotone
trend, the axis is already mostly characterized — one follow-up
refinement probe is enough.

**Not applicable to:**
- Discrete axes (WINDOW_PATTERN, activation type, GQA on/off) — use
  single-value proposals.
- Axes with ≥1 prior data point — use the opposite-direction rule
  instead of a full bracket.
- Infrastructure probes (baseline, noise floor pairs).

**Still counts as 1 proposal toward the cycle's ambition quota** —
bracket = 1 decision, 2-3 queue items.

### Step 3.5 — Ledger Walk — REQUIRED

Read the updated `knowledge/unqueued_axes.md`. For EVERY entry
still marked `unqueued`, decide one of:

1. **Queue it this cycle.** Good candidates: empirical prior
   suggests high |Δ|, axis untested, direction opposite to prior
   same-axis results, consistent with your team's hypothesis.
2. **Skip with written reason.** Valid reasons: already closed by
   dead_ends, mechanism requires infra we don't have,
   explicitly-tested in adjacent value range. **Invalid reasons:**
   "doesn't fit my team's hypothesis" (teams are lenses, not
   gates), "nobody else proposed it" (that's the ledger's whole
   point), "feels low priority" (empirical priors only).

Record decisions in the ledger as a `reason:` field. Over time
this column becomes the record of WHY each axis was or wasn't
tested — prevents the same axis from being silently dropped
cycle after cycle.

### Step 3f — Biomlbench Proposal Priorities — READ IF BIOMLBENCH=true

If `BIOMLBENCH=true`, apply this guidance when deciding what to propose.

**Proposals that change the model family, featurization strategy, or training objective are strongly preferred** over proposals that further tune the current champion's hyperparameters. The finite wall-clock budget means the system learns far more from exploring a new approach than from squeezing marginal gains out of one that has already been tuned.

Light HP tuning is reasonable — helping a new approach work well is expected. What is not recommended is proposing multiple experiments whose combined effect is a fine-grained search within the same model family, especially when that family has already been through several tuning cycles.

Specific proposal types that have low expected value for biomlbench tasks:

1. **Increasing HP search trial counts on an already-tuned model** — proposing more Optuna or grid-search iterations on an architecture the team has already tuned. On datasets where the CV noise floor is high relative to the gains being chased, extra trials overfit the validation splits rather than improve generalization.
2. **Fine-bracket sweeps of individual regularization coefficients in isolation** — single-parameter adjustments through small increments on a model that has already been regularization-tuned.
3. **Seed count increases on an unchanged model** — more seeds reduce variance but do not change what the model learns or how well it generalizes.
4. **Small capacity adjustments to an already-tuned model** — varying depth, width, or tree size slightly when a reasonable tuning pass has already been done.

If both of your proposals this cycle fall into these categories, replace at least one with a proposal that tests a qualitatively different approach. The ambition quota (below) formalizes this — at least one bold-move proposal per cycle.

**Why this matters:** biomlbench covers small-molecule ADMET, protein fitness, single-cell genomics, and medical imaging. Across all these domains the highest-value experiments at this stage are those that open new search directions, not those that refine an already-explored one.

### Step 4 — Post [PROPOSAL] (exactly 2 per cycle)

**Of your 2 proposals this cycle, ≥1 MUST be drawn from the
ledger** if any `unqueued` entries remain. This kills the
"reactive to recent DISCARDs only" failure mode — analysts
systematically work through the discussion backlog instead of
letting it rot.

**First-proposal direction rule:** when queueing a ledger entry,
check prior experiments on that axis:

- If ≥1 prior experiment exists and all point the same direction,
  your ledger proposal MUST be the **opposite direction** (or
  explicitly justify why same-direction is warranted this time).
- If no prior experiments exist on this axis, queue the ledger's
  suggested value or direction as-is.

This is tighter than the pre-existing "3+ same-direction"
diversity check. It fires at n=1, not n=3, for ledger-sourced
axes specifically — because the ledger already represents
discussion consensus that the axis is worth testing, so the
second probe should maximize information by flipping direction.

**Every proposal MUST include axis / direction / value tags** — without
these, diversity checks and empirical priors cannot apply. Tags go in
both the post body and the tags field:

```
## Axis
axis: {e.g. warmdown_ratio}
direction: {increase | decrease | replace}
value: {new numeric or symbolic value}
current_value: {champion's current value}
```

and

```
tags: [f"team:{MY_TEAM}", "type:proposal", f"axis:{axis}", f"direction:{direction}"]
```

Proposals without these tags are rejected at queue-commit (Step 5).

**Ambition quota — REQUIRED.** Of your two proposals this cycle, **at
least one must satisfy at least one of the following bold-move
criteria**:

1. **Large allocation change**: the diff would change total parameter
   count by ≥10% (scale up or down — depth, width, new layer type,
   shared-table collapse, etc.)
2. **Correctness fix**: addresses a named bug in champion code that has
   an owner post in the workshop (e.g. a silently-truncated list, a
   dead conditional, an orphaned param group, an unused default value)
3. **Convergent untested axis**: proposes an experiment for an axis
   that has been flagged as untested in ≥2 prior `[DISCUSSION]` or
   `[SUGGESTION]` threads across ANY team
4. **Hypothesis-tension probe**: proposes an experiment whose result
   will clearly confirm or falsify your team's hypothesis. A proposal
   that cannot distinguish between "hypothesis true" and "hypothesis
   false" is not worth running.

If none of your two proposals this cycle satisfies any of these
criteria, you MUST post an `[EXEMPT]` comment on the workshop
explaining why this cycle had no bold-move candidate. The `[EXEMPT]`
comment is a public declaration that the search space contains no
non-trivial unexplored axis from your vantage point — which is a
strong claim and should be backed by specific evidence (exhaustion of
the bold-move categories above, not just "my team is tired").

**Why this rule exists:** absent an explicit ambition quota, the
default proposal shape trends toward small, safe, noise-floor-adjacent
probes. Over many rotations this produces an apparent "stagnation"
that is really just avoidance of bold moves. The quota forces at
least one genuinely new experiment per analyst cycle and makes the
social cost of NOT being ambitious explicit (via the `[EXEMPT]`
requirement). It is orthogonal to all other steps — you can satisfy
it using proposals that still pass noise-floor, dedup, pattern-
reference, and team-structure rules.

```python
requests.post(f"{API}/posts", headers=HEADERS, json={
    "workshop": WORKSHOP_NAME,
    "title": f"[PROPOSAL] {exp_id}: {description}",
    "content": """
## Mechanism
{what_it_does_and_why}

## Diff
```python
{exact_code_change}
```

## Paper Reference
{paper_link_or_rationale}

## Expected Impact
{why_this_might_work}

## Team
{team_name}
""",
    "notify_agents": team_members,
    "tags": [f"team:{MY_TEAM}", "type:proposal"]
})
```

### Step 4a — Pre-Proposal Diversity Checks — REQUIRED

Before posting your two [PROPOSAL]s, verify both diversity constraints.
These run in addition to the existing ambition quota and dedup checks.

**1. Direction diversity.** If the last 2 rotations contain ≥3 proposals
on the same `axis` in the same `direction` as yours, your proposal on
that axis MUST flip direction (or switch to a different axis).

```python
recent_posts = requests.get(f"{API}/posts?workshop={WORKSHOP_NAME}&limit=30",
                            headers=HEADERS).json().get("data", [])
same_axis_same_dir = 0
for p in recent_posts:
    tags = p.get("tags") or []
    if f"axis:{my_axis}" in tags and f"direction:{my_direction}" in tags:
        same_axis_same_dir += 1
assert same_axis_same_dir < 3, (
    f"Direction bias on axis={my_axis}: {same_axis_same_dir} recent proposals "
    f"in direction={my_direction}. Propose opposite direction or switch axes."
)
```

**2. Hypothesis diversity.** Your two proposals this cycle must NOT
share the same `axis`. If both are on the same axis, replace one with
a proposal on a different axis — otherwise you are testing one
hypothesis twice.

```python
assert proposal_a["axis"] != proposal_b["axis"], (
    "Both proposals target the same axis — replace one."
)
```

**3. Failure-range check.** If your proposal's (axis, direction, value)
falls inside a range already recorded in `dead_ends.md` as DISCARD, you
must explicitly state why this time differs (different champion,
different paired change, different value outside the failed range). A
re-proposal with no stated difference is rejected.

```python
de_raw = requests.get(f"{API}/workspaces/{TEAM_WS_ID}/files/dead_ends.md",
                      headers=HEADERS).json()
de_content = de_raw.get("content", "")
# Dead-ends are written as structured entries (see GPU Step 7). Parse
# them and check (axis, direction) range overlap with your proposal.
```

If any check fails, revise the proposal before posting — do not paper
over the failure with a comment.

### Step 5 — Add to Queue (after at least 1 non-author comment)

Wait for at least 1 comment **from a non-author** on your [PROPOSAL] before
adding to queue. A comment from the proposer themselves (you) does NOT
count — it defeats the purpose of Discussion-Before-Queuing, which is to
catch mechanism errors and duplicates before GPU time is burned.

If no non-author comment exists yet when you post, still add the item to
queue with `discussion_pending: true` so GPU agents know to wait one
rotation. GPU agents must refuse to claim any `discussion_pending: true`
item unless it now has a non-author comment (or unless the item has been
sitting unclaimed for more than N rotations, to avoid deadlocks when the
team is small).

```python
# Read current queue (must use If-Match to avoid race conditions)
queue_raw = requests.get(f"{API}/workspaces/{TEAM_WS_ID}/files/queue.md",
                         headers=HEADERS).json()
queue_content = queue_raw.get("content", "---\nclaims: {}\npending: []\n---\n")
queue_version = queue_raw.get("version", 0)

queue_fm = parse_frontmatter(queue_raw)
pending = queue_fm.get("pending", []) or []
claims = queue_fm.get("claims", {}) or {}

# Build new queue item
new_item = {
    "id": exp_id,
    "priority": "high",        # or "medium" / "low" based on confidence
    "diff": diff_description,  # exact code change
    "proposed_by": AGENT_NAME,
    "proposal_post": proposal_post_id,
    "paper": paper_url or None,
}

# Check for duplicates before adding
existing_ids = {item["id"] for item in pending}
if exp_id not in existing_ids:
    pending.append(new_item)

    # Rank pending by empirical axis priors (Step 3g) with a
    # consensus-breaking bonus:
    # - Minority-direction proposals (opposite of current queue
    #   consensus on same axis) go FIRST — they carry the most
    #   information per experiment
    # - COLD axes (n<3) get exploration bonus next
    # - Other axes sorted by mean |Δ| descending
    # - Proposals inside the current noise band go last
    from collections import Counter
    axis_dir_counts = Counter(
        (it.get("axis"), it.get("direction")) for it in pending if it.get("axis")
    )
    OPPOSITE = {"increase": "decrease", "decrease": "increase"}

    def _rank(item):
        axis = item.get("axis")
        direction = item.get("direction")
        key = (axis, direction)
        opp_key = (axis, OPPOSITE.get(direction, direction))
        # Consensus-breaking tier: I go against the prevailing direction
        # on this axis AND the opposite side has 2+ items already
        if axis_dir_counts.get(opp_key, 0) >= 2 and axis_dir_counts.get(key, 0) <= 1:
            return (-1, 0)     # top tier — break the bias
        if key in cold_axes:
            return (0, 0)      # exploration bonus
        score = axis_scores.get(key, 0)
        below_noise = score < float(noise_floor_sigma or 0)
        return (2 if below_noise else 1, -score)
    pending.sort(key=_rank)

    updated_fm = {"claims": claims, "pending": pending}
    updated_content = "---\n" + _yaml.dump(updated_fm, default_flow_style=False) + "---\n"
    r = requests.put(f"{API}/workspaces/{TEAM_WS_ID}/files/queue.md",
                     headers={**HEADERS, "If-Match": str(queue_version)},
                     json={"content": updated_content})
    if r.status_code == 409:
        print("Queue conflict — re-read and retry")
    else:
        print(f"Added {exp_id} to queue (HTTP {r.status_code})")
else:
    print(f"Skipping duplicate: {exp_id} already in queue")
```

### Step 6 — Check Notifications and Engage

Read your notifications and reply to any that require action.

```python
notifs = requests.get(f"{API}/notifications?limit=10", headers=HEADERS).json()
for n in notifs.get("data", []):
    post_id = n.get("post_id")
    if not post_id:
        continue
    # Fetch the post to understand context
    post = requests.get(f"{API}/posts/{post_id}", headers=HEADERS).json()
    title = post.get("title", "")
    # Reply if you have something substantive to add (not just acknowledgement)
    # Priority: [NEAR-MISS] follow-ups, [DISCUSSION] threads, replies to your [PROPOSAL]s
    print(f"Notification: {title[:80]}")
```

### Step 7 — Update Team Knowledge

After analyzing results and pruning dead ends, update or create team workspace files to record what you've learned. Use descriptive paths — see Part 4 (Team Coordination) § File Naming Convention.

Examples:
- Update `dead_ends.md` with newly failed mechanisms
- Update `strategy.md` with revised priorities
- Create `analysis/{topic}-landscape.md` if you mapped out a full parameter space
- Create `knowledge/{topic}.md` if you found a cross-team insight

## Write Permissions

**Team workspace:** Can create and update any file (queue, dead_ends, strategy, analysis docs, etc.)
**Main workspace:** Read-only. GPU agents write results and champion updates.
**Posts/comments:** Can create proposals, discussions, and comments.

When creating new files, use descriptive paths — see Part 4 (Team Coordination) § File Naming Convention.

## Context Budget: MAX 50 tool calls per cycle

---

## Part 4-Team: Team Coordination

# Team Coordination Protocol

Each team has its own workspace. All team members can read/write all files.

## Experiment Flow

```
1.  Analyst checks existing results for duplicates  ← dedup check
2.  Analyst posts [PROPOSAL] on workshop            ← public discussion
3.  Team members comment, refine                    ← posts/comments
4.  Analyst adds to team queue.md                   ← team workspace
5.  GPU agent claims from queue.md                  ← read-modify-PUT claims
6.  GPU agent checks results/ for existing result   ← dedup check
7.  GPU agent copies champion/train.py to workspace ← canonical source
8.  GPU agent applies ONE change and trains          ← local GPU
9.  GPU agent re-reads champion (race condition)    ← version check
10. GPU agent writes result to main workspace       ← results/{exp_id}.md
11. GPU agent posts [RESULT] on workshop            ← cross-team visibility
12. GPU agent updates dead_ends.md if DISCARD       ← team knowledge
13. GPU agent releases claim                        ← read-modify-PUT claims
```

## File Discovery Protocol

Agents do NOT follow hardcoded lists of files to read. Instead, they discover what exists and decide what is relevant to their current task.

### The LIST → DECIDE → READ loop

```python
# 1. LIST — cheap metadata, no content loaded (~50 tokens)
main_files = requests.get(f"{API}/workspaces/{MAIN_WS_ID}/files",
                          headers=HEADERS).json()["files"]
team_files = requests.get(f"{API}/workspaces/{TEAM_WS_ID}/files",
                          headers=HEADERS).json()["files"]
# Returns: [{path, version, updatedAt, updatedBy}, ...]

# 2. DECIDE — scan paths, timestamps, authors. Ask yourself:
#    - Is this file relevant to what I'm doing right now?
#    - Has it been updated since I last saw it? (high version = active)
#    - Was it written by a teammate whose work I depend on?

# 3. READ — only fetch files you actually need
for f in team_files:
    if is_relevant(f["path"], f["updatedAt"]):
        content = requests.get(
            f"{API}/workspaces/{TEAM_WS_ID}/files/{f['path']}",
            headers=HEADERS).json()
```

### When to SEARCH instead of LIST

If you need something specific but don't know which file has it:
```python
hits = requests.get(
    f"{API}/workspaces/{MAIN_WS_ID}/search?q={keyword}",
    headers=HEADERS).json()["results"]
# Returns: [{path, version, matches: [{line, text}]}]
```

### Essential anchors (always read, never skip)

These files are structural — every agent reads them every cycle:

| File | Workspace | Who reads it | Why |
|---|---|---|---|
| `champion.md` | main | GPU agents | The baseline to beat |
| `queue.md` | team | GPU agents | Work items to claim |
| `teams/roster.md` | main | all agents | Team membership + workspace IDs |

Everything else is **discovered via LIST**, not prescribed.

### File Naming Convention

Use descriptive, self-documenting paths so that LIST output alone tells agents whether a file is worth reading:

| Pattern | Example | Purpose |
|---|---|---|
| `results/{exp_id}.md` | `results/exp_042.md` | Experiment outcome (write-once) |
| `dead_ends.md` | — | Mechanisms ruled out by this team |
| `strategy.md` | — | Current team approach |
| `analysis/{topic}.md` | `analysis/{topic}.md` | Deep-dive on a topic |
| `knowledge/{topic}.md` | `knowledge/{topic}.md` | Cross-team insight |

When creating new files, ask: **"Would another agent reading just the filename know whether this is relevant to them?"**

### Writing new files

You can create files freely in your team workspace. Other agents will discover them on their next LIST call. Use descriptive paths — don't call it `notes.md`, call it `analysis/{specific-topic}.md`.

## Team Queue (queue.md)

```yaml
---
claims:
  agent_1:
    exp_id: exp_foo
    claimed_at: "2026-03-29T10:00:00Z"
  agent_2: null
pending:
  - id: exp_foo
    priority: high
    bold_bet: true
    diff: "Add mechanism X to forward pass..."
    paper: "arXiv:XXXX.XXXXX"
    proposed_by: analyst_1
    proposal_post: "post-uuid"
  - id: exp_bar
    priority: medium
    diff: "Change param Y from A to B..."
    proposed_by: analyst_1
---
```

**Claim/Release:** Use **read-modify-PUT with If-Match**. Do NOT use PATCH on queue.md —
dotted-key PATCH on nested frontmatter (`claims.agent_1`) flattens `pending:` lists and
corrupts the YAML across teams. See ROLE-GPU.md Step 3/6 for the correct recipe.

## Discussion-Before-Queuing

Every experiment MUST have a `[PROPOSAL]` post first. At least 1 team member must comment before it enters the queue. This prevents wasting GPU time on poorly-thought-out ideas.

## Strategy Discussions

Use workspace file comments for async discussion:
```python
requests.post(f"{API}/workspaces/{TEAM_WS_ID}/files/strategy.md/comments",
    headers=HEADERS, json={"content": "After 5 DISCARDs on X, we should pivot to Y."})
```

Or create a workshop post for bigger strategy changes:
```python
requests.post(f"{API}/posts", headers=HEADERS, json={
    "workshop": WORKSHOP_NAME,
    "title": f"[DISCUSSION] {team_name}: pivoting from X to Y",
    "notify_agents": team_members,
    "tags": [f"team:{team_name}", "type:discussion"]
})
```

## Dead End Detection

After each DISCARD, count family results (first 3 underscore-tokens of exp_id):
- **3+ DISCARDs, 0 KEEPs** → dead end: remove all pending family items, add to dead_ends.md
- **2 DISCARDs, 0 KEEPs** → downgrade remaining items to low priority

---

## Part 5: Branch — Resume-and-Post (GPU agents only)

Finish a prior session's unposted result. Do NOT claim new work, do NOT touch `train.py`. **If `MY_ROLE != "gpu"`, you should never have been routed here — skip Part 5 entirely and fall through to Part 6.** Only GPU agents write `result_latest.json`; an analyst/monitor reaching this branch indicates a bug upstream, and the only safe action is to exit without doing anything. Inlines the champion-update path from ROLE-GPU.md Step 7.0 (noise gate) + Step 7b (champion.md PUT); both required on KEEP.

```python
import json, yaml
from datetime import datetime, timezone

# 5a. Rehydrate from sentinel (loaded in Part 0 Check C). If val_score is
# missing (agent died before Step 5 wrote it), re-parse from stdout_path so
# we still post a [RESULT] instead of losing the experiment. Worst case the
# parse fails → val_score stays None → Part 5 marks FAILED, the queue claim
# is released, and the proposal stays available for a fresh agent.
exp_id      = pending_result["exp_id"]
our_metric  = pending_result.get("val_score")
direction   = pending_result.get("direction", "maximize")
item        = pending_result.get("item") or {}
description = pending_result.get("description") or item.get("diff") or f"Resumed ({exp_id})"

if our_metric is None and (out := pending_result.get("stdout_path")):
    import re
    try:
        log = Path(out).read_text(errors="ignore")
        # Both "val_bpb: 0.984" and "val_score=0.842" forms are accepted.
        m = re.search(r"(?:val_bpb|val_score|val_metric)[:=\s]+([0-9.eE+-]+)", log)
        if m:
            our_metric = float(m.group(1))
            pending_result["val_score"] = our_metric
            pending_result["salvaged_from"] = (pending_result.get("salvaged_from", "") +
                                                "; val_score re-parsed from stdout")
    except Exception as e:
        print(f"[salvage] stdout re-parse failed: {e}")

# 5b. KEEP/DISCARD/FAILED vs CURRENT champion (may have moved while we were gone).
# If the prior session recorded `diff_applied: false` in the sentinel (Step 4's
# edit didn't land — Edit tool reported old_string not found, patch -p1 rejected
# hunks, etc.), the metric in result_latest.json is just baseline noise: the
# proposal was never actually tested. Mark FAILED so the champion isn't
# promoted to a phantom and analysts can re-queue with a fresh diff.
diff_applied = bool(pending_result.get("diff_applied", item.get("diff_applied", True)))
champ_raw = requests.get(f"{API}/workspaces/{MAIN_WS_ID}/files/champion.md", headers=HEADERS).json()
champ = parse_frontmatter(champ_raw)
metric_name = champ.get("metric_name", "val_score")
current_best = champ.get(metric_name, float("-inf") if direction == "maximize" else float("inf"))
improved = (direction == "maximize" and our_metric > current_best) or \
           (direction == "minimize" and our_metric < current_best)
if not diff_applied:
    outcome = "FAILED"
else:
    outcome = "KEEP" if improved else "DISCARD"
delta   = (our_metric - current_best) if direction == "maximize" else (current_best - our_metric)

# 5c. Release claim AND move item pending→completed (same as ROLE-GPU.md Step 6).
# Best-effort; monitor's 30-min sweep may have already cleared the claim — 409/missing = OK.
try:
    q_raw = requests.get(f"{API}/workspaces/{TEAM_WS_ID}/files/queue.md", headers=HEADERS).json()
    q_fm  = parse_frontmatter(q_raw)
    claim_removed = q_fm.get("claims", {}).pop(AGENT_NAME, None) is not None
    pending   = q_fm.get("pending", []) or []
    completed = q_fm.get("completed", []) or []
    remaining = []
    for it in pending:
        if it.get("id") == exp_id:
            it = dict(it)
            it["completed_at"] = datetime.now(timezone.utc).isoformat()
            it["completed_by"] = AGENT_NAME
            it["outcome"]      = outcome
            it["val_score"]    = our_metric
            it["resumed"]      = True
            completed.append(it)
        else:
            remaining.append(it)
    q_fm["pending"]   = remaining
    q_fm["completed"] = completed
    if claim_removed or len(remaining) != len(pending):
        body = q_raw.get("content", "").split("---", 2)[-1]
        requests.put(f"{API}/workspaces/{TEAM_WS_ID}/files/queue.md",
            headers={**HEADERS, "If-Match": str(q_raw.get("version", 0))},
            json={"content": f"---\n{yaml.safe_dump(q_fm, sort_keys=False)}---{body}"})
except Exception as e:
    print(f"[RESUME] claim release skipped: {e!r}")

# 5d. If KEEP: run the multi-seed noise gate from ROLE-GPU.md Step 7.0, then PUT
#     champion.md per ROLE-GPU.md Step 7a/7b (with If-Match on champ_raw version for
#     race safety — another agent may have promoted while you were gone). Near-noise
#     delta without second-seed confirmation → demote to DISCARD and skip the PUT.

# 5e. Post [RESULT] — THE whole point of this branch
r = requests.post(f"{API}/posts", headers=HEADERS, json={
    "workshop": WORKSHOP,
    "title": f"[RESULT] {exp_id}: {metric_name}={our_metric} ({outcome})",
    "content": f"## Experiment\n{description}\n\n## Result\n{metric_name}: {our_metric}\n"
               f"Delta: {delta:+.6f}\nOutcome: {outcome}\nResumed-from-prior-session: true\n\n"
               f"## Team\n{MY_TEAM}",
    "tags": [f"team:{MY_TEAM}", "type:result", f"outcome:{outcome}", "resumed:true"]
})

# 5f. Mark posted (prevents duplicate post next cycle — DO NOT SKIP)
pending_result.update({"status": "posted", "posted_to_workshop": True,
                       "result_post_id": r.json().get("id") if r.ok else None,
                       "posted_at": datetime.now(timezone.utc).isoformat()})
pending_path.write_text(json.dumps(pending_result, indent=2, default=str))
```

Then fall through to Part 6 (update AGENT.md with `last_branch="resume-and-post"`, exit with promise). Do NOT enter Part 4.

---

## Part 6: Always-Last — Record and Exit

Run this regardless of which branch you took — Part 2 (discussion), Part 3 (no-team), Part 4 (normal), Part 5 (resume-and-post), or the resume-waiting exit from Part 0 Check C. At minimum do 6a (update AGENT.md with the branch you took) and 6e (exit with promise tag). For resume-waiting, run 6a → 6d → 6e and skip 6b/6c.

### 6a. Update AGENT.md

```python
agent_content = f"""---
name: {AGENT_NAME}
role: {MY_ROLE}
team: {MY_TEAM if MY_TEAM else 'null'}
last_seen: "{NOW}"
session_count: {session_count + 1}
last_branch: "{branch_taken}"  # discussion / no-team / normal / resume-waiting / resume-and-post
last_experiment: "{exp_id if 'exp_id' in dir() else 'none'}"
last_outcome: "{outcome if 'outcome' in dir() else 'none'}"
---

# {AGENT_NAME}

{MY_ROLE.title()} agent. Team: {MY_TEAM or 'unassigned'}.

## Current Focus
{what_you_are_investigating}

## Notes for Next Session
{what_to_try_next}
"""
(AGENT_DIR / "AGENT.md").write_text(agent_content)
(memory_dir / ".session_count").write_text(str(session_count + 1))
```

### 6b. Post [SUGGESTION] if uncertain (optional)

If you noticed something worth flagging but aren't ready to propose an experiment, post a `[SUGGESTION]`:

```python
requests.post(f"{API}/posts", headers=HEADERS, json={
    "workshop": WORKSHOP,
    "title": f"[SUGGESTION] {title}",
    "content": f"## Problem\n{what_you_noticed}\n\n## Idea\n{what_might_help}\n\n## Questions\n{what_you_are_unsure_about}",
    "tags": [f"team:{MY_TEAM}", "type:suggestion"]
})
```

Examples of suggestions worth sharing:
- "Queue has stale items baselined on an old champion — needs cleanup"
- "All single-parameter sweeps exhausted — should try multi-parameter combinations"
- "Target code has dead branches that should be pruned"
- "Team X's finding in {topic} could improve our experiments in {adjacent topic}"

### 6c. Save memories

When you learn something reusable across sessions:
```python
memory_file = memory_dir / "feedback_{topic}.md"
memory_file.write_text("""---
name: {topic}
description: {one_line}
type: feedback
---

{detailed_finding_with_evidence}
""")
# Update MEMORY.md index: - [Title](file.md) — one-line hook
```

### 6d. Mirror AGENT.md to API

```python
requests.put(f"{API}/workspaces/{MAIN_WS_ID}/files/agents/{AGENT_NAME}.md",
    headers=HEADERS, json={"content": agent_content})
```

### 6e. Exit with promise tag

```python
print(f"<promise>{AGENT_NAME} cycle complete (branch={branch_taken})</promise>")
```

---

## Quick reference: branch checklist

Before you do ANY work, confirm in your head:

- [ ] I read my launch prompt and noted whether `MODE=discussion` or `MODE=execute` was set.
- [ ] I read `teams/roster.md` and determined `MY_TEAM`.
- [ ] I checked `agents/{AGENT_NAME}/workspace/result_latest.json` for an unposted prior result (Part 0 Check C).
- [ ] I picked exactly ONE branch from the Part 0 table.
- [ ] If resume-waiting: I will NOT claim new work; the GPU is still busy with my own training.
- [ ] If Part 5 (resume-and-post): I will post the prior result and set `posted_to_workshop=true`; I will NOT start a new experiment.
- [ ] If Part 2 (discussion): I will NOT touch any training code.
- [ ] If Part 3 (no-team): I will exit immediately after recording.
- [ ] If Part 4 (normal): every artifact I produce will have a corresponding AnonAPI API call.

If you cannot tick all boxes, exit cleanly via Part 6e.
