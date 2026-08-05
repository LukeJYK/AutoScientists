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

# GPU Agent Protocol

**STOP. Did you go through HEARTBEAT Part 0 first?** If not, go back. This file is only for agents who have been routed into Part 4 (Normal Cycle) by the Mode Selector. If the Mode Selector sent you to Part 2 (Discussion) or Part 3 (No-Team), do NOT read or execute this file — follow that branch instead.

You run experiments on a dedicated GPU. You belong to a team.

## Two rules that override everything below

1. **No team → no work.** Enforced by HEARTBEAT Part 0. If you reach this file, `MY_TEAM` is set.
2. **Every experiment MUST have a complete AnonAPI API trail:** POST [PROPOSAL] → add to queue → claim → train → write result file → release claim → POST [RESULT]. If KEEP, also PUT champion.md. This applies whether the experiment came from an analyst's queue or you self-designed it. Skip any step → invisible work → forbidden.

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

### Step 0 — Find Your Team (HARD GATE)

```python
# Read roster from main workspace (parse YAML client-side)
roster_raw = requests.get(f"{API}/workspaces/{MAIN_WS_ID}/files/teams/roster.md",
                          headers=HEADERS).json()
roster = parse_frontmatter(roster_raw).get("teams", {})

MY_TEAM = TEAM_WS_ID = None
for name, t in roster.items():
    if AGENT_NAME in t.get("members", []):
        MY_TEAM = name
        TEAM_WS_ID = t["workspace_id"]
        break

if MY_TEAM is None:
    # No team assigned. Per Rule 1, exit immediately. Do NOT run experiments.
    print(f"[EXIT] {AGENT_NAME}: no team in roster ({len(roster)} teams). "
          f"Waiting for monitor to form teams.")
    import sys; sys.exit(0)
```

**Do not** wrap this in a try/except that swallows the exit and continues. The only valid response to "no team" is to exit cleanly.

### Step 1 — Check GPU Availability

```bash
nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader,nounits
```
If >1000 MiB used on your GPU → do analyst work instead.

### Step 1.5 — Shared-Baseline Coordination — REQUIRED

If the champion file is in `awaiting_baseline` state (no metric_value
set yet), the WHOLE SYSTEM needs exactly ONE baseline run — not one per
team. Use claim-based coordination to avoid duplicated baselines.

```python
champ_raw = requests.get(f"{API}/workspaces/{MAIN_WS_ID}/files/champion.md",
                         headers=HEADERS).json()
champ = parse_frontmatter(champ_raw)

if champ.get("status") == "awaiting_baseline":
    # Try to claim the baseline lock with If-None-Match (atomic).
    # First GPU to arrive wins the lock and runs the baseline; every
    # other GPU reads a real experiment from queue instead.
    r = requests.put(f"{API}/workspaces/{MAIN_WS_ID}/files/baseline_lock.md",
                     headers={**HEADERS, "If-None-Match": "*"},
                     json={"content": f"holder: {AGENT_NAME}\nclaimed_at: {NOW}\n"})
    if r.status_code in (200, 201):
        # We got the lock — run champion unchanged as the shared baseline,
        # then seed champion.md for everyone.
        item = {"id": "baseline_shared",
                "axis": "seed",
                "direction": "none",
                "value": 0,
                "diff": "Run champion train.py unchanged (shared baseline)",
                "infrastructure_probe": True}
    else:
        # Someone else holds the lock — skip baseline, proceed to real
        # experiment from queue. If queue is empty, wait one rotation.
        print("[BASELINE] another agent is running the shared baseline; "
              "picking a real experiment from queue instead")
        # fall through to Step 3 (queue claim)
```

**Never run baseline on a team-by-team basis.** The champion metric is
global — one run is sufficient.

### Step 2 — Read Champion Config

```python
# Read champion config from main workspace
champ_raw = requests.get(f"{API}/workspaces/{MAIN_WS_ID}/files/champion.md",
                         headers=HEADERS).json()
champ = parse_frontmatter(champ_raw)
champ_version = champ_raw.get("version", 0)  # Save for race condition check later

# Read canonical champion train.py (SINGLE SOURCE OF TRUTH)
# Located at: {FOCUS_ROOT}/champion/train.py
# Copy it AND its runtime dependencies to your workspace before making changes.
#
# Copying only train.py is the #1 first-launch failure in this role:
# `uv run python train.py` will ModuleNotFoundError on `prepare.py` (or fail
# the `pyproject.toml` lookup, or pick a wrong dependency version without
# `uv.lock`). Both gpu5 and gpu6 hit this on 2026-05-26 — the auto-recovery
# costs 30-60s per agent and burns API budget. Just copy them all.
import shutil
from pathlib import Path
workdir = Path(f"{FOCUS_ROOT}/agents/{AGENT_NAME}/workspace/repo")
workdir.mkdir(parents=True, exist_ok=True)
for fname in ("train.py", "prepare.py", "pyproject.toml", "uv.lock"):
    src = Path(f"{FOCUS_ROOT}/champion") / fname
    if not src.exists():
        # Fallback to task/repo/ for files that aren't champion-tracked
        # (champion only tracks files that diff per experiment).
        src = Path(f"{FOCUS_ROOT}/task/repo") / fname
    shutil.copy(src, workdir / fname)
```

**Never read train.py from another agent's workspace.** Always use `{FOCUS_ROOT}/champion/train.py`.

### Step 2a — Biomlbench Experiment Priorities — READ IF BIOMLBENCH=true

If `BIOMLBENCH=true`, read this section in full before claiming or self-designing any experiment.

#### 2a-i. Register your approach (REQUIRED at start of every cycle)

Before you claim or design an experiment, register your intended approach in the shared
approach registry so other agents don't duplicate it:

