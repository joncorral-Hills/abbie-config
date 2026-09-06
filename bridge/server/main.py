import os
import time
import json
import uuid
import yaml
from collections import deque
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, Request, HTTPException, Depends, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bridge")

app = FastAPI(title="Hermes Bridge")

START_TIME = time.time()
API_KEY = os.environ.get("BRIDGE_API_KEY")
HERMES_DIR = Path.home() / ".hermes"
BRIDGE_DIR = HERMES_DIR / "bridge"
BRIDGE_DIR.mkdir(parents=True, exist_ok=True)

INBOX_FILE = HERMES_DIR / "bridge_inbox.jsonl"
OUTBOX_FILE = HERMES_DIR / "bridge_outbox.jsonl"
CONFIG_FILE = HERMES_DIR / "config.yaml"
CRON_REPORTS_FILE = HERMES_DIR / "bridge_cron_reports.jsonl"

message_deque = deque(maxlen=100)
cron_reports = deque(maxlen=200)

metrics = {
    "total_requests": 0,
    "error_count": 0,
    "last_request_at": None,
    "cron_reports_today": 0,
    "files_pushed_today": 0
}

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    metrics["total_requests"] += 1
    metrics["last_request_at"] = datetime.now(timezone.utc).isoformat()
    if request.url.path != "/health":
        provided_key = request.headers.get("X-Bridge-Key")
        if not API_KEY or provided_key != API_KEY:
            metrics["error_count"] += 1
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    try:
        response = await call_next(request)
        if response.status_code >= 400:
            metrics["error_count"] += 1
        return response
    except Exception as e:
        metrics["error_count"] += 1
        raise e

