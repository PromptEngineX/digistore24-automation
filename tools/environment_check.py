from pathlib import Path
import importlib
import json
import shutil
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
RESULTS = []

def check(name, ok, detail=""):
    RESULTS.append({"name": name, "status": "PASS" if ok else "FAIL", "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))

def command_version(command, args):
    exe = shutil.which(command)
    if not exe:
        return False, "not found in PATH"
    try:
        p = subprocess.run([exe, *args], capture_output=True, text=True, timeout=10)
        out = (p.stdout or p.stderr).strip().splitlines()
        return p.returncode == 0, out[0] if out else "available"
    except Exception as e:
        return False, str(e)

print("=" * 64)
print("DIGIFLOW AUTOMATION PREFLIGHT")
print("=" * 64)
print(f"Python: {sys.version.split()[0]}")
print(f"Project: {ROOT}")
print()

required = [
    ("Playwright", "playwright"),
    ("Requests", "requests"),
    ("BeautifulSoup", "bs4"),
    ("lxml", "lxml"),
    ("Pydantic", "pydantic"),
    ("python-dotenv", "dotenv"),
    ("Pytest", "pytest"),
    ("pytest-playwright", "pytest_playwright"),
    ("Pillow", "PIL"),
    ("RapidFuzz", "rapidfuzz"),
    ("Tenacity", "tenacity"),
    ("HTTPX", "httpx"),
    ("Rich", "rich"),
]

for label, module in required:
    try:
        m = importlib.import_module(module)
        check(label, True, getattr(m, "__version__", "installed"))
    except Exception as e:
        check(label, False, str(e))

ok, detail = command_version("ffmpeg", ["-version"])
check("FFmpeg", ok, detail)

ok, detail = command_version("chrome", ["--version"])
if not ok:
    chrome = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
    if chrome.exists():
        try:
            p = subprocess.run([str(chrome), "--version"], capture_output=True, text=True, timeout=10)
            ok = p.returncode == 0
            detail = (p.stdout or p.stderr).strip()
        except Exception as e:
            detail = str(e)
check("Google Chrome", ok, detail)

try:
    with urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=3) as r:
        data = json.loads(r.read().decode("utf-8"))
        check("Chrome CDP :9222", True, data.get("Browser", "connected"))
except Exception as e:
    check("Chrome CDP :9222", False, str(e))

try:
    with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=3) as r:
        data = json.loads(r.read().decode("utf-8"))
        models = [x.get("name", "") for x in data.get("models", [])]
        check("Ollama", True, f"{len(models)} model(s)")
        for wanted in ("llama3.1:8b", "qwen3:8b"):
            check(
                f"Ollama model {wanted}",
                wanted in models,
                "installed" if wanted in models else "missing"
            )
except Exception as e:
    check("Ollama", False, str(e))

try:
    import sqlite3
    db = sqlite3.connect(str(ROOT / "data" / "digiflow.sqlite3"))
    db.execute("SELECT 1")
    db.close()
    check("DigiFlow SQLite", True, str(ROOT / "data" / "digiflow.sqlite3"))
except Exception as e:
    check("DigiFlow SQLite", False, str(e))

try:
    with urllib.request.urlopen("http://127.0.0.1:8787/api/products/all", timeout=3) as r:
        check("DigiFlow API :8787", r.status == 200, f"HTTP {r.status}")
except Exception as e:
    check("DigiFlow API :8787", False, str(e))

lock = ROOT / "requirements.lock.txt"
check("Dependency lock file", lock.exists(), str(lock))

print()
failed = [x for x in RESULTS if x["status"] == "FAIL"]

print("=" * 64)
print(f"RESULT: {'READY' if not failed else 'NOT READY'}")
print(f"PASS: {len(RESULTS) - len(failed)}  FAIL: {len(failed)}")
print("=" * 64)

(ROOT / "data" / "environment_preflight.json").write_text(
    json.dumps({"ready": not failed, "results": RESULTS}, indent=2),
    encoding="utf-8"
)

sys.exit(0 if not failed else 1)