```python
import json, fcntl
from pathlib import Path

reg_path = Path(f"{FOCUS_ROOT}/logs/approach_registry.json")
MY_APPROACH = "<one-line label, e.g. 'chemprop-GNN' or 'ChemBERTa-finetune' or 'Mordred+RF'>"

# Atomic read-modify-write with file lock
with open(reg_path, "r+") as f:
    fcntl.flock(f, fcntl.LOCK_EX)
    reg = json.load(f)
    taken = reg.get("taken", [])
    if MY_APPROACH in taken:
        print(f"APPROACH CONFLICT: '{MY_APPROACH}' already taken — pick a different paradigm")
        # Choose a different approach and repeat this check before proceeding
    else:
        taken.append(MY_APPROACH)
        reg["taken"] = taken
        f.seek(0); json.dump(reg, f, indent=2); f.truncate()
        print(f"Registered approach: {MY_APPROACH}  (registry now: {taken})")
    fcntl.flock(f, fcntl.LOCK_UN)
```

If `approach_registry.json` does not exist yet, create it:
```python
reg_path.write_text(json.dumps({"cycle": 1, "taken": [MY_APPROACH]}, indent=2))
```

**Do not proceed with training if another agent has already registered the same approach
this cycle.** Pick a different paradigm and re-register.

#### 2a-ii. Declare your compute mode — REQUIRED if GPU_AVAILABLE=True

After registering your approach and **before starting any training**, write a one-line file
declaring whether your experiment needs the GPU or can run on CPU only. The orchestrator
polls this file to decide whether to serialize or parallelize the next agent.

```python
# Determine compute mode based on your chosen approach
MY_COMPUTE = "gpu"   # set to "cpu" if your experiment is CPU-only

claim_path = Path(f"{FOCUS_ROOT}/logs/{AGENT_NAME}.gpu_claim")
claim_path.write_text(MY_COMPUTE + "\n")
print(f"[COMPUTE CLAIM] {AGENT_NAME}: {MY_COMPUTE}")
```

**Write this file as early as possible** — ideally right after approach registration, before
you read the queue or write any code. The orchestrator waits up to 120 s for this file;
if it doesn't appear, it assumes `gpu` and blocks the next agent unnecessarily.

**GPU experiments** (write `gpu`): anything that calls `torch`, `tensorflow`, or a CUDA
kernel — GNN training, transformer fine-tuning, neural network training. These serialize
because only 1 GPU is available.

**CPU experiments** (write `cpu`): classical ML (XGBoost, LightGBM, SVR, RF), Gaussian
processes, AutoML (FLAML/TPOT), offline embedding inference followed by a linear head,
any sklearn-based pipeline. These run in parallel with each other and with the active GPU
agent — they add throughput at zero GPU cost.

**Aim for a mix across the team each cycle.** If the approach registry already shows 2+
GPU approaches registered, strongly prefer a CPU experiment for your slot (and vice versa).
This keeps the GPU busy on deep models while CPU agents explore classical/ensemble methods
simultaneously.

#### 2a-iii. GPU vs CPU approach selection

Read `GPU_AVAILABLE` from your launch prompt. It determines which method classes are practical.

**If `GPU_AVAILABLE=True`** — strongly prefer GPU-native methods:

| Domain | Preferred approaches |
|--------|---------------------|
| Small-molecule ADMET | Chemprop (MPNN), PyG/DGL GNN, ChemBERTa/MolBERT, UniMol, Graph Transformer |
| Protein fitness | ESM-2 embeddings + head, MSA Transformer, Chemprop on SMILES if applicable |
| Single-cell | scVI VAE, Geneformer/scGPT, GNN on cell graph, CLIP-style multimodal |
| Pathology imaging | ViT/ResNet fine-tune, pathology FM (UNI, CONCH), nnU-Net |

You can run pretrained foundation model embeddings for feature extraction and use them as features for a classical ML model.

CPU-friendly methods (XGBoost+RDKit etc.) are fine as ONE fallback team — not as the
default for every agent. If GPU is available and the queue only has classical ML entries,
self-design a GPU-native experiment instead.

**If `GPU_AVAILABLE=False` (CPU only)** — diversify across these CPU-friendly paradigms
(do NOT all pick the same approach)

Paradigms: LightGBM/XGBoost, SVR, RF/ExtraTrees, Gaussian Process, Offline pretrained foundation model embeddings 

**Pick the paradigm your team was assigned in queue.md. If the queue is empty, pick the
highest-value unclaimed paradigm NOT in the registry.**

#### 2a-iv. Low-value experiment types to avoid

The following have low expected value and should NOT be prioritized:

1. **More HP search trials on an already-tuned model** — extra Optuna trials on the same
   architecture tend to overfit the CV split on small datasets.
2. **Fine-bracket sweeps of one regularization coefficient** — usually inside the CV noise band.
3. **More ensemble seeds on an unchanged model** — reduces variance slightly but adds nothing new.
4. **Single-parameter tuning of a model that's already had a tuning pass** — CV noise dominates.

If the queue contains only these types, self-design something that meaningfully changes the
approach. Post a [SUGGESTION] if you skip queued items so analysts can reprioritize.

**Why this matters:** biomlbench tasks span small-molecule ADMET, protein fitness, single-cell
genomics, and medical imaging — all with finite wall-clock budgets. The highest-value experiments
test a qualitatively different approach, not re-tuning a model the team has already optimized.

### Step 2b — Verify Task Specifications

**Before claiming any experiment, verify you understand the task requirements:**

```python
# Read task specification
task_spec_path = f"{FOCUS_ROOT}/task/TASK.md"
with open(task_spec_path) as f:
    task_content = f.read()

# For BioML tasks (ProteinGym, TDC), verify the fold split specification
if "fold_contiguous" in task_content:
    # Ensure you use the correct fold column as specified in TASK.md
    # Example check for ProteinGym:
    import re
    fold_match = re.search(r'fold_([a-z_]+5)', task_content)
    if fold_match:
        required_fold = fold_match.group(0)  # e.g., "fold_contiguous_5"
        print(f"TASK VERIFICATION: Using split = {required_fold}")
        # Verify your code uses this exact fold column before training
```

**Why this matters:** Task specs may specify a particular data split (e.g., `fold_contiguous_5` instead of `fold_random_5`). Using the wrong split will invalidate all results.

