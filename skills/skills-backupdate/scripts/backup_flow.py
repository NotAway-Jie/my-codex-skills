#!/usr/bin/env python3
"""Orchestrate update check, optional extra-skill install, then backup."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True

from update_check import check_updates, report_markdown


def run(command: list[str], cwd: Path | None = None) -> None:
    print(f"+ {' '.join(command)}")
    subprocess.run(command, cwd=str(cwd) if cwd else None, check=True)


def skill_names(root: Path) -> set[str]:
    if not root.exists():
        return set()
    return {p.name for p in root.iterdir() if p.is_dir() and not p.name.startswith(".") and p.name != "_backups"}


def extra_repo_skills(repo_dir: Path, skills_root: Path) -> list[str]:
    return sorted(skill_names(repo_dir / "skills") - skill_names(skills_root))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the optimized skills-backupdate workflow.")
    parser.add_argument("--skills-root", default=str(Path.home() / ".codex" / "skills"))
    parser.add_argument("--repo-dir", default=str(Path.home() / "Documents" / "Codex" / "my-codex-skills"))
    parser.add_argument("--install-extra", action="append", default=[], help="Install a repository-only skill before backup. Repeat for more.")
    parser.add_argument("--install-all-extra", action="store_true", help="Install every repository-only skill before backup.")
    parser.add_argument("--dry-run", action="store_true", help="Report planned actions without installing or backing up.")
    parser.add_argument("--max-file-mb", type=int, default=10)
    parser.add_argument("--max-skill-mb", type=int, default=100)
    args = parser.parse_args()

    skills_root = Path(args.skills_root).expanduser().resolve()
    repo_dir = Path(args.repo_dir).expanduser().resolve()

    update_data = check_updates(skills_root, args.max_file_mb, args.max_skill_mb)
    update_md = report_markdown(update_data)
    print(update_md)

    extras = extra_repo_skills(repo_dir, skills_root)
    if extras:
        print("Repository-only skills:")
        for name in extras:
            print(f"- {name}")
    else:
        print("Repository-only skills: none")

    requested = sorted(set(extras if args.install_all_extra else args.install_extra))
    unknown = set(requested) - set(extras)
    if unknown:
        raise SystemExit(f"Requested extra skill(s) are not repository-only: {', '.join(sorted(unknown))}")

    if requested:
        command = [
            sys.executable,
            str(repo_dir / "scripts" / "install_skills.py"),
            "--repo-dir",
            str(repo_dir),
            "--target-skills-root",
            str(skills_root),
        ]
        for name in requested:
            command.extend(["--skill", name])
        if args.dry_run:
            command.append("--dry-run")
        run(command, repo_dir)
    elif extras:
        print("No repository-only skills installed. Pass --install-extra NAME or --install-all-extra after confirmation.")

    if args.dry_run:
        print("dry_run=true; backup not refreshed")
        return 0

    reports_dir = repo_dir / "docs"
    manifest_dir = repo_dir / "manifest"
    reports_dir.mkdir(parents=True, exist_ok=True)
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "LOCAL_UPDATE_CHECK.md").write_text(update_md, encoding="utf-8")

    run([
        sys.executable,
        str(Path(__file__).with_name("prepare_sync.py")),
        "--skills-root",
        str(skills_root),
        "--repo-dir",
        str(repo_dir),
        "--max-file-mb",
        str(args.max_file_mb),
        "--max-skill-mb",
        str(args.max_skill_mb),
    ])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
