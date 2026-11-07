"""Deployment config: Vercel static frontend, lean backend image, no secrets in the repo."""
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_frontend_vercel_config():
    cfg = json.loads((ROOT / "game" / "vercel.json").read_text(encoding="utf-8"))
    assert cfg["buildCommand"] == "npm run build" and cfg["outputDirectory"] == "."
    csp = next(h["value"] for rule in cfg["headers"] for h in rule["headers"] if h["key"] == "Content-Security-Policy")
    assert "https://*.run.app" in csp.split("connect-src", 1)[1].split(";")[0]
    assert "config.js" in (ROOT / "game" / ".gitignore").read_text(encoding="utf-8").split()
    assert (ROOT / "game" / "personas.json").exists()


def test_runtime_requirements_are_lean_and_env_is_never_shipped():
    req = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    assert "telegram" not in req and "pillow" not in req and "fastapi" in req and "upstash-redis" in req
    assert ".env" in (ROOT / ".gitignore").read_text(encoding="utf-8").split()
    dock = (ROOT / ".dockerignore").read_text(encoding="utf-8").split()
    assert ".env" in dock and "bot" in dock


def test_no_api_keys_in_tracked_files():
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8").stdout.split()
    rx = re.compile(r"gsk_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9-]{30,}|\d{9,10}:[A-Za-z0-9_-]{35}")
    leaks = [f for f in files if (ROOT / f).is_file() and f.endswith((".py", ".js", ".json", ".md", ".yaml", ".yml", ".txt", ".html", ".example"))
             and rx.search((ROOT / f).read_text(encoding="utf-8", errors="ignore"))]
    assert not leaks, leaks