### Step 3 — Claim Experiment from Team Queue (REQUIRED)

**Safety: abort if a prior unposted result still sits in `result_latest.json`** (HEARTBEAT Part 0 Check C should have caught this; verify once more to prevent orphaned results):

```python
import json
from pathlib import Path
_p = Path(f"{FOCUS_ROOT}/agents/{AGENT_NAME}/workspace/result_latest.json")
if _p.exists():
    _pend = json.loads(_p.read_text())
    if not _pend.get("posted_to_workshop") and _pend.get("status") == "complete":
        raise RuntimeError(f"[SAFETY] unposted result for {_pend.get('exp_id')} — re-enter HEARTBEAT, go to Part 5")
```

Check your team's queue for pending experiments.

```python
queue_raw = requests.get(f"{API}/workspaces/{TEAM_WS_ID}/files/queue.md",
                         headers=HEADERS).json()
queue = parse_frontmatter(queue_raw)
pending = queue.get("pending", [])

if pending:
    # Normal path: claim from queue
    item = pending[0]
else:
    # EMPTY QUEUE — self-propose a bold experiment within your team's
    # dimension. Read your team's strategy.md, dead_ends.md, and the
    # champion code to pick the highest-value untested change. Then:
    #   1. Post a [PROPOSAL] to the workshop (full rationale + diff)
    #   2. Add it to your team's queue.md
    #   3. Claim it below
    # This maintains the full API trail while not wasting GPU time.
    # Teams are HYPOTHESIS-based, not axis-based — propose any axis as
    # long as the change is consistent with your team's hypothesis.
    # Prefer changes that are:
    #   - Bold (ambition quota: ≥10% param change, or structural variant)
    #   - Not in dead_ends.md
    #   - Grounded in champion code analysis, not speculation
    item = self_designed_item  # you create this from your analysis
```

**Every experiment must have a full API trail:** [PROPOSAL] post → queue
entry → claim → training → result file → [RESULT] post. Self-designed
experiments follow the same trail; the only difference is the GPU agent
writes the proposal instead of an analyst.

**Every queue item and [PROPOSAL] MUST include axis / direction / value
tags.** These feed the empirical-priors ranking, direction-diversity
check, and failure-range check. Claiming or self-designing an item
without these tags is forbidden — if the queue item is missing them,
reject the claim and post a [SUGGESTION] asking the analyst to fix the
queue.

**Teams are hypothesis-based, not axis-based.** You may propose any
axis as long as the change is consistent with your team's hypothesis.
If another team's proposal looks promising and shares your hypothesis's
lens, you can claim it.
# **Discussion-gate check:** if the item is `discussion_pending: true`,
# verify its [PROPOSAL] post has at least one comment from a non-author
# before claiming. A comment from the proposer themselves does not count.
# Skip items that don't yet meet this bar and pick the next one.
#
# Two auto-clear overrides prevent the gate from starving the queue
# (observed in gpt-nano-agents 2026-05-26: cycles 7-12 had GPU agents
# posting near-empty "[GPU-REVIEW] acknowledged" comments just to satisfy
# the gate, burning API budget for no information value):
#
#   1. Time-based: if the proposal was posted more than DISCUSSION_GRACE
#      ago (default 15 min), claim it anyway. The discussion window has
#      passed; agents who wanted to comment had their chance.
#   2. Queue-starvation: if THIS is the only `discussion_pending: true`
#      item remaining and there are no non-pending items either, claim
#      it. A blocked GPU is worse than a thinly-discussed proposal.
import time
DISCUSSION_GRACE_SEC = 15 * 60

if item.get("discussion_pending"):
    proposal_id = item.get("proposal_post")
    cleared = False

    # Override 1: time-based grace
    proposed_at = item.get("proposed_at") or item.get("created_at")
    if proposed_at:
        try:
            from datetime import datetime, timezone
            t0 = datetime.fromisoformat(proposed_at.replace("Z", "+00:00"))
            if (datetime.now(timezone.utc) - t0).total_seconds() > DISCUSSION_GRACE_SEC:
                cleared = True  # waited long enough
        except Exception:
            pass

    # Override 2: starvation — this is the only claimable item
    if not cleared:
        other_claimable = [it for it in (queue.get("pending") or [])
                           if it.get("id") != item["id"]
                           and not it.get("discussion_pending")]
        if not other_claimable:
            cleared = True  # rather claim discussion-pending than idle the GPU

    # Default path: require a non-author comment
    if not cleared and proposal_id:
        comments = requests.get(f"{API}/posts/{proposal_id}/comments",
                                headers=HEADERS).json().get("data", [])
        proposer = item.get("proposed_by", "")
        non_author = [c for c in comments
                      if proposer not in str(c.get("author", ""))]
        if not non_author:
            # Not yet discussed — skip to next item
            item = None  # fall through to next pending item or self-design

# Claim via read-modify-PUT with If-Match (DO NOT use PATCH — it corrupts nested YAML
# frontmatter like pending: lists. Confirmed to destroy queue.md across teams.)
queue_version = queue_raw.get("version", 0)
fm = parse_frontmatter(queue_raw)
fm.setdefault("claims", {})[AGENT_NAME] = {"exp_id": item["id"], "claimed_at": now}
body = queue_raw.get("content", "").split("---", 2)[-1]
new_content = f"---\n{yaml.safe_dump(fm, sort_keys=False)}---{body}"
# Validate round-trip before writing
assert yaml.safe_load(new_content.split("---")[1]) == fm, "frontmatter round-trip failed"
r = requests.put(f"{API}/workspaces/{TEAM_WS_ID}/files/queue.md",
    headers={**HEADERS, "If-Match": str(queue_version)},
    json={"content": new_content})
if r.status_code == 409:
    # Conflict — another agent claimed concurrently. Re-read and retry or pick a different item.
    pass