@app.get("/health")
def health():
    return {
        "status": "ok",
        "agent": "allie",
        "uptime_seconds": int(time.time() - START_TIME),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

# --- Hevy Webhook ---
import hmac
import hashlib
import subprocess

HEVY_WEBHOOK_SECRET = os.environ.get("HEVY_WEBHOOK_SECRET", "")
HEVY_EVENTS_FILE = HERMES_DIR / "hevy_webhook_events.jsonl"

@app.post("/webhook/hevy")
async def hevy_webhook(request: Request):
    body = await request.body()

    # Validate HMAC signature if secret is configured
    if HEVY_WEBHOOK_SECRET:
        sig_header = request.headers.get("X-Hevy-Signature", "")
        expected = hmac.new(
            HEVY_WEBHOOK_SECRET.encode(), body, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(sig_header, expected):
            logger.warning("Hevy webhook: invalid signature")
            raise HTTPException(status_code=401, detail="Invalid signature")

    # Parse and store the event
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event_record = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": payload
    }

    try:
        with open(HEVY_EVENTS_FILE, "a") as f:
            f.write(json.dumps(event_record) + "\n")
    except Exception as e:
        logger.error(f"Error writing hevy event: {e}")

    # Drop a message into inbox to trigger hevy_sync
    sync_record = {
        "id": str(uuid.uuid4()),
        "message": "Hevy webhook received: new workout completed. Run delta sync.",
        "category": "webhook",
        "context": json.dumps(payload),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    message_deque.append(sync_record)
    try:
        with open(INBOX_FILE, "a") as f:
            f.write(json.dumps(sync_record) + "\n")
    except Exception as e:
        logger.error(f"Error writing webhook to inbox: {e}")

    logger.info(f"Hevy webhook processed: {event_record['id']}")
    return {"status": "ok", "event_id": event_record["id"]}

class SendMessage(BaseModel):
    message: str
    category: Optional[str] = None
    context: Optional[str] = None

@app.post("/relay/send")
def relay_send(payload: SendMessage):
    msg_id = str(uuid.uuid4())
    record = {
        "id": msg_id,
        "message": payload.message,
        "category": payload.category,
        "context": payload.context,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    message_deque.append(record)
    try:
        with open(INBOX_FILE, "a") as f:
            f.write(json.dumps(record) + "\n")
    except Exception as e:
        logger.error(f"Error writing to inbox: {e}")
        raise HTTPException(status_code=500, detail="Error writing to inbox")
    
    return {"id": msg_id, "status": "received"}

@app.get("/relay/inbox")
def relay_inbox(ack: bool = False):
    messages = []
    if OUTBOX_FILE.exists():
        try:
            with open(OUTBOX_FILE, "r") as f:
                for line in f:
                    if line.strip():
                        messages.append(json.loads(line))
        except Exception as e:
            logger.error(f"Error reading outbox: {e}")
    
    if ack and OUTBOX_FILE.exists():
        try:
            OUTBOX_FILE.unlink()
        except Exception as e:
            logger.error(f"Error clearing outbox: {e}")
            
    return {"messages": messages}

class PushFile(BaseModel):
    path: str
    content: str
    overwrite: bool = False

def resolve_safe_path(rel_path: str) -> Path:
    if ".." in rel_path or rel_path.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid path")
    resolved = (HERMES_DIR / rel_path).resolve()
    # Check if resolved path is within HERMES_DIR
    try:
        resolved.relative_to(HERMES_DIR)
    except ValueError:
        raise HTTPException(status_code=400, detail="Path traversal detected")
    return resolved

@app.post("/files/push")
def push_file(payload: PushFile):
    target_path = resolve_safe_path(payload.path)
    if target_path.exists() and not payload.overwrite:
        raise HTTPException(status_code=409, detail="File exists and overwrite is false")
    
    target_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(target_path, "w") as f:
            f.write(payload.content)
        metrics["files_pushed_today"] += 1
        return {"path": payload.path, "bytes_written": len(payload.content.encode('utf-8'))}
    except Exception as e:
        logger.error(f"Error writing file {payload.path}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/files/pull")
def pull_file(path: str):
    target_path = resolve_safe_path(path)
    if not target_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    if not target_path.is_file():
        raise HTTPException(status_code=400, detail="Not a file")
        
    try:
        content = target_path.read_text()
        return {"path": path, "content": content, "size": len(content.encode('utf-8'))}
    except Exception as e:
        logger.error(f"Error reading file {path}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/status/crons")
def get_crons():
    if not CONFIG_FILE.exists():
        return {"crons": [], "error": "Config file not found"}
    try:
        with open(CONFIG_FILE, "r") as f:
            config = yaml.safe_load(f) or {}
            crons = config.get("crons", [])
            return {"crons": crons}
    except Exception as e:
        logger.error(f"Error parsing config: {e}")
        return {"crons": [], "error": str(e)}

@app.get("/status/system")
def get_system():
    import platform
    import shutil
    
    try:
        total, used, free = shutil.disk_usage("/")
    except Exception:
        free = 0
    
    mem_used_pct = 0.0
    try:
        if platform.system() == "Linux":
            with open('/proc/meminfo', 'r') as f:
                meminfo = {}
                for line in f:
                    parts = line.split(':')
                    if len(parts) == 2:
                        meminfo[parts[0].strip()] = int(parts[1].split()[0])
            total_mem = meminfo.get('MemTotal', 0)
            available_mem = meminfo.get('MemAvailable', 0)
            if total_mem > 0:
                mem_used_pct = round(((total_mem - available_mem) / total_mem) * 100, 2)
    except Exception:
        pass

    uptime_str = "unknown"
    try:
        if platform.system() == "Linux":
            with open('/proc/uptime', 'r') as f:
                uptime_seconds = float(f.readline().split()[0])
            days, remainder = divmod(uptime_seconds, 86400)
            hours, remainder = divmod(remainder, 3600)
            minutes, seconds = divmod(remainder, 60)
            uptime_str = f"{int(days)}d {int(hours)}h {int(minutes)}m"
    except Exception:
        pass
        
    return {
        "hostname": platform.node(),
        "uptime": uptime_str,
        "disk_free_gb": round(free / (1024**3), 2) if free else 0.0,
        "memory_used_pct": mem_used_pct,
        "python_version": platform.python_version()
    }

class CronReport(BaseModel):
    cron_id: str
    name: str
    status: str
    tokens_used: Optional[int] = None
    duration_seconds: Optional[float] = None
    output_summary: Optional[str] = None

@app.post("/status/cron-report")
def add_cron_report(payload: CronReport):
    metrics["cron_reports_today"] += 1
    report_id = str(uuid.uuid4())
    record = payload.model_dump() if hasattr(payload, 'model_dump') else payload.dict()
    record["id"] = report_id
    record["timestamp"] = datetime.now(timezone.utc).isoformat()
    
    cron_reports.append(record)
    try:
        with open(CRON_REPORTS_FILE, "a") as f:
            f.write(json.dumps(record) + "\n")
    except Exception as e:
        logger.error(f"Error writing cron report: {e}")
        
    return {"id": report_id, "status": "recorded"}

@app.get("/status/cron-reports")
def get_cron_reports(limit: int = 20, status: Optional[str] = None):
    reports_list = list(cron_reports)[::-1]
    if status:
        reports_list = [r for r in reports_list if r.get("status") == status]
    reports_list = reports_list[:limit]
    return {"reports": reports_list, "total": len(cron_reports)}

@app.get("/files/list")
def list_files(path: str):
    target_path = resolve_safe_path(path)
    if not target_path.exists():
        raise HTTPException(status_code=404, detail="Directory not found")
    if not target_path.is_dir():
        raise HTTPException(status_code=400, detail="Not a directory")
        
    entries = []
    try:
        for entry in target_path.iterdir():
            entries.append({
                "name": entry.name,
                "type": "dir" if entry.is_dir() else "file",
                "size": entry.stat().st_size if entry.is_file() else 0
            })
    except Exception as e:
        logger.error(f"Error listing directory {path}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
        
    return {"path": path, "entries": entries}

@app.get("/status/metrics")
def get_metrics():
    return {
        "total_requests": metrics["total_requests"],
        "error_count": metrics["error_count"],
        "uptime_seconds": int(time.time() - START_TIME),
        "last_request_at": metrics["last_request_at"],
        "cron_reports_today": metrics["cron_reports_today"],
        "files_pushed_today": metrics["files_pushed_today"]
    }
