#!/usr/bin/env python3
"""Lightweight GitHub source checks for personal Codex skills."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True

from scan_skills import scan, utc_now


def run_text(command: list[str], cwd: Path | None = None) -> tuple[int, str]:
    try:
        completed = subprocess.run(command, cwd=str(cwd) if cwd else None, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)
    return completed.returncode, (completed.stdout or completed.stderr).strip()


def local_git_head(skill_path: Path) -> str:
    if not (skill_path / ".git").exists():
        return ""
    code, text = run_text(["git", "rev-parse", "HEAD"], skill_path)
    return text if code == 0 else ""


def remote_head(source: str) -> tuple[str, str]:
    code, text = run_text(["git", "ls-remote", source, "HEAD"])
    if code != 0:
        return "", text
    first = text.splitlines()[0] if text else ""
    return (first.split()[0], "") if first else ("", "empty ls-remote response")


def check_updates(skills_root: Path, max_file_mb: int, max_skill_mb: int) -> dict:
    data = scan(skills_root, max_file_mb, max_skill_mb)
    checks = []
    for skill in data["skills"]:
        skill_path = Path(skill["path"])
        local_head = local_git_head(skill_path)
        if not skill["github_sources"]:
            checks.append({
                "skill": skill["folder"],
                "status": "no_source",
                "sources": [],
                "local_head": local_head,
                "remote_head": "",
                "note": "No GitHub source detected.",
            })
            continue
        for source in skill["github_sources"]:
            remote, error = remote_head(source)
            status = "source_detected"
            note = "Remote HEAD checked; compare manually before updating."
            if error:
                status = "check_failed"
                note = error
            elif local_head and remote and local_head == remote:
                status = "same_head"
                note = "Local git HEAD matches remote HEAD."
            elif remote:
                status = "possible_update"
            checks.append({
                "skill": skill["folder"],
                "status": status,
                "sources": [source],
                "local_head": local_head,
                "remote_head": remote,
                "note": note,
            })
    return {"generated_at": utc_now(), "skills_root": str(skills_root), "checks": checks}


def report_markdown(data: dict) -> str:
    lines = [
        "# Local Skill Update Check",
        "",
        f"Generated at: `{data['generated_at']}`",
        f"Skills root: `{data['skills_root']}`",
        "",
        "| Skill | Status | Source | Note |",
        "|---|---|---|---|",
    ]
    for check in data["checks"]:
        source = "<br>".join(check["sources"]) if check["sources"] else "Not detected"
        note = check["note"].replace("|", "\\|")
        lines.append(f"| `{check['skill']}` | `{check['status']}` | {source} | {note} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Lightweight check for skill upstream updates.")
    parser.add_argument("--skills-root", default=str(Path.home() / ".codex" / "skills"))
    parser.add_argument("--out-json", default="")
    parser.add_argument("--out-md", default="")
    parser.add_argument("--max-file-mb", type=int, default=10)
    parser.add_argument("--max-skill-mb", type=int, default=100)
    args = parser.parse_args()

    result = check_updates(Path(args.skills_root).expanduser().resolve(), args.max_file_mb, args.max_skill_mb)
    if args.out_json:
        out = Path(args.out_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.out_md:
        out = Path(args.out_md)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report_markdown(result), encoding="utf-8")
    if not args.out_json and not args.out_md:
        print(report_markdown(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