```

If queue is empty, design your own experiment. Your only constraint
is **consistency with your team's hypothesis**: the change you propose
must be one your team's hypothesis predicts will improve the metric.
Any axis is fair game. This is the triangulation value of
hypothesis-based teams — the same experiment may be proposed by
different teams for different reasons.

```python
# Discover your team's context for self-designed experiments
team_files = requests.get(f"{API}/workspaces/{TEAM_WS_ID}/files",
                          headers=HEADERS).json()["files"]
# Read strategy.md, dead_ends.md, analysis/ files from YOUR team
# Design an experiment within YOUR dimension
```

### Step 3b — Dedup Check

Before training, verify this experiment hasn't already been run AND isn't already in the code:

```python
# 1. Search workspace results for similar experiments
hits = requests.get(f"{API}/workspaces/{MAIN_WS_ID}/search?q={mechanism_keyword}",
                    headers=HEADERS).json()["results"]
# If results/ files already cover this mechanism, skip it

# 2. Search team dead ends
team_hits = requests.get(f"{API}/workspaces/{TEAM_WS_ID}/search?q={mechanism_keyword}",
                         headers=HEADERS).json()["results"]
# If your mechanism appears in dead_ends or similar analysis, skip it

# 3. Check if the mechanism already exists in champion code
champion_code = open(f"{FOCUS_ROOT}/champion/train.py").read()
if mechanism_keyword.lower() in champion_code.lower():
    print(f"ALREADY IN CODE: {mechanism_keyword} — skip this experiment")
    # Release claim and pick next experiment

# 4. **Target validation** — if your change reads or writes a named variable or
#    collection in the target code (a list of params, a config dict, a feature
#    set), verify that collection is non-empty and actually wired into the code
#    path you expect. Helper variables are sometimes defined but never referenced
#    — tuning them produces noise-only deltas that look like real signal.
#    Catch this BEFORE running, not after cascades of dead hypotheses.
#
# Example pattern:
#   target_collection = f"{group_name}_items"
#   if f"{target_collection} = []" in code:
#       print(f"DEAD TARGET: {target_collection} is empty — change would be a no-op")
#       # Release claim, skip, and post a [SUGGESTION] for code cleanup
```

### Step 3c — External Repo Setup (if experiment requires it)

If the claimed experiment depends on a GitHub repo or pretrained checkpoint
that is not already installed in `{FOCUS_ROOT}/.cache/repos/`:

1. Read `{FOCUS_ROOT}/system/external-repo-setup/SKILL.md` — it is the
   complete protocol for cloning repos, installing deps, downloading weights,
   extracting embeddings, and caching them.
2. Check whether a teammate already did the setup:
   ```python
   # Search team workspace for setup notes
   team_hits = requests.get(
       f"{API}/workspaces/{TEAM_WS_ID}/search?q=setup_{REPO_NAME}",
       headers=HEADERS
   ).json()["results"]
   ```
   If `knowledge/setup_{REPO_NAME}.md` exists, load pre-cached embeddings
   instead of re-running extraction.
3. After successful setup, write `knowledge/setup_{REPO_NAME}.md` to the
   team workspace so other GPU agents can reuse the cached embeddings.

**Time budget:** factor in 15-30 min for first-time setup when deciding
whether to run this experiment or pick a lighter one from the queue instead.

### Step 4 — Apply Change and Train

Apply ONE change from the experiment's diff, then **block synchronously** on
training. Detached / fire-and-forget training is forbidden: round 19 showed
that when the agent's claude session ends before parsing `train.stdout`, the
real metric is computed but never recorded — the entire cycle's work
vanishes. The agent MUST wait for the training subprocess and then run
Steps 5–8 in the same session.

**Before training, verify the diff actually landed.** If the Edit tool said
`old_string not found`, `patch -p1` printed `FAILED` / `Hunk #N FAILED`, or the
resulting `train.py` is byte-identical to `champion/train.py`, the proposal
was NOT tested — training would just re-measure the baseline at noise. Set
`item["diff_applied"] = False` on the sentinel BEFORE launching training, or
better, skip training entirely and post `[RESULT] {exp_id}: FAILED` so the
proposal can be re-queued with a fresh diff. Phantom KEEPs from this exact
path (gpt-nano-pubrun round on 2026-05-26: `data_v7`, `0.979985`, diff
rejected) corrupted the champion lineage — never let baseline noise be
mistaken for evidence about a change.

```python
import filecmp
diff_applied = not filecmp.cmp(
    str(rep / "train.py"),
    f"{FOCUS_ROOT}/champion/train.py",
    shallow=False,
)
item["diff_applied"] = diff_applied
if not diff_applied:
    print(f"[STEP4] diff for {exp_id} did NOT apply — train.py matches champion. "
          f"Marking FAILED and skipping training.")
    # Jump to Step 5 with outcome="FAILED", our_metric=None.
```

**Pattern A (default, foreground shell).** Use when you just want to watch
training in the current shell:

```bash
cd $FOCUS_ROOT/agents/$AGENT_NAME/workspace/repo
CUDA_VISIBLE_DEVICES=$GPU_ID \
UV_CACHE_DIR=$FOCUS_ROOT/.cache/uv HF_HOME=$FOCUS_ROOT/.cache/huggingface \
TORCH_HOME=$FOCUS_ROOT/.cache/torch \
uv run python train.py
```

**Pattern B (blocking subprocess from Python, capture stdout/stderr to
files).** Use when you want stdout/stderr persisted on disk for later
inspection. This is still SYNCHRONOUS — `subprocess.run` waits for the
training process to exit. NEVER use `subprocess.Popen` without an
immediately-following `proc.wait()`; NEVER use `nohup ... &`; NEVER exit
the agent session while training is still running.

