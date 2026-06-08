#!/usr/bin/env python3
"""Report possible upstream updates for GitHub-sourced backed-up skills."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def latest_commit(repo_url: str, timeout: int) -> dict:
    owner_repo = repo_url.rstrip("/").removeprefix("https://github.com/")
    api = f"https://api.github.com/repos/{owner_repo}/commits/HEAD"
    req = Request(api, headers={"Accept": "application/vnd.github+json", "User-Agent": "skills-backupdate"})
    with urlopen(req, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8"))
    return {
        "sha": data.get("sha", ""),
        "html_url": data.get("html_url", ""),
        "date": data.get("commit", {}).get("committer", {}).get("date", ""),
    }


def local_hint(repo_dir: Path, skill: str) -> str:
    try:
        return subprocess.check_output(
            ["git", "log", "-n", "1", "--format=%H", "--", f"skills/{skill}"],
            cwd=str(repo_dir),
            text=True,
        ).strip()
    except Exception:
        return ""


def render_report(generated_at: str, rows: list[dict]) -> str:
    lines = [
        "# Skills Update Report",
        "",
        f"Generated at: `{generated_at}`",
        "",
        "This report checks detected GitHub sources. It does not apply updates automatically.",
        "",
    ]
    for row in rows:
        lines.append(f"## {row['skill']}")
        lines.append(f"- Source: {row['source']}")
        lines.append(f"- Status: {row['status']}")
        if row.get("remote_sha"):
            lines.append(f"- Remote HEAD: `{row['remote_sha'][:12]}`")
        if row.get("remote_url"):
            lines.append(f"- Remote commit: {row['remote_url']}")
        if row.get("local_hint"):
            lines.append(f"- Local backup commit hint: `{row['local_hint'][:12]}`")
        if row.get("error"):
            lines.append(f"- Error: {row['error']}")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check GitHub-sourced skills for upstream HEAD changes.")
    parser.add_argument("--repo-dir", default=".")
    parser.add_argument("--timeout", type=int, default=15)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    repo_dir = Path(args.repo_dir).expanduser().resolve()
    manifest = repo_dir / "manifest" / "skills-manifest.json"
    if not manifest.exists():
        raise SystemExit(f"Missing manifest: {manifest}")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    rows = []
    for skill in data.get("skills", []):
        folder = skill.get("folder", "")
        for source in skill.get("github_sources", []):
            row = {"skill": folder, "source": source, "status": "unknown", "local_hint": local_hint(repo_dir, folder)}
            try:
                remote = latest_commit(source, args.timeout)
                row.update(
                    {
                        "remote_sha": remote["sha"],
                        "remote_url": remote["html_url"],
                        "remote_date": remote["date"],
                        "status": "remote HEAD checked; review before updating",
                    }
                )
            except Exception as exc:
                row.update({"status": "check failed", "error": str(exc)})
            rows.append(row)

    generated_at = utc_now()
    result = {"generated_at": generated_at, "updates": rows}
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if not args.dry_run:
        (repo_dir / "manifest").mkdir(parents=True, exist_ok=True)
        (repo_dir / "docs").mkdir(parents=True, exist_ok=True)
        (repo_dir / "manifest" / "update-check.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (repo_dir / "docs" / "UPDATE_REPORT.md").write_text(render_report(generated_at, rows), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
