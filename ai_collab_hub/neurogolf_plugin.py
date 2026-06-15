from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from io import BytesIO
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

try:
    from .config import load_config
    from .database import (SessionLocal, Project, Topic, Agent, AgentProjectState,
                           NeuroGolfArtifact, NeuroGolfArtifactBlob, ActivityLog,
                           KaggleSubmission)
except ImportError:
    from config import load_config
    from database import (SessionLocal, Project, Topic, Agent, AgentProjectState,
                          NeuroGolfArtifact, NeuroGolfArtifactBlob, ActivityLog,
                          KaggleSubmission)


router = APIRouter(prefix="/api/project_plugin", tags=["project-plugin"])

CONFIG = load_config()
WORKSPACE_ROOT = Path(CONFIG["workspace"]["root"]).resolve()
TASK_RE = re.compile(r"^task(\d{3})\.onnx$")
TASK_ID_RE = re.compile(r"task\s*0*(\d{1,3})", re.IGNORECASE)
SOLVED_STATUS = "IS_READY"
DUMMY_SIZE_BYTES = 868  # the placeholder template is EXACTLY 868 bytes (verified on disk)
CLAIM_EXPIRE_HOURS = 24   # 认领有效期: 超时自动可被接管, 防止崩溃 AI 死锁任务
MAX_ACTIVE_CLAIMS = 12    # 单 AI 同时认领上限 (沿用论坛 #44 批量认领的先例)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def iso(dt) -> str:
    return dt.isoformat() + "Z"


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def normalize_task_id(task_id: str) -> str:
    raw = task_id.strip().lower()
    if raw.startswith("task"):
        raw = raw[4:]
    if not raw.isdigit():
        raise HTTPException(status_code=400, detail=f"非法 task_id: {task_id!r}")
    n = int(raw)
    if not (1 <= n <= 400):
        raise HTTPException(status_code=400, detail="task_id 必须在 task001..task400 范围内。")
    return f"task{n:03d}"


def require_project(db: Session, project: str) -> Project:
    p = db.query(Project).filter(Project.name == project).first()
    if not p:
        raise HTTPException(status_code=404, detail=f"项目 '{project}' 不存在。")
    if p.name != "neurogolf":
        raise HTTPException(status_code=404, detail=f"项目 '{project}' 没有 NeuroGolf 插件。")
    return p


def shared_dir(project: str) -> Path:
    return WORKSPACE_ROOT / project


def working_dir(project: str) -> Path:
    return shared_dir(project) / "data" / "working"


def raw_dir(project: str) -> Path:
    return shared_dir(project) / "data" / "raw"


def manifest_path(project: str) -> Path:
    return working_dir(project) / "solution_manifest.json"


def archive_dir(project: str) -> Path:
    return working_dir(project) / "archive"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def is_dummy_model(path: Path) -> bool:
    # The placeholder dummies are one fixed template of EXACTLY 868 bytes.
    # Legit golfed models can be smaller (tiny = high points), so a <= size
    # heuristic would misclassify them; equality pins the actual template.
    return (not path.exists()) or path.stat().st_size == DUMMY_SIZE_BYTES


def is_dummy_blob(blob: bytes) -> bool:
    return len(blob) == DUMMY_SIZE_BYTES


def blob_uri(digest: str) -> str:
    return f"db://neurogolf_artifact_blobs/{digest}"


def store_artifact_blob(db: Session, digest: str, content: bytes) -> bool:
    pending = db.info.setdefault("neurogolf_blob_pending", set())
    if digest in pending:
        return False
    row = db.query(NeuroGolfArtifactBlob).filter(NeuroGolfArtifactBlob.sha256 == digest).first()
    if row:
        return False
    db.add(NeuroGolfArtifactBlob(
        sha256=digest,
        bytes=len(content),
        content=content,
        created_at=utcnow(),
    ))
    pending.add(digest)
    return True


def _legacy_artifact_paths(project: str, row: NeuroGolfArtifact) -> list[Path]:
    candidates: list[Path] = []
    if row.artifact_path and not row.artifact_path.startswith("db://"):
        candidates.append(Path(row.artifact_path))
    candidates.append(task_file(project, row.task_id))
    unique: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        key = str(path.expanduser())
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def artifact_payload(db: Session, project: str, row: Optional[NeuroGolfArtifact]) -> tuple[Optional[bytes], bool]:
    """Return artifact bytes from DB, importing once from legacy paths if needed.

    The DB blob is the durable source of truth. Legacy files are only a migration
    bridge so an existing workspace can seed the blob table.
    """
    if not row or not row.sha256:
        return None, False
    blob = db.query(NeuroGolfArtifactBlob).filter(NeuroGolfArtifactBlob.sha256 == row.sha256).first()
    if blob:
        return blob.content, False

    for path in _legacy_artifact_paths(project, row):
        if not path.exists() or not path.is_file():
            continue
        content = path.read_bytes()
        if sha256_bytes(content) != row.sha256:
            continue
        created = store_artifact_blob(db, row.sha256, content)
        return content, created
    return None, False


def load_manifest(project: str) -> dict:
    path = manifest_path(project)
    if not path.exists():
        return {"tasks": {}}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"读取 solution_manifest.json 失败: {exc}")
    if not isinstance(data, dict):
        raise HTTPException(status_code=500, detail="solution_manifest.json 必须是 JSON object。")
    data.setdefault("tasks", {})
    if not isinstance(data["tasks"], dict):
        raise HTTPException(status_code=500, detail="solution_manifest.json 的 tasks 字段必须是 object。")
    return data


def save_manifest(project: str, data: dict) -> None:
    path = manifest_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    tmp.replace(path)


def require_agent_member(db: Session, p: Project, agent_name: str) -> Agent:
    agent = db.query(Agent).filter(Agent.name == agent_name).first()
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found. 请先用 update 命令注册。")
    st = (db.query(AgentProjectState)
          .filter(AgentProjectState.agent_id == agent.id, AgentProjectState.project_id == p.id).first())
    if not st:
        raise HTTPException(status_code=403,
                            detail=f"'{agent_name}' 不是项目 '{p.name}' 的成员。请先执行 update --project {p.name} 注册加入。")
    return agent