```python
import json, os, subprocess
from pathlib import Path
from datetime import datetime, timezone

ws  = Path(f"{FOCUS_ROOT}/agents/{AGENT_NAME}/workspace")
rep = ws / "repo"
out, err = ws / f"train_{exp_id}.stdout", ws / f"train_{exp_id}.stderr"

sentinel = {
    "status": "running", "posted_to_workshop": False,
    "exp_id": exp_id, "agent": AGENT_NAME, "item": item, "queue_claimed": True,
    "direction": direction, "val_score": None,
    "submission_path": str(rep / f"submission_{exp_id}.csv"),
    "train_path":      str(rep / f"train_{exp_id}.py"),
    "stdout_path": str(out), "stderr_path": str(err),
    # Record OUR pid so HEARTBEAT Part 0 Check C can tell whether we died
    # ungracefully (rate limit, OOM, SIGKILL) vs. legitimately still training.
    # `pid: None` would make _alive() return False and incorrectly route a
    # live cycle to resume-and-post.
    "pid": os.getpid(), "monitor_id": None, "description": description,
    "launched_at": datetime.now(timezone.utc).isoformat(),
}
(ws / "result_latest.json").write_text(json.dumps(sentinel, indent=2, default=str))

# BLOCK until training finishes. 20-min hard cap matches the per-experiment
# budget; raise it locally if you genuinely need longer runs (and document why).
result = subprocess.run(
    ["uv", "run", "python", "train.py"],
    cwd=str(rep),
    capture_output=True,
    text=True,
    timeout=1200,
    env={**os.environ, "CUDA_VISIBLE_DEVICES": str(GPU_ID),
         "UV_CACHE_DIR": f"{FOCUS_ROOT}/.cache/uv",
         "HF_HOME":      f"{FOCUS_ROOT}/.cache/huggingface",
         "TORCH_HOME":   f"{FOCUS_ROOT}/.cache/torch"},
)
out.write_text(result.stdout)
err.write_text(result.stderr)
training_succeeded = result.returncode == 0
sentinel["status"] = "complete" if training_succeeded else "failed"
sentinel["returncode"] = result.returncode
(ws / "result_latest.json").write_text(json.dumps(sentinel, indent=2, default=str))
# Now parse the metric from result.stdout and continue to Step 4b → Step 5
# in this same session — do NOT exit until the result is posted.
```

If your training is too long to fit in one session, split it: run a shorter
config (fewer steps, smaller batch) so the metric still flows back this
cycle. A recorded partial result beats a perfect orphaned one.

After training, save outputs to **agent-local paths** (never `task/` or `champion/`):

```python
import shutil
from pathlib import Path

agent_workspace = Path(f"{FOCUS_ROOT}/agents/{AGENT_NAME}/workspace/repo")

# Save a stamped copy of the submission for this experiment
agent_sub = agent_workspace / f"submission_{exp_id}.csv"
shutil.copy(agent_workspace / "submission.csv", agent_sub)

# Save a stamped copy of the train script for this experiment
agent_train = agent_workspace / f"train_{exp_id}.py"
shutil.copy(agent_workspace / "train.py", agent_train)

print(f"[ISOLATION] saved submission → {agent_sub}")
print(f"[ISOLATION] saved train     → {agent_train}")
```

**Stamped files belong here in agent-local paths.** The shared `champion/train.py` is propagated by the KEEP-winning agent in Step 7b1 (see below) — not from this step and not by the orchestrator. The stamped copy must exist before Step 7b1 can copy it.

### Step 4b — Analyze Training Dynamics — REQUIRED

After training completes, analyze the training log before recording the
result. This takes 30 seconds and produces diagnostic signals that are
more informative than the final metric alone.

Check these three things from the training output:

1. **Was the loss still decreasing when training ended?** Compare the
   loss at the final step to the loss at ~80% of training. If the loss
   is still dropping meaningfully (>1% of its total range), the model
   is **undertrained** — it would benefit from more steps. Note this in
   the result file. This signal suggests step-increasing changes
   (smaller batch, shorter sequences, faster kernels) are productive.

2. **Did the loss plateau early?** If the loss flattened before ~60%
   of training, the model has **excess capacity** for this step count.
   Note this. This signal suggests capacity can be reduced (smaller
   model) or step count decreased (larger batch) without loss.

3. **How many training steps completed?** Record `num_steps` and
   `tokens_seen` in the result file. These are the key throughput
   metrics. Any experiment that reduces steps by >10% relative to
   champion is fighting an uphill battle in a fixed-time benchmark —
   flag this prominently so analysts can factor throughput into their
   proposals.

Include these diagnostics in every result file under a `## Training
Dynamics` section. Analysts use this information in Step 1b2 (post-KEEP
inductive reasoning) to understand WHY a KEEP worked, not just that it
did.

### Step 5 — Record Result

**Before recording: re-read champion.md to handle race conditions.**

```python
# Re-read champion (may have changed during our 5-min training)
fresh_raw = requests.get(f"{API}/workspaces/{MAIN_WS_ID}/files/champion.md",
                         headers=HEADERS).json()
fresh_champ = parse_frontmatter(fresh_raw)
# Generic metric handling (supports different optimization directions)
metric_name = fresh_champ["metric_name"]  # task defines this in champion.md
direction = fresh_champ.get("direction", "minimize")  # "minimize" or "maximize"
current_best = fresh_champ.get(metric_name, float("inf") if direction == "minimize" else float("-inf"))
fresh_version = fresh_raw.get("version", 0)

race_condition = (fresh_version != champ_version)
if race_condition:
    print(f"Champion changed during training (v{champ_version} → v{fresh_version})")

# Compare against CURRENT champion, not the one we read before training.
# Use < for minimize (smaller is better), > for maximize (larger is better).
#
# IMPORTANT: a result is only meaningful if the proposed diff actually applied.
# If Step 4's edit failed (Edit tool said old_string not found, patch -p1
# rejected hunks, etc.) and you trained on the untouched champion code anyway,
# the metric you measured is baseline noise — NOT evidence about the proposal.
# Recording it as KEEP corrupts the champion (a phantom that didn't test the
# proposed change); recording it as DISCARD wrongly refutes the proposal.
# Mark FAILED so the orchestrator skips champion promotion and analysts can
# re-queue the proposal with a fresh diff.
diff_applied = bool(item.get("diff_applied", True))  # default True for legacy items

if not diff_applied:
    outcome = "FAILED"
elif (direction == "minimize" and our_metric < current_best) or \
     (direction == "maximize" and our_metric > current_best):
    outcome = "KEEP"
else:
    outcome = "DISCARD"
```

