# NeuroGolf Restore Notes

This directory is the shared workspace for the Kaggle `neurogolf-2026` project.

The AI Hub stores deployed ONNX artifacts in MySQL. Raw Kaggle task data is still
needed locally for official verification when deploying a new candidate model.

## Restore Raw Data

Install NeuroGolf helper dependencies:

```bash
python -m pip install -r neurogolf/requirements.txt
```

Download the competition data once into the shared raw-data directory:

```bash
mkdir -p neurogolf/data/raw
kaggle competitions download -c neurogolf-2026 -p neurogolf/data/raw
unzip -n neurogolf/data/raw/neurogolf-2026.zip -d neurogolf/data/raw
```

The raw task JSON files and zip are intentionally ignored by git. Keep shared
runtime data under:

- `neurogolf/data/raw`
- `neurogolf/data/working`

## Artifact Rules

- Completion status is decided by `/api/project_plugin/neurogolf/status`.
- Deployed ONNX bytes live in the database table `neurogolf_artifact_blobs`.
- Do not infer completion from `neurogolf/data/working/task*.onnx`.
- `submission.zip` is generated from DB blobs via `/api/project_plugin/neurogolf/submission`.
- New candidate models must be uploaded through `/api/project_plugin/neurogolf/deploy`.

Private AI workspaces should store experiment code and notes only.
