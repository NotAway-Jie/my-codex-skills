#!/usr/bin/env python3
"""Prepare a private-repo-ready backup of personal Codex skills."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.dont_write_bytecode = True

from scan_skills import scan


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def copy_allowed_files(skills_root: Path, repo_dir: Path, inventory: list[dict], dry_run: bool) -> list[str]:
    copied = []
    copied_skills = {entry["skill"] for entry in inventory if entry["action"] == "copy"}
    skills_dest = repo_dir / "skills"
    if not dry_run and skills_dest.exists():
        for existing in skills_dest.iterdir():
            if existing.is_dir() and existing.name not in copied_skills:
                shutil.rmtree(existing)
    for entry in inventory:
        if entry["action"] != "copy":
            continue
        src = skills_root / entry["skill"] / entry["path"]
        dest = repo_dir / "skills" / entry["skill"] / entry["path"]
        copied.append(str(dest))
        if dry_run:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    return copied


def skill_index(data: dict) -> str:
    lines = [
        "# Codex Skills Index",
        "",
        f"Generated at: `{data['generated_at']}`",
        f"Skills root: `{data['skills_root']}`",
        "",
        "| Skill | Description | GitHub source | Files | Copied size | Skipped |",
        "|---|---|---|---:|---:|---:|",
    ]
    for skill in data["skills"]:
        sources = "<br>".join(skill["github_sources"]) if skill["github_sources"] else "Not detected"
        desc = (skill["description"] or skill["summary"] or "").replace("|", "\\|")
        lines.append(
            f"| `{skill['folder']}` | {desc} | {sources} | {skill['file_count']} | {skill['copied_size']} | {skill['skipped_count']} |"
        )
    return "\n".join(lines) + "\n"


def update_report(data: dict) -> str:
    lines = [
        "# Skills Update Report",
        "",
        f"Generated at: `{data['generated_at']}`",
        "",
        "This report identifies possible GitHub sources. It does not apply updates automatically.",
        "",
    ]
    for skill in data["skills"]:
        lines.append(f"## {skill['folder']}")
        if skill["github_sources"]:
            for source in skill["github_sources"]:
                lines.append(f"- Source: {source}")
            lines.append("- Status: source detected; compare upstream only after user confirmation.")
        else:
            lines.append("- Source: not detected.")
            lines.append("- Status: backed up and documented only.")
        if skill["skipped_count"] or skill["recorded_count"]:
            lines.append(f"- Review: {skill['skipped_count']} skipped, {skill['recorded_count']} recorded-only files.")
        lines.append("")
    return "\n".join(lines)


def sync_guide() -> str:
    return """# Sync Guide

## First Computer

1. Run `scripts/backup_flow.py` from the `skills-backupdate` skill.
2. Review `docs/LOCAL_UPDATE_CHECK.md`, `docs/SKILLS_INDEX.md`, `docs/UPDATE_REPORT.md`, and `manifest/file-inventory.json`.
3. Confirm any local skill updates or repository-only skill installs before applying them.
4. Create a private GitHub repo named `my-codex-skills` if it does not exist.
5. Commit and push only after reviewing large and suspicious file warnings.

Preview the optimized workflow:

```powershell
python C:\\Users\\NotAway\\.codex\\skills\\skills-backupdate\\scripts\\backup_flow.py --skills-root C:\\Users\\NotAway\\.codex\\skills --repo-dir C:\\Users\\NotAway\\Documents\\Codex\\my-codex-skills --dry-run
```

Run the workflow:

```powershell
python C:\\Users\\NotAway\\.codex\\skills\\skills-backupdate\\scripts\\backup_flow.py --skills-root C:\\Users\\NotAway\\.codex\\skills --repo-dir C:\\Users\\NotAway\\Documents\\Codex\\my-codex-skills
```

## Other Computer

Clone the private repo, then dry-run the installer:

```powershell
python scripts\\install_skills.py --repo-dir . --target-skills-root "$env:USERPROFILE\\.codex\\skills" --dry-run
```

If the dry-run looks correct:

```powershell
python scripts\\install_skills.py --repo-dir . --target-skills-root "$env:USERPROFILE\\.codex\\skills"
```

The installer backs up conflicting target skill folders and does not delete local-only skills.

## Pull and Apply

After the repo is cloned, preview the latest backup on another computer with:

```powershell
python scripts\\sync_skills.py apply --repo-dir . --target-skills-root "$env:USERPROFILE\\.codex\\skills"
```

This command runs `git pull --ff-only` and then dry-runs the installer.

To write changes after reviewing the plan:

```powershell
python scripts\\sync_skills.py apply --repo-dir . --target-skills-root "$env:USERPROFILE\\.codex\\skills" --confirm
```
"""


def risk_summary(data: dict) -> str:
    total_skills = len(data["skills"])
    copied = sum(1 for entry in data["inventory"] if entry["action"] == "copy")
    skipped = sum(1 for entry in data["inventory"] if entry["action"] == "skip")
    recorded = sum(1 for entry in data["inventory"] if entry["action"] == "record")
    sources = sum(1 for skill in data["skills"] if skill["github_sources"])
    return (
        f"skills={total_skills}, copied_files={copied}, recorded_only={recorded}, "
        f"skipped={skipped}, github_sources_detected={sources}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare my-codex-skills repository contents.")
    parser.add_argument("--skills-root", default=str(Path.home() / ".codex" / "skills"))
    parser.add_argument("--repo-dir", default=str(Path.home() / "Documents" / "Codex" / "my-codex-skills"))
    parser.add_argument("--max-file-mb", type=int, default=10)
    parser.add_argument("--max-skill-mb", type=int, default=100)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    skills_root = Path(args.skills_root).expanduser().resolve()
    repo_dir = Path(args.repo_dir).expanduser().resolve()
    data = scan(skills_root, args.max_file_mb, args.max_skill_mb)

    copied = copy_allowed_files(skills_root, repo_dir, data["inventory"], args.dry_run)
    if not args.dry_run:
        write_json(repo_dir / "manifest" / "skills-manifest.json", {k: v for k, v in data.items() if k != "inventory"})
        write_json(repo_dir / "manifest" / "file-inventory.json", data["inventory"])
        (repo_dir / "docs").mkdir(parents=True, exist_ok=True)
        (repo_dir / "docs" / "SKILLS_INDEX.md").write_text(skill_index(data), encoding="utf-8")
        (repo_dir / "docs" / "UPDATE_REPORT.md").write_text(update_report(data), encoding="utf-8")
        (repo_dir / "docs" / "SYNC_GUIDE.md").write_text(sync_guide(), encoding="utf-8")
        scripts_dir = repo_dir / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(Path(__file__).with_name("install_skills.py"), scripts_dir / "install_skills.py")
        shutil.copy2(Path(__file__).with_name("scan_skills.py"), scripts_dir / "scan_skills.py")
        shutil.copy2(Path(__file__).with_name("sync_skills.py"), scripts_dir / "sync_skills.py")
        shutil.copy2(Path(__file__).with_name("update_check.py"), scripts_dir / "update_check.py")
        shutil.copy2(Path(__file__).with_name("backup_flow.py"), scripts_dir / "backup_flow.py")
        shutil.copy2(Path(__file__), scripts_dir / "prepare_sync.py")

    print(risk_summary(data))
    print(f"repo_dir={repo_dir}")
    print(f"would_copy={len(copied)}" if args.dry_run else f"copied={len(copied)}")
    if args.dry_run:
        print("dry_run=true; no files written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