Write to **main workspace** (visible to all teams):
```python
requests.put(f"{API}/workspaces/{MAIN_WS_ID}/files/results/{item['id']}.md",
    headers=HEADERS, json={"content": result_markdown})
```

### Step 6 — Release Claim AND Move Item to Completed

Atomically do BOTH in a single read-modify-PUT: drop the claim AND move
the experiment record from `pending:` → `completed:`. Doing only the first
(the historic pattern) leaves stale rows in `pending:`, forcing the next
analyst cycle to hand-prune the queue before they can propose. Observed in
gpt-nano-agents 2026-05-26: cycles 2-4 each had analysts spending several
turns cleaning up DISCARDed-but-still-pending items.

```python
# Read-modify-PUT with If-Match (NEVER PATCH — corrupts nested pending: list).
# Missing claim or 409 is benign on resume (monitor's 30-min sweep may have cleared it).
from datetime import datetime, timezone
q_raw = requests.get(f"{API}/workspaces/{TEAM_WS_ID}/files/queue.md", headers=HEADERS).json()
q_fm  = parse_frontmatter(q_raw)

claim_removed = q_fm.get("claims", {}).pop(AGENT_NAME, None) is not None

# Move the just-finished item from pending → completed in the same write.
pending = q_fm.get("pending", []) or []
completed = q_fm.get("completed", []) or []
remaining = []
for it in pending:
    if it.get("id") == exp_id:
        it = dict(it)
        it["completed_at"] = datetime.now(timezone.utc).isoformat()
        it["completed_by"] = AGENT_NAME
        it["outcome"]      = outcome  # KEEP / DISCARD / FAILED from Step 5
        it["val_score"]    = our_metric
        completed.append(it)
    else:
        remaining.append(it)
q_fm["pending"]   = remaining
q_fm["completed"] = completed

if claim_removed or len(remaining) != len(pending):
    q_body = q_raw.get("content", "").split("---", 2)[-1]
    q_new  = f"---\n{yaml.safe_dump(q_fm, sort_keys=False)}---{q_body}"
    requests.put(f"{API}/workspaces/{TEAM_WS_ID}/files/queue.md",
        headers={**HEADERS, "If-Match": str(q_raw.get("version", 0))},
        json={"content": q_new})  # 409 OK — continue to Step 7/8
```

### Step 7 — Update Champion (KEEP only)

If result is strictly better than current champion:

**CRITICAL: Before propagating, make ALL improvements unconditional in your train.py.**
Do NOT gate changes behind `if EXPERIMENT_ID == "exp_foo"` or similar checks.
Every improvement must be baked into the code as the default behavior.
If you find gated code from previous experiments, make it unconditional too.

```python
# Bad:  if EXPERIMENT_ID == "exp_my_change": value *= factor
# Good: value *= factor  (always active)
```

#### Step 7.0 — Multi-Seed Gate — REQUIRED

**Before writing the champion file, confirm the result is not a lucky
seed.** Read the team's empirically-measured seed standard deviation
from `knowledge/noise_floor.md` (or the team's canonical location for
it). Let `sigma` be that value.

- **If `|delta| > sigma * MARGIN`** (default `MARGIN = 2`), the result
  is outside the one-seed noise band. Propagate as normal.
- **If `|delta| <= sigma * MARGIN`**, the delta is inside a band where
  a lucky seed could account for the improvement. You MUST re-run the
  same code change on a **different random seed** before promoting.
  - If the second-seed result is also strictly better than champion,
    propagate.
  - If the second-seed result is not better, classify as near-miss,
    post a `[NEAR-MISS]` instead of promoting, and leave champion
    unchanged. Do NOT overwrite champion on half-confirmed evidence.

```python
# Read empirical noise pairs (see analyst Step 0.5). If n<3, use
# conservative 0.003 band.
nf_raw = requests.get(
    f"{API}/workspaces/{MAIN_WS_ID}/files/knowledge/noise_floor_data.md",
    headers=HEADERS).json()
pairs = parse_pairs(nf_raw.get("content", ""))
if len(pairs) >= 3:
    sigma = pooled_std(pairs)
    noise_floor = sigma
else:
    noise_floor = 0.0015  # conservative, implies 2σ band ≈ 0.003

MARGIN = 2.0
if abs(delta) > noise_floor * MARGIN:
    promote = True
else:
    # Borderline — re-run on a different seed before promoting, AND
    # append the (metric_a, metric_b, code_hash) triple to
    # knowledge/noise_floor_data.md so future runs get better σ for
    # free. This is the lazy-calibration source.
    second_seed_metric = run_training_on_fresh_seed(code=our_code)
    _append_noise_pair(MAIN_WS_ID, our_metric, second_seed_metric, code_hash=sha1_of_train_py)
    promote = (second_seed_metric is strictly better than current_best)
```

The append is REQUIRED on every second-seed invocation. Without it the
noise floor never accumulates and the conservative default (0.003)
stays active forever, which blocks real small-delta KEEPs long-term.

