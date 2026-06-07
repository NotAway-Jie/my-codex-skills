#!/usr/bin/env python3
"""Scan personal Codex skills without loading large files into context."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_MAX_FILE_MB = 10
DEFAULT_MAX_SKILL_MB = 100
GITHUB_RE = re.compile(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
SECRET_NAME_RE = re.compile(
    r"(^\.env(\..*)?$|token|secret|credential|credentials|cookie|session|private[_-]?key|id_rsa|id_dsa|\.pem$|\.p12$|\.pfx$)",
    re.IGNORECASE,
)
SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    "dist",
    "build",
    ".next",
    ".cache",
}
BINARY_EXTS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".pdf",
    ".zip",
    ".7z",
    ".tar",
    ".gz",
    ".mp4",
    ".mov",
    ".avi",
    ".db",
    ".sqlite",
    ".sqlite3",
    ".bin",
    ".onnx",
    ".pt",
    ".pth",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_text_limited(path: Path, limit: int = 65536) -> str:
    try:
        data = path.read_bytes()[:limit]
        return data.decode("utf-8", errors="replace")
    except OSError:
        return ""


def parse_skill_md(path: Path) -> dict:
    text = read_text_limited(path)
    result = {"name": path.parent.name, "description": "", "summary": ""}
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].splitlines():
                if ":" not in line:
                    continue
                key, value = line.split(":", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key in {"name", "description"}:
                    result[key] = value
            body = parts[2]
        else:
            body = text
    else:
        body = text
    paragraphs = [line.strip() for line in body.splitlines() if line.strip() and not line.startswith("#")]
    result["summary"] = " ".join(paragraphs[:3])[:600]
    return result


def find_github_sources(skill_dir: Path) -> list[str]:
    sources: set[str] = set()
    candidates = [
        skill_dir / "SKILL.md",
        skill_dir / "agents" / "openai.yaml",
        skill_dir / ".git" / "config",
    ]
    candidates.extend(skill_dir.glob("*.md"))
    for path in candidates:
        if path.exists() and path.is_file():
            sources.update(GITHUB_RE.findall(read_text_limited(path)))
    return sorted(sources)


def classify_file(path: Path, rel: str, max_file_bytes: int) -> tuple[str, str]:
    name = path.name
    if any(part in SKIP_DIRS for part in path.parts):
        return "skip", "skip directory"
    if SECRET_NAME_RE.search(name):
        return "skip", "suspicious credential filename"
    try:
        size = path.stat().st_size
    except OSError:
        return "skip", "unreadable"
    if size > max_file_bytes:
        return "skip", "over max file size"
    if path.suffix.lower() in BINARY_EXTS:
        return "record", "binary or asset file"
    if rel.endswith(".log") or rel.endswith(".tmp"):
        return "skip", "log or temporary file"
    return "copy", "allowed"


def scan_skill(skill_dir: Path, max_file_bytes: int) -> tuple[dict, list[dict]]:
    skill_md = skill_dir / "SKILL.md"
    meta = parse_skill_md(skill_md) if skill_md.exists() else {"name": skill_dir.name, "description": "", "summary": ""}
    files = []
    total_size = 0
    copied_size = 0
    skipped_count = 0
    recorded_count = 0

    for path in sorted(skill_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(skill_dir).as_posix()
        try:
            size = path.stat().st_size
            mtime = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
        except OSError:
            size = 0
            mtime = ""
        total_size += size
        action, reason = classify_file(path, rel, max_file_bytes)
        entry = {
            "skill": skill_dir.name,
            "path": rel,
            "size": size,
            "mtime": mtime,
            "action": action,
            "reason": reason,
            "sha256": sha256_file(path) if action in {"copy", "record"} else "",
        }
        if action == "copy":
            copied_size += size
        elif action == "skip":
            skipped_count += 1
        else:
            recorded_count += 1
        files.append(entry)

    skill = {
        "folder": skill_dir.name,
        "name": meta.get("name") or skill_dir.name,
        "description": meta.get("description", ""),
        "summary": meta.get("summary", ""),
        "path": str(skill_dir),
        "github_sources": find_github_sources(skill_dir),
        "total_size": total_size,
        "copied_size": copied_size,
        "file_count": len(files),
        "skipped_count": skipped_count,
        "recorded_count": recorded_count,
    }
    return skill, files


def scan(skills_root: Path, max_file_mb: int, max_skill_mb: int) -> dict:
    max_file_bytes = max_file_mb * 1024 * 1024
    max_skill_bytes = max_skill_mb * 1024 * 1024
    skills = []
    inventory = []
    for child in sorted(skills_root.iterdir()):
        if not child.is_dir():
            continue
        if child.name == ".system" or child.name.startswith("."):
            continue
        if child.name.lower() in {"cache", "plugins"}:
            continue
        skill, files = scan_skill(child, max_file_bytes)
        if skill["total_size"] > max_skill_bytes:
            downgraded_size = 0
            downgraded_count = 0
            for entry in files:
                if entry["action"] == "copy":
                    downgraded_size += entry["size"]
                    downgraded_count += 1
                    entry["action"] = "record"
                    entry["reason"] = "skill over max folder size"
            skill["copied_size"] = max(0, skill["copied_size"] - downgraded_size)
            skill["recorded_count"] += downgraded_count
        skills.append(skill)
        inventory.extend(files)
    return {
        "generated_at": utc_now(),
        "skills_root": str(skills_root),
        "thresholds": {"max_file_mb": max_file_mb, "max_skill_mb": max_skill_mb},
        "skills": skills,
        "inventory": inventory,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan personal Codex skills.")
    parser.add_argument("--skills-root", default=str(Path.home() / ".codex" / "skills"))
    parser.add_argument("--out", help="Optional JSON output path.")
    parser.add_argument("--max-file-mb", type=int, default=DEFAULT_MAX_FILE_MB)
    parser.add_argument("--max-skill-mb", type=int, default=DEFAULT_MAX_SKILL_MB)
    args = parser.parse_args()

    result = scan(Path(args.skills_root).expanduser().resolve(), args.max_file_mb, args.max_skill_mb)
    text = json.dumps(result, indent=2, ensure_ascii=False)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + os.linesep, encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