def claim_expires_at(entry: dict) -> Optional[datetime]:
    try:
        ts = datetime.fromisoformat(entry["claimed_at"].rstrip("Z"))
    except (KeyError, ValueError):
        return None
    return ts + timedelta(hours=CLAIM_EXPIRE_HOURS)


def claim_is_active(entry: Optional[dict]) -> bool:
    if not entry:
        return False
    exp = claim_expires_at(entry)
    return exp is not None and datetime.utcnow() < exp


def claim_view(entry: Optional[dict]) -> Optional[dict]:
    if not entry:
        return None
    exp = claim_expires_at(entry)
    return {"agent": entry.get("agent"), "claimed_at": entry.get("claimed_at"),
            "note": entry.get("note") or "",
            "expires_at": iso(exp) if exp else None,
            "expired": not claim_is_active(entry)}


def deployed_artifacts(db: Session, project_id: int) -> dict[str, NeuroGolfArtifact]:
    rows = (db.query(NeuroGolfArtifact)
            .filter(NeuroGolfArtifact.project_id == project_id,
                    NeuroGolfArtifact.is_deployed == True)  # noqa: E712
            .all())
    return {row.task_id: row for row in rows}


def latest_forum_by_task(db: Session, project_id: int) -> dict[str, dict]:
    names = {a.id: a.name for a in db.query(Agent).all()}
    topics = (db.query(Topic)
              .filter(Topic.project_id == project_id)
              .order_by(Topic.created_at.desc())
              .all())
    # 分两轮：先记录每个 task 最新的已结案 topic，再 fallback 到最新的开放 topic
    closed: dict[str, dict] = {}
    open_: dict[str, dict] = {}
    for t in topics:
        text = "\n".join([t.title or "", t.content or "", t.conclusion or ""])
        for n in TASK_ID_RE.findall(text):
            tid = f"task{int(n):03d}"
            entry = {
                "topic_id": t.id,
                "status": "已完结" if t.closed_at is not None else "待执行" if t.claimed_by_id else "验证提案",
                "creator": names.get(t.creator_id, "Unknown"),
                "claimed_by": names.get(t.claimed_by_id) if t.claimed_by_id else None,
            }
            if t.closed_at is not None:
                if tid not in closed:
                    closed[tid] = entry
            else:
                if tid not in open_:
                    open_[tid] = entry
    # 已结案优先，没有则用开放帖
    return {**open_, **closed}


def read_task_index(project: str) -> dict[str, dict]:
    path = working_dir(project) / "task_index.csv"
    if not path.exists():
        return {}
    import csv
    rows: dict[str, dict] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            raw = row.get("task_id") or row.get("task") or row.get("id")
            if not raw:
                continue
            try:
                tid = normalize_task_id(Path(raw).stem)
            except HTTPException:
                continue
            rows[tid] = row
    return rows


def task_file(project: str, task_id: str) -> Path:
    return working_dir(project) / f"{task_id}.onnx"


def artifact_status(row: Optional[NeuroGolfArtifact], manifest_entry: Optional[dict],
                    path: Path, db_payload: Optional[bytes] = None) -> dict:
    exists = path.exists()
    dummy = is_dummy_model(path)
    if not row:
        manifest_entry = manifest_entry or {}
        manifest_verified = manifest_entry.get("verified_status") or "UNKNOWN"
        manifest_sha = manifest_entry.get("model_sha256")
        manifest_score = manifest_entry.get("deployed_score", manifest_entry.get("best_score"))
        manifest_topic = manifest_entry.get("source_topic")
        manifest_deployed = manifest_verified == SOLVED_STATUS and exists and not dummy
        return {
            "verified_status": manifest_verified,
            "score": manifest_score,
            "sha256": manifest_sha or (sha256_file(path) if exists else None),
            "bytes": path.stat().st_size if exists else 0,
            "is_deployed": manifest_deployed,
            "is_dummy": dummy,
            "artifact_available": exists and not dummy,
            "storage": "file" if exists else "missing",
            "source_topic": manifest_topic,
            "created_by": manifest_entry.get("created_by"),
            "artifact_age": None,
        }
    age = None
    if row.updated_at:
        age = (datetime.utcnow() - row.updated_at).total_seconds()
    blob_available = db_payload is not None
    return {
        "verified_status": row.verified_status,
        "score": row.score,
        "sha256": row.sha256,
        "bytes": row.bytes,
        "is_deployed": row.is_deployed,
        "is_dummy": row.is_dummy,
        "artifact_available": blob_available,
        "storage": "db" if blob_available else "missing",
        "source_topic": row.forum_topic_id,
        "created_by": row.created_by,
        "artifact_age": age,
    }