**3-seed confirmation for persistent NEAR-MISSes.** If the same
(axis, direction, value) has already produced 2 NEAR-MISS results
with a consistent pattern (same seed beats champion, other seed
doesn't), do NOT discard the result as noise. Instead, launch a
**third** seed on the same code. Promote only if ≥2 of the 3 seeds
beat champion. This resolves the case where a real sub-noise signal
keeps showing up but can never clear the 2-seed gate.

Look up prior same-tuple NEAR-MISSes in `knowledge/near_miss_ledger.md`
before classifying. If current run is the 3rd attempt on the same
tuple, run seed 3 immediately; don't require another full claim cycle.

**Why this exists:** the champion file is the baseline every subsequent
experiment is measured against. A single-seed lucky draw that slips
into champion corrupts every downstream comparison — every "it's
better by +0.0005" judgment is made relative to a fictional baseline.
One measurement showed the seed-variance band was 4-6× larger than
the previously-assumed noise floor, which means several past champion
updates may have been artifacts. A multi-seed confirmation gate
prevents this from continuing to accumulate.

**If `knowledge/noise_floor.md` doesn't exist yet**, your team has not
measured seed variance. Before promoting anything near noise, post a
`[SUGGESTION]` requesting a seed-variance infrastructure probe (or run
it yourself as a dormant-team activity), then apply this gate once a
measurement exists. Until then, treat any delta smaller than the
prior-champion-delta as "not confirmed" and do not promote.

#### Step 7a — Extract Reproduction Information

```python
import re, json

# 1. Read YOUR train.py docstring (experiment description)
with open(f"{FOCUS_ROOT}/agents/{AGENT_NAME}/workspace/repo/train.py") as f:
    code = f.read()
docstring_match = re.search(r'"""(.*?)"""', code, re.DOTALL)
experiment_description = docstring_match.group(1).strip() if docstring_match else "No description provided"

# 2. Parse JSON hyperparameters from training stdout
# train.py prints JSON between === markers. Extract it:
json_match = re.search(r'=+\n({.*?})\n=+', training_stdout, re.DOTALL)
hyperparameters_json = json.loads(json_match.group(1)) if json_match else {}
```

#### Step 7b — Build Complete champion.md

**champion.md must be a complete standalone reproduction recipe.** Include ALL information needed to reproduce without reading train.py.

**Recorded `metric_value` is the BEST seed observed.** When a multi-seed
gate fired in Step 7.0, two measurements of the same code exist
(`our_metric` from the proposal-default seed and `second_seed_metric`
from the confirmation seed). Use the optimization-direction-best of
the two so subsequent agents diff against the strongest evidence
this code can produce, not against the worse draw. The other seed's
value is preserved in `knowledge/noise_floor_data.md` as a
reproducibility ledger and contributes to σ.

```python
# Choose the BEST seed value across all multi-seed runs of this code.
# direction="minimize" → use min; direction="maximize" → use max.
seed_metrics = [our_metric] + ([second_seed_metric] if 'second_seed_metric' in dir() else [])
champion_metric = min(seed_metrics) if direction == "minimize" else max(seed_metrics)

# Read current champion version for If-Match
current_raw = requests.get(f"{API}/workspaces/{MAIN_WS_ID}/files/champion.md", headers=HEADERS).json()
current_version = current_raw.get("version", 0)

champion_content = f"""---
metric_name: {metric_name}
metric_value: {champion_metric}
seed_values: {seed_metrics}
direction: {direction}
experiment_id: {exp_id}
agent: {AGENT_NAME}
timestamp: {datetime.now(timezone.utc).isoformat()}
---

# Champion: {exp_id}

## Experiment Description

{experiment_description}

## Result

- **Recorded metric (best of {len(seed_metrics)} seeds):** {metric_name} = {champion_metric}
- **All seed values:** {seed_metrics}
- **Delta from previous:** {delta:+.6f}

## Complete Hyperparameters

```json
{json.dumps(hyperparameters_json, indent=2)}
```

## Reproduction

1. Copy `{FOCUS_ROOT}/champion/train.py`
2. Run: `CUDA_VISIBLE_DEVICES=0 uv run python train.py`
3. Expected: {metric_name} ∈ {seed_metrics} (recorded best = {champion_metric})

## Provenance

- Agent: {AGENT_NAME}
- Timestamp: {datetime.now(timezone.utc).isoformat()}
- Source: {FOCUS_ROOT}/champion/train.py
"""

requests.put(f"{API}/workspaces/{MAIN_WS_ID}/files/champion.md",
    headers={**HEADERS, "If-Match": str(current_version)},
    json={"content": champion_content})
```

#### Step 7b1 — Propagate champion/train.py — REQUIRED on KEEP

**Immediately after the champion.md PUT succeeds, you MUST copy your stamped train file
to `{FOCUS_ROOT}/champion/train.py` and append a SOURCE line.** The local champion file
is read by every subsequent rotation's GPU agent in Step 2 — leaving it stale corrupts
every downstream baseline. This step is the agent's responsibility, not the orchestrator's.

```python
import shutil
from datetime import datetime, timezone
from pathlib import Path

# Atomic write: temp-then-rename so concurrent KEEPs cannot half-overwrite.
src = Path(f"{FOCUS_ROOT}/agents/{AGENT_NAME}/workspace/repo/train_{exp_id}.py")
dst = Path(f"{FOCUS_ROOT}/champion/train.py")
tmp = dst.with_suffix(".py.tmp")
shutil.copy(src, tmp)
tmp.replace(dst)  # atomic on POSIX

# Append provenance to champion/SOURCE (one line per promotion).
src_log = Path(f"{FOCUS_ROOT}/champion/SOURCE")
ts = datetime.now(timezone.utc).isoformat()
with src_log.open("a") as f:
    f.write(f"{exp_id} {our_metric:.6f} {AGENT_NAME} {ts}\n")
```

**Race-safety:** if multiple GPU agents land KEEPs in the same rotation, the champion.md
PUT serializes them via If-Match — only one wins. The losing agent's `our_metric < current_best`
check at the top of Step 7 will already have failed (champion changed during their training),
so they will not enter Step 7b1. The winning agent's `tmp.replace(dst)` is atomic.

**Why this exists:** the champion file is the baseline every subsequent experiment's
diff is applied against. A 4-KEEP-deep stale champion file means agents who don't know
to read the latest stamped train file in the winning workspace will silently regress
the codebase. This step replaces the prior "orchestrator promotes" model that was
unreliable in practice.

#### Step 7c — Write result_latest.json (agent-local sentinel)

`result_latest.json` is your post-training state record — it lets HEARTBEAT Part 0
resume an unposted result on the next session and is read by analysts who want to
know your last outcome. Champion propagation already happened in Step 7b1; this file
is purely a sentinel.

```python
import json
from pathlib import Path

# Merge with any Step 4 in-flight sentinel to preserve stdout_path/launched_at.
rl = Path(f"{FOCUS_ROOT}/agents/{AGENT_NAME}/workspace") / "result_latest.json"
prior = json.loads(rl.read_text()) if rl.exists() else {}
rep = Path(f"{FOCUS_ROOT}/agents/{AGENT_NAME}/workspace/repo")

rl.write_text(json.dumps({**prior,
    "val_score": our_metric, "direction": direction,
    "exp_id": exp_id, "agent": AGENT_NAME,
    "submission_path": str(rep / f"submission_{exp_id}.csv"),
    "train_path":      str(rep / f"train_{exp_id}.py"),
    "timestamp": datetime.now(timezone.utc).isoformat(),
    # Resume fields — HEARTBEAT Part 0 Check C reads these. REQUIRED.
    "status": "complete", "posted_to_workshop": False, "result_post_id": None,
    "item": prior.get("item") or item,
    "queue_claimed": prior.get("queue_claimed", True),
    "description": description,
}, indent=2, default=str))
```

**If DISCARD:** write the result to `dead_ends.md` in your team workspace so analysts and other
GPU agents skip this mechanism family. Use If-Match to avoid clobbering concurrent writes.

```python
if outcome == "DISCARD":
    de_raw = requests.get(f"{API}/workspaces/{TEAM_WS_ID}/files/dead_ends.md",
                          headers=HEADERS).json()
    de_content = de_raw.get("content", "# Dead Ends\n\n")
    de_version = de_raw.get("version", 0)

    # Structured entry — REQUIRED. Future proposals check whether their
    # (axis, direction, value) falls inside a recorded DISCARD range.
    # Unstructured free-text entries defeat the failure-range check and
    # are not permitted.
    axis = item.get("axis") or "UNKNOWN"
    direction = item.get("direction") or "UNKNOWN"
    value = item.get("value")
    fam = "_".join(exp_id.split("_")[:2])
    entry = (
        f"\n- exp_id: {exp_id}\n"
        f"  axis: {axis}\n"
        f"  direction: {direction}\n"
        f"  value: {value}\n"
        f"  delta: {delta:+.6f}\n"
        f"  family: {fam}\n"
        f"  date: {datetime.now(timezone.utc).date()}\n"
        f"  reason: {experiment_description[:160].replace(chr(10), ' ')}\n"
    )

    r = requests.put(f"{API}/workspaces/{TEAM_WS_ID}/files/dead_ends.md",
                     headers={**HEADERS, "If-Match": str(de_version)},
                     json={"content": de_content + entry})
    if r.status_code == 409:
        print("dead_ends.md conflict — skipping write (analyst will update next cycle)")
    else:
        print(f"Recorded DISCARD in dead_ends.md (HTTP {r.status_code})")
```

### Step 8 — Post Result to Workshop (MANDATORY)

**This step is required for EVERY experiment, KEEP or DISCARD.** A result file in the workspace is not enough — the workshop post is what notifies analysts and other teams. Skipping this step makes the experiment invisible to the rest of the system.

Post as a NEW workshop post (not a comment on the kickoff thread):

```python
r = requests.post(f"{API}/posts", headers=HEADERS, json={
    "workshop": WORKSHOP,
    "title": f"[RESULT] {item['id']}: {metric_name}={our_metric} ({outcome})",
    "content": f"## Experiment\n{description}\n\n## Result\n{metric_name}: {our_metric}\nDelta: {delta}\nOutcome: {outcome}\nRace condition: {race_condition}\n\n## Team\n{MY_TEAM}",
    "notify_agents": team_members,
    "tags": [f"team:{MY_TEAM}", "type:result", f"outcome:{outcome}"]
})
result_post_id = r.json().get("id") if r.ok else None
```

### Step 8b — Mark result as posted (REQUIRED — prevents duplicate [RESULT] next cycle)

```python
from datetime import datetime, timezone
rl_path = Path(f"{FOCUS_ROOT}/agents/{AGENT_NAME}/workspace") / "result_latest.json"
rl = json.loads(rl_path.read_text())
rl.update({"status": "posted", "posted_to_workshop": True,
           "result_post_id": result_post_id,
           "posted_at": datetime.now(timezone.utc).isoformat()})
rl_path.write_text(json.dumps(rl, indent=2, default=str))
```

### Step 9 — Near-Miss Protocol

A "near-miss" only makes sense as a **signal-carrying DISCARD** — a result
close enough to champion that the underlying mechanism may still be
productive. It must be anchored to the **team's noise floor** (see the
analyst Step 1a noise-floor rule), not a fixed global delta threshold:

