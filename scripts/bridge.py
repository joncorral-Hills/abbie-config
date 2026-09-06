#!/usr/bin/env python3
import argparse
import json
import os
import ssl
import sys
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / ".bridge_config.json"

def load_config():
    if not CONFIG_PATH.exists():
        print(f"❌ Config file not found at {CONFIG_PATH}")
        sys.exit(1)
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)

def make_request(method, endpoint, payload=None, query=None):
    config = load_config()
    url = f"{config['url'].rstrip('/')}{endpoint}"
    if query:
        url += "?" + urllib.parse.urlencode(query)
    
    headers = {
        "X-Bridge-Key": config["api_key"]
    }
    
    data = None
    if payload is not None:
        data = json.dumps(payload).encode('utf-8')
        headers["Content-Type"] = "application/json"
        
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE
    try:
        with urllib.request.urlopen(req, timeout=30, context=ssl_ctx) as response:
            res_body = response.read()
            if res_body:
                return json.loads(res_body)
            return {}
    except urllib.error.HTTPError as e:
        print(f"❌ HTTP Error {e.code}: {e.read().decode('utf-8')}")
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"⚠️  Bridge connection failed: {e.reason}. Consider using Notion bridge fallback.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Request error: {e}")
        sys.exit(1)

def cmd_health(args):
    res = make_request("GET", "/health")
    print("✅ Allie is reachable!")
    print(json.dumps(res, indent=2))

def cmd_send(args):
    payload = {"message": args.message}
    if args.category:
        payload["category"] = args.category
    if args.context:
        payload["context"] = args.context
        
    res = make_request("POST", "/relay/send", payload=payload)
    print(f"📬 Sent successfully: {res.get('id')}")

def cmd_read(args):
    res = make_request("GET", "/relay/inbox", query={"ack": "true" if args.ack else "false"})
    messages = res.get("messages", [])
    if not messages:
        print("📭 No new messages.")
        return
    for msg in messages:
        print(f"📩 [{msg.get('timestamp')}] {msg.get('category', 'msg')}: {msg.get('message')}")

def cmd_status(args):
    print("🔄 Fetching status...")
    system = make_request("GET", "/status/system")
    crons = make_request("GET", "/status/crons")
    print("💻 System:")
    print(json.dumps(system, indent=2))
    print("\n⏰ Crons:")
    print(json.dumps(crons, indent=2))

def cmd_push(args):
    name = args.skill_name
    # Support pushing skills or runbooks
    candidates = [
        Path(f".agents/skills/{name}"),
        Path(f"runbooks/{name}.md"),
    ]
    
    skill_dir = None
    runbook_file = None
    for c in candidates:
        if c.is_dir():
            skill_dir = c
            break
        elif c.is_file():
            runbook_file = c
            break
    
    if runbook_file:
        # Push single runbook file
        content = runbook_file.read_text(errors='replace')
        remote = f"runbooks/{runbook_file.name}"
        res = make_request("POST", "/files/push", payload={"path": remote, "content": content, "overwrite": True})
        print(f"✅ Pushed {remote} ({res.get('bytes_written')} bytes)")
        return
    
    if not skill_dir:
        print(f"❌ Not found as skill or runbook: {name}")
        print(f"   Looked for: .agents/skills/{name}/ and runbooks/{name}.md")
        sys.exit(1)
    
    pushed = 0
    for root, _, files in os.walk(skill_dir):
        for file in files:
            file_path = Path(root) / file
            remote_path = f"skills/{name}/{file_path.relative_to(skill_dir)}"
            try:
                content = file_path.read_text(errors='replace')
                res = make_request("POST", "/files/push", payload={"path": remote_path, "content": content, "overwrite": True})
                print(f"  ✅ {remote_path} ({res.get('bytes_written')} bytes)")
                pushed += 1
            except Exception as e:
                print(f"  ❌ {remote_path}: {e}")
    print(f"\n📦 Pushed {pushed} files for skill '{name}'")