def verify_model(project: str, task_id: str, model_path: Path) -> str:
    if os.environ.get("NEUROGOLF_VERIFY_CMD"):
        cmd = os.environ["NEUROGOLF_VERIFY_CMD"].format(
            model=str(model_path),
            task=task_id,
            task_json=str(raw_dir(project) / f"{task_id}.json"),
            raw_dir=str(raw_dir(project)),
        )
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=300)
        output = (proc.stdout or "") + "\n" + (proc.stderr or "")
        if proc.returncode == 0 and ("IS READY" in output or "READY" in output):
            return SOLVED_STATUS
        raise HTTPException(status_code=422, detail=f"官方验证失败:\n{output[-4000:]}")

    utils = raw_dir(project) / "neurogolf_utils" / "neurogolf_utils.py"
    task_json = raw_dir(project) / f"{task_id}.json"
    if not utils.exists() or not task_json.exists():
        raise HTTPException(
            status_code=503,
            detail="中心机缺少 NeuroGolf raw data 或 neurogolf_utils.py，无法执行官方验证。"
        )

    script = r"""
import importlib.util, inspect, pathlib, sys
utils_path, model_path, task_json, task_id = sys.argv[1:5]
spec = importlib.util.spec_from_file_location("neurogolf_utils", utils_path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
func = None
for name in ("verify_network", "verify_model", "benchmark_network", "run_benchmark"):
    if hasattr(mod, name):
        func = getattr(mod, name)
        break
if func is None:
    raise SystemExit("No known verify function in neurogolf_utils.py")
args_list = [
    (model_path, task_json),
    (task_json, model_path),
    (pathlib.Path(model_path), pathlib.Path(task_json)),
    (pathlib.Path(task_json), pathlib.Path(model_path)),
    (model_path, int(task_id[-3:])),
    (int(task_id[-3:]), model_path),
    (model_path,),
]
last = None
for args in args_list:
    try:
        result = func(*args)
        print(result)
        raise SystemExit(0)
    except TypeError as exc:
        last = exc
        continue
raise SystemExit(f"Could not call verifier: {last}")
"""
    proc = subprocess.run(
        [sys.executable, "-c", script, str(utils), str(model_path), str(task_json), task_id],
        capture_output=True,
        text=True,
        timeout=300,
    )
    output = (proc.stdout or "") + "\n" + (proc.stderr or "")
    if proc.returncode == 0 and ("IS READY" in output or "pass" in output.lower()):
        return SOLVED_STATUS
    raise HTTPException(status_code=422, detail=f"官方验证失败:\n{output[-4000:]}")


def archive_current(project: str, task_id: str, current: Path, deployed: Optional[NeuroGolfArtifact]) -> Optional[Path]:
    if not current.exists():
        return None
    archive_dir(project).mkdir(parents=True, exist_ok=True)
    score = "unknown" if not deployed or deployed.score is None else f"{deployed.score:.3f}"
    topic = "notopic" if not deployed or deployed.forum_topic_id is None else f"t{deployed.forum_topic_id}"
    digest = sha256_file(current)[:12]
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    target = archive_dir(project) / f"{task_id}_{score}pts_{topic}_{digest}_{stamp}.onnx"
    shutil.move(str(current), str(target))
    return target


_GATE_UTILS_CACHE = {}


def _gate_real_input(project: Optional[str], task_num: Optional[int]):
    """A REAL grader-style input tensor for the task (what Kaggle actually feeds),
    or None. The all-background synthetic probe falsely fails models that
    divide-by-zero on an empty grid (e.g. task137) yet work on every real input."""
    if project is None or task_num is None:
        return None
    try:
        import importlib.util
        if project not in _GATE_UTILS_CACHE:
            utils = raw_dir(project) / "neurogolf_utils" / "neurogolf_utils.py"
            if not utils.exists():
                _GATE_UTILS_CACHE[project] = None
            else:
                spec = importlib.util.spec_from_file_location(f"ng_gate_{project}", str(utils))
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                mod._NEUROGOLF_DIR = str(raw_dir(project)) + os.sep
                _GATE_UTILS_CACHE[project] = mod
        ng = _GATE_UTILS_CACHE[project]
        if ng is None:
            return None
        ex = ng.load_examples(task_num)
        for split in ("arc-gen", "train", "test"):
            for e in ex.get(split, []):
                bench = ng.convert_to_numpy(e)
                if bench:
                    return bench["input"]
    except Exception:  # noqa: BLE001
        return None
    return None


def grader_inference_error(blob: bytes, task_num: Optional[int] = None,
                           project: Optional[str] = None) -> str:
    """Return '' if the model survives the Kaggle grader's call, else why it fails.

    The grader (neurogolf_utils.convert_to_numpy/run_network) feeds a batch=1
    one-hot float32 tensor [1,10,30,30] of a REAL example and thresholds a float
    output at 0. We replicate that with the task's real first example when
    available (falling back to a synthetic probe) — a synthetic ALL-BACKGROUND
    grid is unrepresentative and falsely fails legit models that choke on empty
    input. We require: runs, rank-4 output, channel dim == 10, numeric/bool
    dtype. Scoring is all-or-nothing, so any real violation poisons the zip.
    """
    try:
        import numpy as np  # type: ignore
        import onnxruntime as ort  # type: ignore
    except Exception as exc:  # noqa: BLE001
        return f"deps: {exc}"  # caller decides whether to treat as fatal
    try:
        opt = ort.SessionOptions()
        opt.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL
        sess = ort.InferenceSession(blob, opt, providers=["CPUExecutionProvider"])
    except Exception as exc:  # noqa: BLE001
        return f"load: {str(exc)[:80]}"
    inp = sess.get_inputs()[0]
    if inp.type != "tensor(float)":
        return f"input dtype {inp.type} (grader feeds float32)"
    x = _gate_real_input(project, task_num)
    if x is None:
        x = np.zeros((1, 10, 30, 30), dtype=np.float32)
        x[0, 0] = 1.0
    x = np.asarray(x, dtype=np.float32)
    try:
        out = sess.run(["output"], {inp.name: x})[0]
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        msg = msg.split("Status Message:")[-1].strip() if "Status" in msg else msg
        return f"infer: {msg[:80]}"
    if out.ndim != 4 or out.shape[1] != 10:
        return f"output shape {tuple(out.shape)} (need (1,10,H,W))"
    # The grader thresholds via `(out > 0.0).astype(float)`, which is dtype-
    # agnostic for numeric/bool. bool/uint8 outputs are proven safe: they ship
    # inside real scored Kaggle submissions (afr1ste 6335). Only non-numeric
    # outputs would break it. The fatal 2026-06-11 models failed on SHAPE.
    if out.dtype.kind not in "fbui":
        return f"output dtype {out.dtype} (grader cannot threshold it)"
    return ""


def _deployed_payloads(project: str, db: Session) -> tuple[list[tuple[str, bytes]], bool]:
    artifacts = deployed_artifacts(db, require_project(db, project).id)
    payloads: list[tuple[str, bytes]] = []
    missing: list[str] = []
    backfilled = False
    for i in range(1, 401):
        tid = f"task{i:03d}"
        row = artifacts.get(tid)
        if not (row and row.verified_status == SOLVED_STATUS and row.is_deployed and not row.is_dummy):
            missing.append(f"{tid}.onnx")
            continue
        content, created = artifact_payload(db, project, row)
        backfilled = backfilled or created
        if content is None or is_dummy_blob(content):
            missing.append(f"{tid}.onnx")
            continue
        payloads.append((f"{tid}.onnx", content))
    if missing:
        raise HTTPException(status_code=409, detail=f"DB 缺少 {len(missing)} 个已部署 ONNX，不能重建 submission.zip: {missing[:8]}")
    return payloads, backfilled