- **Delta inside the noise band:** NOT a near-miss. It's noise. Do NOT
  post a [NEAR-MISS] and do NOT trigger a cross-team follow-up. If it's
  the only point on its axis, leave the axis open; if it's part of a
  bracketed minimum already above the noise band, the axis is closed.
- **Delta clearly above the noise band but within a small multiple of
  it:** legitimate near-miss. Post a [NEAR-MISS] and let analysts apply
  the Step 1a far / opposite / 2-point rule before any follow-up.

```python
noise_floor = ...  # team's current estimate from knowledge/noise_floor.md
if (delta > noise_floor) and (delta < noise_floor * SMALL_MULTIPLE):
    requests.post(f"{API}/posts", headers=HEADERS, json={
        "workshop": WORKSHOP,
        "title": f"[NEAR-MISS] {item['id']}: delta=+{delta}",
        "content": f"Near-miss. Team: {MY_TEAM}. Description: {description}. "
                   f"Delta: {delta} (noise floor {noise_floor}).",
        "notify_agents": all_agent_names,
        "tags": ["type:near-miss"],
    })
```

**Do not** simultaneously label a result as a near-miss AND register it
as an axis-exhaustion trigger — if it qualifies for the former it is
signal, if it qualifies for the latter it is too high above the noise
floor for any refinement to reach KEEP and the axis is closed.

### Step 10 — Run Second Experiment

Go back to Step 2 for a second experiment before finishing your session.

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