def cmd_push_file(args):
    local_path = Path(args.local)
    if not local_path.exists():
        print(f"❌ Local file not found: {local_path}")
        sys.exit(1)
        
    content = local_path.read_text(errors='replace')
    res = make_request("POST", "/files/push", payload={"path": args.remote, "content": content, "overwrite": True})
    print(f"✅ Pushed to {args.remote} ({res.get('bytes_written')} bytes)")

def cmd_pull(args):
    res = make_request("GET", "/files/pull", query={"path": args.remote_path})
    print(f"📄 Content of {args.remote_path} ({res.get('size')} bytes):\n")
    print(res.get("content"))

def cmd_reports(args):
    query = {"limit": args.limit}
    res = make_request("GET", "/status/cron-reports", query=query)
    reports = res.get("reports", [])
    total = res.get("total", 0)
    
    print(f"📋 Cron Reports (Showing {len(reports)} of {total}):")
    if not reports:
        print("   No reports found.")
        return
        
    for r in reports:
        status = r.get("status", "")
        if status == "success":
            icon = "✅"
        elif status == "error":
            icon = "❌"
        elif status == "skipped":
            icon = "⏭️"
        else:
            icon = "❓"
            
        print(f" {icon} [{r.get('timestamp', 'unknown')}] {r.get('name')} (ID: {r.get('id', '')[:8]}...)")
        if r.get('output_summary'):
            print(f"      Summary: {r.get('output_summary')}")

def cmd_ls(args):
    res = make_request("GET", "/files/list", query={"path": args.path})
    entries = res.get("entries", [])
    
    print(f"📁 Listing of {res.get('path')}:")
    if not entries:
        print("   (Empty directory)")
        return
        
    for entry in sorted(entries, key=lambda e: (e['type'] != 'dir', e['name'])):
        if entry['type'] == 'dir':
            print(f" 📂 {entry['name']}/")
        else:
            size_kb = entry['size'] / 1024
            print(f" 📄 {entry['name']} ({size_kb:.1f} KB)")

def cmd_metrics(args):
    res = make_request("GET", "/status/metrics")
    print("📊 Server Metrics:")
    print(json.dumps(res, indent=2))

def main():
    parser = argparse.ArgumentParser(description="Bridge CLI Client")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    subparsers.add_parser("health")
    
    send_parser = subparsers.add_parser("send")
    send_parser.add_argument("message")
    send_parser.add_argument("--category", required=False)
    send_parser.add_argument("--context", required=False)
    
    read_parser = subparsers.add_parser("read")
    read_parser.add_argument("--ack", action="store_true")
    
    subparsers.add_parser("status")
    
    push_parser = subparsers.add_parser("push")
    push_parser.add_argument("skill_name")
    
    push_file_parser = subparsers.add_parser("push-file")
    push_file_parser.add_argument("local")
    push_file_parser.add_argument("remote")
    
    pull_parser = subparsers.add_parser("pull")
    pull_parser.add_argument("remote_path")
    
    reports_parser = subparsers.add_parser("reports")
    reports_parser.add_argument("--limit", type=int, default=20)
    
    ls_parser = subparsers.add_parser("ls")
    ls_parser.add_argument("path")
    
    subparsers.add_parser("metrics")
    
    args = parser.parse_args()
    
    if args.command == "health":
        cmd_health(args)
    elif args.command == "send":
        cmd_send(args)
    elif args.command == "read":
        cmd_read(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "push":
        cmd_push(args)
    elif args.command == "push-file":
        cmd_push_file(args)
    elif args.command == "pull":
        cmd_pull(args)
    elif args.command == "reports":
        cmd_reports(args)
    elif args.command == "ls":
        cmd_ls(args)
    elif args.command == "metrics":
        cmd_metrics(args)

if __name__ == "__main__":
    main()