def build_submission_zip(project: str, db: Session) -> dict:
    payloads, backfilled = _deployed_payloads(project, db)

    try:
        import onnx  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"缺少 onnx 依赖，无法做 zip 内加载校验: {exc}")

    # Best-effort local inference probe. The official deploy verifier is the
    # authoritative gate; local onnxruntime can lag Kaggle and report
    # NOT_IMPLEMENTED for models that are already accepted by the competition.
    gate_warnings: list[str] = []
    for name, content in payloads:
        task_num = int(name[4:7])
        err = grader_inference_error(content, task_num=task_num, project=project)
        if err.startswith("deps:"):
            gate_warnings.append(f"{name}: {err}")
            break
        if err:
            gate_warnings.append(f"{name}: {err}")

    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, content in payloads:
            zf.writestr(name, content)
    content = buf.getvalue()

    bad: list[str] = []
    with zipfile.ZipFile(BytesIO(content), "r") as zf:
        for name in zf.namelist():
            try:
                onnx.load_model_from_string(zf.read(name))
            except Exception as exc:
                bad.append(f"{name}: {exc}")
    if bad:
        raise HTTPException(status_code=422, detail=f"zip 内模型加载失败: {bad[:5]}")
    return {
        "content": content,
        "zip": "db://neurogolf/submission.zip",
        "checked": 400,
        "size": len(content),
        "backfilled": backfilled,
        "gate_warning_count": len(gate_warnings),
        "gate_warnings": gate_warnings[:8],
    }


def rebuild_submission_zip(project: str, db: Session) -> dict:
    info = build_submission_zip(project, db)
    return {k: v for k, v in info.items() if k != "content"}


def ensure_submission_inputs(project: str, candidate_task: str, db: Session) -> bool:
    artifacts = deployed_artifacts(db, require_project(db, project).id)
    missing = [
        f"task{i:03d}.onnx"
        for i in range(1, 401)
        if f"task{i:03d}" != candidate_task and not (
            (row := artifacts.get(f"task{i:03d}"))
            and row.verified_status == SOLVED_STATUS
            and row.is_deployed
            and not row.is_dummy
        )
    ]
    if missing:
        raise HTTPException(
            status_code=409,
            detail=f"DB 缺少 {len(missing)} 个既有 ONNX 台账，部署后无法重建 submission.zip: {missing[:8]}"
        )
    backfilled = False
    for i in range(1, 401):
        tid = f"task{i:03d}"
        if tid == candidate_task:
            continue
        content, created = artifact_payload(db, project, artifacts[tid])
        backfilled = backfilled or created
        if content is None or is_dummy_blob(content):
            raise HTTPException(
                status_code=409,
                detail=f"DB 缺少 {tid}.onnx 模型内容，部署后无法重建 submission.zip。"
            )
    return backfilled


@router.get("/{project}/status")
def neurogolf_status(project: str, db: Session = Depends(get_db)):
    p = require_project(db, project)
    artifacts = deployed_artifacts(db, p.id)
    forum = latest_forum_by_task(db, p.id)
    task_index = read_task_index(project)
    manifest = load_manifest(project)
    manifest_tasks = manifest.get("tasks", {})
    claims = manifest.get("claims", {})
    tasks = []
    counts = {"solved": 0, "claimed": 0, "open": 0}
    backfilled = False
    for i in range(1, 401):
        tid = f"task{i:03d}"
        path = task_file(project, tid)
        row = artifacts.get(tid)
        payload, created_blob = artifact_payload(db, project, row)
        backfilled = backfilled or created_blob
        art = artifact_status(row, manifest_tasks.get(tid), path, payload)
        f = forum.get(tid)
        cl = claims.get(tid)
        idx = task_index.get(tid, {})
        # 状态只看 DB artifact 台账 + DB blob + 认领台账, 论坛不参与推导:
        #   solved  = 已验证部署台账 + ONNX bytes 已入库
        #   claimed = 有未过期的直接认领
        #   open    = 其余
        ledger_verified = (art["verified_status"] == SOLVED_STATUS and art["is_deployed"]
                           and not art["is_dummy"])
        solved = ledger_verified and art["artifact_available"]
        if solved:
            card_status = "solved"; counts["solved"] += 1
        elif claim_is_active(cl):
            card_status = "claimed"; counts["claimed"] += 1
        else:
            card_status = "open"; counts["open"] += 1
        tasks.append({
            "id": tid,
            "rule_family": idx.get("rule_family") or idx.get("shape_category") or "UNKNOWN",
            "shape": idx.get("shape") or idx.get("notes") or "VARIABLE",
            "onnx_exists": art["artifact_available"],
            "onnx_size": art["bytes"],
            "file_exists": path.exists(),
            "storage": art["storage"],
            "is_dummy": art["is_dummy"],
            "status": card_status,
            "solved": solved,
            "ledger_verified": ledger_verified,
            "artifact_available": art["artifact_available"],
            "verified_status": art["verified_status"],
            "best_score": art["score"],
            "deployed_score": art["score"] if art["is_deployed"] else None,
            "sha256": art["sha256"],
            "sha256_short": art["sha256"][:8] if art["sha256"] else None,
            "source_topic": art["source_topic"],
            "created_by": art["created_by"],
            "artifact_age": art["artifact_age"],
            "claim": claim_view(cl),
            "forum": f,
        })
    if backfilled:
        db.commit()
    return {"tasks": tasks, "counts": counts, "manifest": str(manifest_path(project))}


