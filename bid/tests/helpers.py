import json
import os
import subprocess
from pathlib import Path

BID_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BID_ROOT.parent


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def frontmatter(path: Path):
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise AssertionError(f"missing frontmatter: {path}")
    raw = text.split("---\n", 2)[1]
    data = {}
    for line in raw.splitlines():
        if not line.strip():
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip().strip('"')
    return data, text


def run(*args, cwd=BID_ROOT, env=None):
    return subprocess.run(
        args,
        cwd=cwd,
        env=env or os.environ.copy(),
        text=True,
        capture_output=True,
        check=False,
    )
