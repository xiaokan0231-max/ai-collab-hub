# NeuroGolf 2026 — Project Canon

> Current home: `/Users/kanxiao/IdeaProjects/ai-collab-hub/neurogolf`
> Competition: Kaggle `neurogolf-2026`
> Metric direction: higher is better

## Goal

Build correct and compact ONNX networks for the 400 NeuroGolf ARC-style tasks.
The Hub is the coordination layer for task status, claims, deployment history,
forum conclusions, and downloadable submission packages.

## Current Artifact Policy

NeuroGolf artifacts are coordinated through the central AI Hub database, not
through ad-hoc file copies or git commits.

- `neurogolf_artifacts` is the deployment ledger.
- `neurogolf_artifact_blobs` stores deployed ONNX bytes by SHA-256.
- A task counts as solved only when Hub status reports it as solved:
  `verified_status == IS_READY`, `is_deployed == true`, `is_dummy == false`,
  and the DB blob is available.
- `neurogolf/data/working/task*.onnx` is local cache only. Do not use file
  counts to infer solved count.
- `GET /api/project_plugin/neurogolf/submission` generates `submission.zip`
  from DB blobs.
- `POST /api/project_plugin/neurogolf/deploy` verifies a candidate ONNX, writes
  the blob to DB, updates the deployment ledger, and rebuilds submission data.

## Shared Data Policy

Raw Kaggle data belongs in this shared workspace:

- `/Users/kanxiao/IdeaProjects/ai-collab-hub/neurogolf/data/raw`
- `/Users/kanxiao/IdeaProjects/ai-collab-hub/neurogolf/data/working`

Raw data is ignored by git. Restore it with the commands in `neurogolf/README.md`
or keep a local cache inside this directory. The Hub still needs raw task JSON
files and `neurogolf_utils.py` for official verification during deploy.

## Task Workflow

Per-task work does not require forum voting.

1. Check status:

   ```bash
   curl http://127.0.0.1:8000/api/project_plugin/neurogolf/status
   ```

2. Claim only unsolved tasks:

   ```bash
   curl -X POST http://127.0.0.1:8000/api/project_plugin/neurogolf/claim \
        -F task_id=task037 -F agent_name=Codex -F note="periodic tiling family"
   ```

3. Deploy a verified candidate through the Hub:

   ```bash
   python tools/deploy_neurogolf_artifact.py \
     --hub http://127.0.0.1:8000 \
     --task task037 \
     --model path/to/task037.onnx \
     --score 12.345 \
     --agent Codex
   ```

4. Download the current DB-built submission:

   ```bash
   python tools/pull_submission.py \
     --hub http://127.0.0.1:8000 \
     --out neurogolf/data/working/submission.zip
   ```

## Forum Scope

Use forum topics for family-level solution patterns, playbooks, workflow
changes, bug disputes, and milestone reports. Avoid opening new per-task topics
unless the task reveals a reusable rule or a platform issue.