@router.post("/{project}/claim")
def claim_task(project: str,
               task_id: str = Form(...),
               agent_name: str = Form(...),
               note: Optional[str] = Form(None),
               db: Session = Depends(get_db)):
    """直接认领任务: 不发帖、不投票, 打上排他 flag 防止重复劳动。24h 过期, 单 AI 上限 12 个。"""
    p = require_project(db, project)
    tid = normalize_task_id(task_id)
    agent = require_agent_member(db, p, agent_name)

    row = (db.query(NeuroGolfArtifact)
           .filter(NeuroGolfArtifact.project_id == p.id,
                   NeuroGolfArtifact.task_id == tid,
                   NeuroGolfArtifact.is_deployed == True)  # noqa: E712
           .first())
    payload, created_blob = artifact_payload(db, project, row)
    if created_blob:
        db.commit()
    if row and row.verified_status == SOLVED_STATUS and row.is_deployed and not row.is_dummy and payload is not None:
        ledger = (f"当前最高 {row.score} 分, by {row.created_by or '?'}"
                  if row and row.verified_status == SOLVED_STATUS
                  else "台账未过账")
        raise HTTPException(status_code=409,
                            detail=f"{tid} 已完成 ({ledger})。挑战无需认领: 做出更优模型直接走 deploy API, "
                                   f"更高分自动顶替。先查历史避免重复尝试: "
                                   f"GET /api/project_plugin/{project}/history?task_id={tid}")

    manifest = load_manifest(project)
    claims = manifest.setdefault("claims", {})
    entry = claims.get(tid)
    if entry and entry.get("agent") != agent_name and claim_is_active(entry):
        cv = claim_view(entry)
        raise HTTPException(status_code=409,
                            detail=f"{tid} 已被 {cv['agent']} 认领 (有效至 {cv['expires_at']})。"
                                   f"请换别的任务; 若对方确已放弃, 等过期后可接管, 或请其 release。")

    active_mine = [t for t, e in claims.items()
                   if e.get("agent") == agent_name and claim_is_active(e) and t != tid]
    if len(active_mine) >= MAX_ACTIVE_CLAIMS:
        raise HTTPException(status_code=409,
                            detail=f"你已有 {len(active_mine)} 个进行中认领 (上限 {MAX_ACTIVE_CLAIMS})。"
                                   f"先 deploy 交付或 release 释放部分任务: {sorted(active_mine)[:12]}")

    takeover = bool(entry and entry.get("agent") != agent_name)
    now = utcnow()
    claims[tid] = {"agent": agent_name, "claimed_at": iso(now), "note": (note or "").strip()}
    save_manifest(project, manifest)
    desc = f"直接认领了 {tid}" + (f" (接管过期认领 {entry.get('agent')})" if takeover else "")
    if note:
        desc += f": {note}"
    db.add(ActivityLog(project_id=p.id, agent_id=agent.id, action_type="task_claim", description=desc))
    db.commit()
    return {"status": "success", "task_id": tid, "agent": agent_name,
            "expires_at": iso(now + timedelta(hours=CLAIM_EXPIRE_HOURS)),
            "active_claims": sorted(active_mine + [tid])}


@router.post("/{project}/release")
def release_task(project: str,
                 task_id: str = Form(...),
                 agent_name: str = Form(...),
                 reason: Optional[str] = Form(None),
                 db: Session = Depends(get_db)):
    """释放认领: 放弃任务时退回公共池 (带原因留痕); 过期认领任何成员可清理。"""
    p = require_project(db, project)
    tid = normalize_task_id(task_id)
    agent = require_agent_member(db, p, agent_name)

    manifest = load_manifest(project)
    claims = manifest.setdefault("claims", {})
    entry = claims.get(tid)
    if not entry:
        raise HTTPException(status_code=404, detail=f"{tid} 当前没有认领记录, 无需释放。")
    if entry.get("agent") != agent_name and claim_is_active(entry):
        raise HTTPException(status_code=403,
                            detail=f"{tid} 的认领属于 {entry.get('agent')} 且未过期, 只能由本人释放。")

    claims.pop(tid, None)
    save_manifest(project, manifest)
    owner = entry.get("agent")
    desc = (f"释放了 {tid} 的认领" if owner == agent_name
            else f"清理了 {owner} 在 {tid} 的过期认领")
    if reason:
        desc += f": {reason}"
    db.add(ActivityLog(project_id=p.id, agent_id=agent.id, action_type="task_release", description=desc))
    db.commit()
    return {"status": "success", "task_id": tid, "released_from": owner}


@router.get("/{project}/history")
def task_history(project: str, task_id: str, db: Session = Depends(get_db)):
    """单任务台账: 全部部署/挑战记录(含被拒尝试)、当前最高分、认领状态、归档文件。"""
    p = require_project(db, project)
    tid = normalize_task_id(task_id)

    rows = (db.query(NeuroGolfArtifact)
            .filter(NeuroGolfArtifact.project_id == p.id, NeuroGolfArtifact.task_id == tid)
            .order_by(NeuroGolfArtifact.created_at.asc())
            .all())
    attempts = []
    backfilled = False
    for r in rows:
        payload, created_blob = artifact_payload(db, project, r)
        backfilled = backfilled or created_blob
        attempts.append({
            "at": iso(r.created_at),
            "by": r.created_by,
            "score": r.score,
            "verified_status": r.verified_status,
            "deployed": r.is_deployed,
            "outcome": ("当前部署" if r.is_deployed else
                        "挑战被拒(低分)" if r.verified_status == "REJECTED_LOW_SCORE" else "已被顶替"),
            "sha256_short": r.sha256[:8] if r.sha256 else None,
            "source_topic": r.forum_topic_id,
            "artifact_available": payload is not None,
        })
    if backfilled:
        db.commit()
    scores = [r.score for r in rows if r.score is not None]
    current = next((a for a in attempts if a["deployed"]), None)

    manifest = load_manifest(project)
    archives = sorted(f.name for f in archive_dir(project).glob(f"{tid}_*.onnx")) \
        if archive_dir(project).exists() else []
    return {
        "task_id": tid,
        "best_score": max(scores) if scores else None,
        "current": current,
        "attempts": attempts,
        "claim": claim_view(manifest.get("claims", {}).get(tid)),
        "archives": archives,
    }


