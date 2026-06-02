"""
Dashboard server with API endpoints for running update/backtest scripts.
Usage: python web/server.py [port]
"""
from __future__ import annotations

import json
import mimetypes
import queue
import subprocess
import sys
import threading
import time
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"
SCRIPTS_DIR = ROOT / "scripts"
TEMP_DIR = ROOT / "web" / ".task-output"
TEMP_DIR.mkdir(exist_ok=True)

tasks: dict[str, dict] = {}
tasks_lock = threading.Lock()


def _run_script(script_path: Path, task_id: str, log_path: Path):
    """Run a PowerShell script, writing output to log_path."""
    try:
        with open(log_path, "w", encoding="utf-8") as f, \
             open(log_path, "a", encoding="utf-8") as fa:
            fa.write(f"=== Starting: {script_path.name} ===\n")
            fa.flush()
            proc = subprocess.Popen(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                 "-File", str(script_path)],
                cwd=str(ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=False,
            )
            # Read binary chunks and decode to avoid buffering issues
            while True:
                chunk = proc.stdout.read(4096)
                if not chunk:
                    break
                text = chunk.decode("utf-8", errors="replace")
                fa.write(text)
                fa.flush()
            proc.wait()
            fa.write(f"\n=== Done (exit code {proc.returncode}) ===\n")
            fa.flush()
    except Exception as e:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n=== Error: {e} ===\n")
    finally:
        with tasks_lock:
            t = tasks.get(task_id)
            if t:
                t["done"] = True


def _start_task(script_name: str) -> str:
    """Start a PowerShell script in background, return task_id."""
    task_id = uuid.uuid4().hex[:12]
    log_path = TEMP_DIR / f"{task_id}.log"
    with tasks_lock:
        tasks[task_id] = {"done": False, "log_path": log_path}

    script_path = SCRIPTS_DIR / script_name
    t = threading.Thread(target=_run_script, args=(script_path, task_id, log_path), daemon=True)
    t.start()
    return task_id


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0].split("#")[0]
        if path == "/api/status":
            self._send_json({"tasks": {k: {"done": v["done"]} for k, v in tasks.items()}})
        elif path.startswith("/api/progress/"):
            task_id = path.split("/")[-1]
            with tasks_lock:
                t = tasks.get(task_id)
            if t is None:
                self._send_json({"error": "task not found"}, 404)
                return
            try:
                output = t["log_path"].read_text(encoding="utf-8", errors="replace")
            except Exception:
                output = ""
            self._send_json({"done": t["done"], "text": output})
        elif path.startswith("/api/progress-json/"):
            task_id = path.split("/")[-1]
            with tasks_lock:
                t = tasks.get(task_id)
            if t is None:
                self._send_json({"error": "task not found"}, 404)
                return
            try:
                raw = t["log_path"].read_text(encoding="utf-8", errors="replace")
                lines = raw.split("\n")
            except Exception:
                lines = []
            self._send_json({"done": t["done"], "output": lines, "lines": len(lines)})
        else:
            self._serve_static()

    def do_POST(self):
        if self.path == "/api/run-update-data":
            task_id = _start_task("update_data.ps1")
            self._send_json({"task_id": task_id, "message": "update started"})
        elif self.path == "/api/run-backtest":
            task_id = _start_task("run_backtest.ps1")
            self._send_json({"task_id": task_id, "message": "backtest started"})
        elif self.path == "/api/run-full-update":
            task_id = _start_task("full_update.ps1")
            self._send_json({"task_id": task_id, "message": "full update started"})
        else:
            self._send_json({"error": "not found"}, 404)

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_static(self):
        path = self.path.split("?")[0].split("#")[0]
        if path == "/":
            path = "/index.html"
        filepath = WEB_DIR / path.lstrip("/")
        if not filepath.exists() or not filepath.is_file():
            self.send_response(404)
            self.end_headers()
            return
        content = filepath.read_bytes()
        mime, _ = mimetypes.guess_type(str(filepath))
        self.send_response(200)
        self.send_header("Content-Type", mime or "application/octet-stream")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, fmt, *args):
        pass


# Clean up old log files from previous server runs
for f in TEMP_DIR.glob("*.log"):
    try:
        f.unlink()
    except Exception:
        pass


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"Dashboard server started at http://localhost:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")


if __name__ == "__main__":
    main()
