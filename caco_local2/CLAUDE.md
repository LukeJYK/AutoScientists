# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is the AutoScientists repository, a decentralized team of AI agents for long-running computational scientific experimentation. Unlike prior agent systems that follow a single research trajectory, AutoScientists agents self-organize into teams around promising hypotheses, critique each other's proposals before spending experimental compute, and share successes and failures so the system avoids redundant exploration and sustains parallel search.

## Key Components

### Task Structure
- Tasks are defined in `task-{name}/` directories with:
  - `TASK.md` - Task specification with constraints and evaluation details
  - `LAUNCH.md` - Task profile with hooks for execution
  - Data files in `data/` directory (train.csv, test_features.csv, sample_submission.csv)
  - `train.py` - Model training script (to be written by participants)

### Multi-Agent Architecture
The system uses a multi-agent framework with:
- **Monitor Agent**: Sets up infrastructure and coordinates teams
- **Analyst Agents**: Propose ideas and analyze results
- **GPU Agents**: Execute experiments and report results
- **Workshop System**: Central coordination point using ClawInstitute API

### Core Workflow
1. **Bootstrap Phase**: Monitor sets up workshop, agents, and workspace
2. **Discussion Phase**: Agents propose dimensions and form teams
3. **Execution Phase**: Teams run experiments and report results
4. **Adaptation Phase**: When teams stagnate, restructure approaches

## Key Directories and Files

- `task/` - Contains the current task definition and data
- `agents/` - Contains agent configurations and roles
- `system/` - System reference materials and templates
- `runbook.md` - Execution instructions for the system
- `run_metadata.json` - Metadata about current run

## Working with the System

### Running Experiments
To run a task, use:
```bash
claude -p "Read runbook.md and execute. Task: task-autoresearch. Run name: ar_v1."
```

### Using the ClawInstitute API
The system communicates through the ClawInstitute API:
- Use `requests.get`/`post`/`patch`/`delete` to interact with the API
- All file operations require parsing frontmatter client-side (not server-side)
- File discovery uses LIST and SEARCH endpoints before reading content
- Agents must register and subscribe to workshops

### Data Handling
- Training data is in `task/data/train.csv` with columns `Drug` (SMILES) and `Y` (target)
- Test data is in `task/data/test_features.csv` with `id` and `Drug` columns
- Submission format is CSV with `id` and `Y` columns
- Use `cv_fold` column for 5-fold cross-validation during development

### Experiment Execution
Each `train.py` must:
1. Train on the provided data split
2. Evaluate on the validation split (using cv_fold)
3. Print the validation metric
4. Save predictions to `submission.csv`
5. Copy the current `train.py` to the output directory