@router.get("/{project}/artifact/{filename}")
def download_artifact(project: str, filename: str, db: Session = Depends(get_db)):
    p = require_project(db, project)
    if filename != "submission.zip" and not TASK_RE.match(filename):
        raise HTTPException(status_code=400, detail="只允许下载 submission.zip 或 taskXXX.onnx。")
    if filename == "submission.zip":
        info = build_submission_zip(project, db)
        if info.get("backfilled"):
            db.commit()
        return Response(
            content=info["content"],
            media_type="application/zip",
            headers={"Content-Disposition": 'attachment; filename="submission.zip"'},
        )

    tid = normalize_task_id(filename[:-5])
    row = (db.query(NeuroGolfArtifact)
           .filter(NeuroGolfArtifact.project_id == p.id,
                   NeuroGolfArtifact.task_id == tid,
                   NeuroGolfArtifact.is_deployed == True)  # noqa: E712
           .first())
    payload, created_blob = artifact_payload(db, project, row)
    if created_blob:
        db.commit()
    if payload is None:
        raise HTTPException(status_code=404, detail=f"artifact 不存在: {filename}")
    return Response(
        content=payload,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{project}/submission")
def download_submission(project: str, db: Session = Depends(get_db)):
    require_project(db, project)
    return download_artifact(project, "submission.zip", db)


@router.post("/{project}/deploy")
async def deploy_artifact(
    project: str,
    file: UploadFile = File(...),
    task_id: str = Form(...),
    score: float = Form(...),
    forum_topic_id: Optional[int] = Form(None),
    agent_name: Optional[str] = Form(None),
    allow_regression: bool = Form(False),
    db: Session = Depends(get_db),
):
    p = require_project(db, project)
    tid = normalize_task_id(task_id)
    expected_name = f"{tid}.onnx"
    if file.filename and Path(file.filename).name != expected_name:
        raise HTTPException(status_code=400, detail=f"上传文件名必须是 {expected_name}。")

    with tempfile.TemporaryDirectory() as tmpdir:
        candidate = Path(tmpdir) / expected_name
        with candidate.open("wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)

        content = candidate.read_bytes()
        if is_dummy_blob(content):
            raise HTTPException(status_code=422, detail="拒绝部署 dummy/空模型。")
        verified_status = verify_model(project, tid, candidate)
        digest = sha256_bytes(content)
        size = len(content)
        store_artifact_blob(db, digest, content)

        current = (db.query(NeuroGolfArtifact)
                   .filter(NeuroGolfArtifact.project_id == p.id,
                           NeuroGolfArtifact.task_id == tid,
                           NeuroGolfArtifact.is_deployed == True)  # noqa: E712
                   .first())
        historical_scores = [
            r.score for r in db.query(NeuroGolfArtifact)
            .filter(NeuroGolfArtifact.project_id == p.id,
                    NeuroGolfArtifact.task_id == tid,
                    NeuroGolfArtifact.score != None)  # noqa: E711
            .all()
        ]
        previous_best = max(historical_scores) if historical_scores else None
        if previous_best is not None and score < previous_best and not allow_regression:
            # 验证已通过但分数不够: 把失败的挑战也记录在案, 后人查 history 不再重蹈覆辙
            db.add(NeuroGolfArtifact(
                project_id=p.id, task_id=tid, score=score, verified_status="REJECTED_LOW_SCORE",
                sha256=digest, bytes=size, forum_topic_id=forum_topic_id, created_by=agent_name,
                artifact_path=blob_uri(digest), is_deployed=False, is_dummy=False,
                created_at=utcnow(), updated_at=utcnow()))
            db.add(ActivityLog(project_id=p.id, agent_id=None, action_type="artifact_reject",
                               topic_id=forum_topic_id,
                               description=f"{tid} 挑战被拒: {score:.3f} < 历史最佳 {previous_best:.3f}"
                                           f" (by {agent_name or '?'}), 尝试已记录"))
            db.commit()
            raise HTTPException(status_code=409,
                                detail=f"拒绝低分覆盖: {score:.3f} < 历史部署 {previous_best:.3f}。"
                                       f"本次尝试已记录, 历史: GET /api/project_plugin/{project}/history?task_id={tid}")
        ensure_submission_inputs(project, tid, db)

        archive_path = None
        if current:
            current.is_deployed = False
            current.updated_at = utcnow()

        row = NeuroGolfArtifact(
            project_id=p.id,
            task_id=tid,
            score=score,
            verified_status=verified_status,
            sha256=digest,
            bytes=size,
            forum_topic_id=forum_topic_id,
            created_by=agent_name,
            artifact_path=blob_uri(digest),
            is_deployed=True,
            is_dummy=False,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        db.add(row)
        db.flush()

        manifest = load_manifest(project)
        old_manifest_entry = manifest["tasks"].get(tid)
        # 部署成功 = 任务交付, 自动释放认领 (rollback 时恢复)
        old_claim = manifest.get("claims", {}).pop(tid, None)
        manifest_best = max(previous_best, score) if previous_best is not None else score
        manifest["tasks"][tid] = {
            "best_score": manifest_best,
            "deployed_score": score,
            "verified_status": verified_status,
            "source_topic": forum_topic_id,
            "created_by": agent_name,
            "model_sha256": digest,
            "model_path": blob_uri(digest),
            "updated_at": datetime.utcnow().isoformat() + "Z",
        }
        save_manifest(project, manifest)
        try:
            zip_info = rebuild_submission_zip(project, db)
        except HTTPException:
            # 回滚 manifest，恢复部署前的状态
            if old_manifest_entry is None:
                manifest["tasks"].pop(tid, None)
            else:
                manifest["tasks"][tid] = old_manifest_entry
            if old_claim is not None:
                manifest.setdefault("claims", {})[tid] = old_claim
            save_manifest(project, manifest)
            raise
        db.add(ActivityLog(project_id=p.id, agent_id=None, action_type="artifact_deploy",
                           topic_id=forum_topic_id,
                           description=f"{tid} 部署成功: score={score}, sha256={digest[:8]}"))
        db.commit()
        db.refresh(row)
        return {
            "status": "success",
            "artifact_id": row.id,
            "task_id": tid,
            "score": score,
            "verified_status": verified_status,
            "sha256": digest,
            "bytes": size,
            "archived": str(archive_path) if archive_path else None,
            "submission": zip_info,
        }


KAGGLE_COMPETITION = "neurogolf-2026"


def _count_solved(project: str, db: Session) -> tuple[int, bool]:
    p = require_project(db, project)
    artifacts = deployed_artifacts(db, p.id)
    count = 0
    backfilled = False
    for i in range(1, 401):
        row = artifacts.get(f"task{i:03d}")
        payload, created_blob = artifact_payload(db, project, row)
        backfilled = backfilled or created_blob
        if row and row.verified_status == SOLVED_STATUS and row.is_deployed and not row.is_dummy and payload is not None:
            count += 1
    return count, backfilled


def _fetch_kaggle_score(target_dt: Optional[datetime] = None) -> dict:
    """Query kaggle submissions list. If target_dt given, match the submission closest in time."""
    try:
        proc = subprocess.run(
            ["kaggle", "competitions", "submissions", "-c", KAGGLE_COMPETITION, "--csv"],
            capture_output=True, text=True, timeout=30,
        )
        if proc.returncode != 0:
            return {}
        import csv as _csv, io as _io
        rows = list(_csv.DictReader(_io.StringIO(proc.stdout)))
        if not rows:
            return {}

        def parse_dt(s: str) -> Optional[datetime]:
            try:
                return datetime.fromisoformat(s.replace(" ", "T").split(".")[0])
            except Exception:
                return None

        if target_dt is not None:
            matched = min(
                rows,
                key=lambda r: abs(
                    ((parse_dt(r.get("date", "")) or datetime.min) - target_dt).total_seconds()
                ) if parse_dt(r.get("date", "")) else float("inf"),
            )
        else:
            matched = rows[0]

        score_raw = (matched.get("publicScore") or matched.get("public_score") or "").strip()
        raw_status = (matched.get("status") or "pending").lower()
        if "complete" in raw_status:
            status = "complete"
        elif "error" in raw_status or "fail" in raw_status:
            status = "error"
        else:
            status = "pending"
        return {
            "status": status,
            "public_score": float(score_raw) if score_raw else None,
        }
    except Exception:
        return {}


def _fetch_kaggle_rank() -> dict:
    """Download full leaderboard zip and find our rank by username."""
    try:
        kaggle_json = Path.home() / ".kaggle" / "kaggle.json"
        if not kaggle_json.exists():
            return {}
        with kaggle_json.open() as f:
            username = json.load(f).get("username", "")
        if not username:
            return {}
        import tempfile, zipfile, csv as _csv, io as _io
        with tempfile.TemporaryDirectory() as tmpdir:
            proc = subprocess.run(
                ["kaggle", "competitions", "leaderboard", "-c", KAGGLE_COMPETITION,
                 "--download", "--path", tmpdir],
                capture_output=True, text=True, timeout=60,
            )
            if proc.returncode != 0:
                return {}
            zips = list(Path(tmpdir).glob("*.zip"))
            if not zips:
                return {}
            with zipfile.ZipFile(zips[0]) as zf:
                csvname = next((n for n in zf.namelist() if n.endswith(".csv")), None)
                if not csvname:
                    return {}
                rows = list(_csv.DictReader(_io.StringIO(zf.read(csvname).decode("utf-8-sig"))))
            total = len(rows)
            for row in rows:
                members = row.get("TeamMemberUserNames", "")
                if username.lower() in members.lower():
                    rank_raw = row.get("Rank") or row.get("﻿Rank") or ""
                    return {
                        "rank": int(rank_raw) if rank_raw.isdigit() else None,
                        "total_teams": total,
                        "team_name": row.get("TeamName", ""),
                        "lb_score": float(row["Score"]) if row.get("Score") else None,
                    }
        return {"total_teams": total}
    except Exception:
        return {}


@router.post("/{project}/submit")
def submit_kaggle(project: str,
                  message: str = Form("NeuroGolf Hub submission"),
                  submitted_by: str = Form("human"),
                  db: Session = Depends(get_db)):
    p = require_project(db, project)
    zip_info = build_submission_zip(project, db)
    solved_count, count_backfilled = _count_solved(project, db)
    if zip_info.get("backfilled") or count_backfilled:
        db.commit()
    refs_before = _kaggle_submission_refs()
    with tempfile.NamedTemporaryFile(prefix="neurogolf_submission_", suffix=".zip") as tmp:
        tmp.write(zip_info["content"])
        tmp.flush()
        proc = subprocess.run(
            ["kaggle", "competitions", "submit", "-c", KAGGLE_COMPETITION,
             "-f", tmp.name, "-m", message],
            capture_output=True, text=True, timeout=300,
        )
    # The CLI can exit non-zero even after the upload lands (transient), so we
    # trust Kaggle's submission list, not the return code: succeed iff a NEW
    # submission ref appeared. This makes the record-keeping authoritative.
    refs_after = _kaggle_submission_refs()
    new_refs = refs_after - refs_before
    if not new_refs:
        raise HTTPException(status_code=500,
                            detail=("kaggle submit 未产生新提交记录。\n" + proc.stdout + "\n" + proc.stderr)[-4000:])

    # sync the full list into the DB (creates the new row with its kaggle_ref)
    _sync_kaggle_submissions(db, p.id, default_solved=solved_count,
                             default_by=submitted_by, override_msg={r: message for r in new_refs})
    sub = (db.query(KaggleSubmission)
           .filter(KaggleSubmission.project_id == p.id,
                   KaggleSubmission.kaggle_ref.in_(list(new_refs)))
           .order_by(KaggleSubmission.submitted_at.desc()).first())
    return {
        "id": sub.id, "kaggle_ref": sub.kaggle_ref, "status": sub.status,
        "public_score": sub.public_score, "solved_count": sub.solved_count,
        "submitted_at": iso(sub.submitted_at),
    }


def _kaggle_submission_refs() -> set:
    """Set of all current Kaggle submission ids for the competition (empty on error)."""
    try:
        proc = subprocess.run(
            ["kaggle", "competitions", "submissions", "-c", KAGGLE_COMPETITION, "--csv"],
            capture_output=True, text=True, timeout=30)
        if proc.returncode != 0:
            return set()
        import csv as _csv, io as _io
        return {(r.get("ref") or "").strip() for r in _csv.DictReader(_io.StringIO(proc.stdout))
                if (r.get("ref") or "").strip()}
    except Exception:  # noqa: BLE001
        return set()


def _sync_kaggle_submissions(db: Session, project_id: int, default_solved=None,
                             default_by="kaggle-sync", override_msg=None) -> dict:
    """Reconcile the DB with Kaggle's actual submission list (idempotent).

    Keyed by kaggle_ref. A Kaggle submission with no matching ref adopts the
    closest-in-time ref-less local row (within 30 min) — folding in rows made
    before kaggle_ref existed or out-of-band — otherwise inserts a new row.
    """
    import csv as _csv, io as _io
    override_msg = override_msg or {}
    try:
        proc = subprocess.run(
            ["kaggle", "competitions", "submissions", "-c", KAGGLE_COMPETITION, "--csv"],
            capture_output=True, text=True, timeout=30)
        rows = list(_csv.DictReader(_io.StringIO(proc.stdout))) if proc.returncode == 0 else []
    except Exception:  # noqa: BLE001
        rows = []

    existing = db.query(KaggleSubmission).filter(KaggleSubmission.project_id == project_id).all()
    by_ref = {r.kaggle_ref: r for r in existing if r.kaggle_ref}
    refless = [r for r in existing if not r.kaggle_ref]

    def parse_dt(s):
        try:
            return datetime.fromisoformat((s or "").replace(" ", "T").split(".")[0])
        except Exception:  # noqa: BLE001
            return None

    created = adopted = updated = 0
    for kr in rows:
        ref = (kr.get("ref") or "").strip()
        if not ref:
            continue
        score_raw = (kr.get("publicScore") or "").strip()
        score = float(score_raw) if score_raw else None
        raw_status = (kr.get("status") or "pending").lower()
        status = "complete" if "complete" in raw_status else "error" if ("error" in raw_status or "fail" in raw_status) else "pending"
        dt = parse_dt(kr.get("date", ""))
        desc = (kr.get("description") or "")[:500]
        row = by_ref.get(ref)
        if row is None:
            cand = None
            if dt and refless:
                cand = min(refless, key=lambda r: abs(((r.submitted_at or datetime.min) - dt).total_seconds()))
                if abs(((cand.submitted_at or datetime.min) - dt).total_seconds()) > 1800:
                    cand = None
            if cand is not None:
                row = cand; refless.remove(cand); adopted += 1
            else:
                row = KaggleSubmission(project_id=project_id, submitted_at=dt or utcnow(),
                                       solved_count=default_solved, submitted_by=default_by)
                db.add(row); created += 1
            row.kaggle_ref = ref
        if score is not None:
            row.public_score = score
        row.status = status
        if dt:
            row.submitted_at = dt
        row.message = override_msg.get(ref) or row.message or desc
        if row.solved_count is None and default_solved is not None:
            row.solved_count = default_solved
        updated += 1
    db.commit()
    return {"created": created, "adopted": adopted, "synced": updated}


@router.post("/{project}/reconcile_submissions")
def reconcile_submissions(project: str, db: Session = Depends(get_db)):
    """Self-heal: pull Kaggle's submission list and upsert any missing/changed
    rows (idempotent). Use after an out-of-band CLI submit or to refresh scores."""
    p = require_project(db, project)
    return _sync_kaggle_submissions(db, p.id)


@router.get("/{project}/kaggle_submissions")
def get_kaggle_submissions(project: str, db: Session = Depends(get_db)):
    p = require_project(db, project)
    rows = (db.query(KaggleSubmission)
            .filter(KaggleSubmission.project_id == p.id)
            .order_by(KaggleSubmission.submitted_at.desc())
            .limit(30)
            .all())
    return {"submissions": [{
        "id": r.id,
        "kaggle_ref": r.kaggle_ref,
        "submitted_at": iso(r.submitted_at),
        "message": r.message,
        "public_score": r.public_score,
        "rank": r.rank,
        "total_teams": r.total_teams,
        "status": r.status,
        "solved_count": r.solved_count,
        "submitted_by": r.submitted_by,
    } for r in rows]}


@router.post("/{project}/kaggle_submissions/{sub_id}/refresh")
def refresh_kaggle_score(project: str, sub_id: int, db: Session = Depends(get_db)):
    """Poll Kaggle for updated score and rank on a pending submission."""
    p = require_project(db, project)
    sub = db.query(KaggleSubmission).filter(
        KaggleSubmission.id == sub_id, KaggleSubmission.project_id == p.id
    ).first()
    if not sub:
        raise HTTPException(status_code=404, detail=f"提交记录 #{sub_id} 不存在。")

    # 按提交时间匹配 Kaggle 对应记录，避免拿错其他提交的分数
    score_data = _fetch_kaggle_score(target_dt=sub.submitted_at)
    if score_data.get("public_score") is not None:
        sub.public_score = score_data["public_score"]
    if score_data.get("status"):
        sub.status = score_data["status"]

    # 排名基于当前榜单最佳分（与哪条提交无关）
    rank_data = _fetch_kaggle_rank()
    if rank_data.get("rank") is not None:
        sub.rank = rank_data["rank"]
    if rank_data.get("total_teams"):
        sub.total_teams = rank_data["total_teams"]
    # 不用 lb_score 覆盖 public_score：两者含义不同

    db.commit()
    db.refresh(sub)
    return {
        "id": sub.id,
        "public_score": sub.public_score,
        "rank": sub.rank,
        "total_teams": sub.total_teams,
        "status": sub.status,
    }
