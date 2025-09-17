#!/usr/bin/env python3
import os
import json
import uuid
import time
import threading
import subprocess
from pathlib import Path
from typing import Dict, Any, List

from flask import Flask, request, send_file, jsonify, send_from_directory

APP_ROOT = Path(__file__).resolve().parent
WEB_DIR = APP_ROOT / "web"
OUT_ROOT = APP_ROOT / "output"
AUDIT_LOG = APP_ROOT / "audit-log.jsonl"

app = Flask(__name__, static_folder=None)
OUT_ROOT.mkdir(exist_ok=True)

class Job:
    def __init__(self, job_id: str, tool: str, args: Dict[str, Any], token_masked: str):
        self.job_id = job_id
        self.tool = tool
        self.args = args
        self.token_masked = token_masked
        self.created_ts = time.time()
        self.started_ts = None
        self.ended_ts = None
        self.status = "queued"
        self.progress = 0
        self.message = "Queued"
        self.log: List[str] = []
        self.output_files: List[str] = []
        self.proc: subprocess.Popen | None = None
        self.out_dir = OUT_ROOT / job_id
        self.out_dir.mkdir(parents=True, exist_ok=True)

JOBS: Dict[str, Job] = {}
LOG_LIMIT = 400

def append_audit(entry: Dict[str, Any]):
    AUDIT_LOG.parent.mkdir(exist_ok=True, parents=True)
    with AUDIT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

def mask_token(token: str) -> str:
    if not token:
        return ""
    if len(token) <= 8:
        return "*" * len(token)
    return token[:4] + "*" * (len(token) - 8) + token[-4:]

@app.get("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")

@app.get("/web/<path:filename>")
def static_files(filename):
    return send_from_directory(WEB_DIR, filename)

@app.get("/api/audit")
def api_audit():
    lines = []
    if AUDIT_LOG.exists():
        with AUDIT_LOG.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    lines.append(json.loads(line))
    return jsonify(lines[-100:])

@app.post("/api/extract")
def api_extract():
    data = request.get_json(force=True)
    tool_type = data.get("type")
    token = (data.get("token") or "").strip()
    args = data.get("args") or {}

    if tool_type not in {"file-commit-history", "pull-request-extractor"}:
        return jsonify({"error": "Invalid 'type'"}), 400
    if not token:
        return jsonify({"error": "GitHub token is required"}), 400

    job_id = uuid.uuid4().hex[:12]
    job = Job(job_id, tool_type, args, mask_token(token))
    JOBS[job_id] = job

    if tool_type == "file-commit-history":
        script = str(APP_ROOT / "file-commit-history.py")
        base_cmd = ["python", "-u", script, "--output-dir", str(job.out_dir),
                    "--emit-progress", "--audit-log", str(job.out_dir / "script-audit.jsonl")]
        arg_map = {
            "org": "--org", "repos": "--repos", "file_path": "--file-path",
            "since": "--since", "until": "--until", "sha": "--sha", "verbose": "--verbose",
        }
    else:
        script = str(APP_ROOT / "pull-request-extractor.py")
        base_cmd = ["python", "-u", script, "--output-dir", str(job.out_dir),
                    "--emit-progress", "--audit-log", str(job.out_dir / "script-audit.jsonl")]
        arg_map = {
            "org": "--org", "repos": "--repos", "since": "--since", "until": "--until",
            "state": "--state", "merged_only": "--merged-only", "verbose": "--verbose",
        }

    cmd = list(base_cmd)

    # repos: support comma/space list
    repos = (args.get("repos") or "").strip()
    if repos:
        parts = [p for p in repos.replace(",", " ").split() if p]
        if parts:
            cmd.append(arg_map["repos"])
            cmd.extend(parts)

    for key, flag in arg_map.items():
        if key == "repos":
            continue
        val = args.get(key)
        if val is None or val == "":
            continue
        if isinstance(val, bool):
            if key in ("verbose", "merged_only"):
                if val:
                    cmd.append(flag)
                else:
                    if key == "merged_only":
                        cmd.append("--no-merged-only")
            continue
        cmd.extend([flag, str(val)])

    cmd.extend(["--token", token])

    # For visibility in audit (mask token)
    cmd_preview = [c if c != token else "[TOKEN]" for c in cmd]
    append_audit({
        "ts": time.time(), "job_id": job_id, "tool": job.tool,
        "args": job.args, "token_masked": job.token_masked,
        "status": "started", "cmd_preview": cmd_preview
    })

    t = threading.Thread(target=run_job, args=(job_id, cmd), daemon=True)
    t.start()

    return jsonify({"job_id": job_id})

def run_job(job_id: str, cmd: List[str]):
    job = JOBS[job_id]
    job.status = "running"
    job.started_ts = time.time()
    job.message = "Starting..."
    job.progress = 1

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    try:
        job.proc = subprocess.Popen(
            cmd,
            cwd=str(APP_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,            # line-buffered at the OS pipe layer
            universal_newlines=True,
            env=env,
        )
        assert job.proc.stdout is not None
        for line in job.proc.stdout:
            line = line.rstrip("\n")
            if not line:
                continue
            job.log.append(line)
            if len(job.log) > LOG_LIMIT:
                job.log = job.log[-LOG_LIMIT:]

            if line.startswith("PROGRESS "):
                try:
                    payload = json.loads(line[len("PROGRESS "):].strip())
                    job.progress = max(0, min(100, int(payload.get("pct", job.progress))))
                    job.message = payload.get("msg", job.message) or job.message
                except Exception:
                    pass

            if line.startswith("OUTPUT_CSV "):
                p = line[len("OUTPUT_CSV "):].strip().strip('"')
                fp = (APP_ROOT / p).resolve() if not Path(p).is_absolute() else Path(p)
                if fp.exists() and fp.suffix.lower() == ".csv":
                    try:
                        rel = fp.relative_to(job.out_dir)
                        job.output_files.append(str(rel))
                    except Exception:
                        job.output_files.append(str(fp))

        ret = job.proc.wait()
        job.ended_ts = time.time()
        if ret == 0:
            job.status = "succeeded"
            job.progress = 100
            job.message = "Done."
        else:
            job.status = "failed"
            job.message = f"Exited with code {ret}"
    except Exception as e:
        job.status = "failed"
        job.message = f"Exception: {e}"
        job.ended_ts = time.time()

    append_audit({
        "ts": time.time(),
        "job_id": job_id,
        "tool": job.tool,
        "args": job.args,
        "token_masked": job.token_masked,
        "status": job.status,
        "duration_sec": (job.ended_ts or time.time()) - (job.started_ts or time.time()),
        "progress": job.progress,
        "outputs": job.output_files,
        "last_message": job.message,
    })

@app.get("/api/status/<job_id>")
def api_status(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        return jsonify({"error": "Unknown job_id"}), 404
    return jsonify({
        "job_id": job.job_id, "tool": job.tool, "status": job.status,
        "progress": job.progress, "message": job.message,
        "log": job.log[-LOG_LIMIT:], "outputs": job.output_files,
    })

@app.get("/api/download/<job_id>/<path:filename>")
def api_download(job_id: str, filename: str):
    job = JOBS.get(job_id)
    if not job:
        return jsonify({"error": "Unknown job_id"}), 404
    path = job.out_dir / filename
    if not path.exists():
        return jsonify({"error": "File not found"}), 404
    return send_file(path, as_attachment=True, download_name=path.name)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="127.0.0.1", port=port, debug=True, threaded=True)
