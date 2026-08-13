"""End-to-end: launch run_all.py --live, hit /api/live, verify, then stop."""
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

# launch the full stack with the live feed enabled
proc = subprocess.Popen(
    [sys.executable, "-u", "app/run_all.py", "--live"],
    cwd=str(Path(__file__).resolve().parents[1]),
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    text=True, encoding="utf-8", errors="replace",
)
live = {"ok": False}
try:
    # find the API port from the banner (may fall back off 8000)
    deadline = time.time() + 20
    port = None
    banner = ""
    while time.time() < deadline and proc.poll() is None:
        line = proc.stdout.readline()
        if line:
            banner += line
            if "REST API" in line:
                port = line.strip().split(":")[-1]
            if "Live MQTT feed" in line and "ENABLED" in line:
                live["banner"] = True
            if "Live MQTT feed" in line:
                live["banner_line"] = line.strip()
        if "Ctrl-C" in banner or "shutting" in banner:
            break
        time.sleep(0.1)
    print("PORT:", port)
    if port:
        url = f"http://127.0.0.1:{port}/api/live"
        for _ in range(40):
            try:
                with urllib.request.urlopen(url, timeout=2) as r:
                    body = r.read().decode()
                    import json
                    live["json"] = json.loads(body)
                    live["ok"] = live["json"].get("enabled") is True
                    break
            except Exception:
                time.sleep(0.5)
    print("LIVE JSON:", live.get("json"))
    print("BANNER LINE:", live.get("banner_line"))
finally:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except Exception:
        proc.kill()

ok = live.get("ok") and live.get("banner")
print("E2E RESULT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
