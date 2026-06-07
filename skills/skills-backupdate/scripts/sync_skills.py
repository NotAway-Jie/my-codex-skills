#!/usr/bin/env python3
"""Pull and optionally apply a my-codex-skills repository."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def run(command: list[str], cwd: Path) -> None:
    print(f"+ {' '.join(command)}")
    subprocess.run(command, cwd=str(cwd), check=True)


def output(command: list[str], cwd: Path) -> str:
    return subprocess.check_output(command, cwd=str(cwd), text=True).strip()


def pull_repo(repo_dir: Path) -> None:
    if not (repo_dir / ".git").exists():
        raise SystemExit(f"Not a git repository: {repo_dir}")
    run(["git", "fetch", "--prune"], repo_dir)
    branch = output(["git", "branch", "--show-current"], repo_dir)
    if not branch:
        raise SystemExit("Cannot pull while HEAD is detached.")
    upstream = output(["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], repo_dir)
    remote, remote_branch = upstream.split("/", 1)
    run(["git", "pull", "--ff-only", remote, remote_branch], repo_dir)


def apply_skills(repo_dir: Path, target_skills_root: Path, confirm: bool) -> None:
    installer = repo_dir / "scripts" / "install_skills.py"
    if not installer.exists():
        raise SystemExit(f"Missing installer: {installer}")
    command = [
        sys.executable,
        str(installer),
        "--repo-dir",
        str(repo_dir),
        "--target-skills-root",
        str(target_skills_root),
    ]
    if not confirm:
        command.append("--dry-run")
    run(command, repo_dir)
    if not confirm:
        print("apply defaulted to dry-run; rerun with --confirm to write skills")


def main() -> int:
    parser = argparse.ArgumentParser(description="Pull and optionally apply backed-up Codex skills.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    pull_parser = subparsers.add_parser("pull", help="Fetch and fast-forward the backup repository only.")
    pull_parser.add_argument("--repo-dir", default=".")

    apply_parser = subparsers.add_parser("apply", help="Pull the backup repository, then install skills.")
    apply_parser.add_argument("--repo-dir", default=".")
    apply_parser.add_argument("--target-skills-root", default=str(Path.home() / ".codex" / "skills"))
    apply_parser.add_argument("--confirm", action="store_true", help="Write changes. Without this, apply is a dry-run.")

    args = parser.parse_args()
    repo_dir = Path(args.repo_dir).expanduser().resolve()

    if args.command == "pull":
        pull_repo(repo_dir)
        return 0

    if args.command == "apply":
        pull_repo(repo_dir)
        apply_skills(repo_dir, Path(args.target_skills_root).expanduser().resolve(), args.confirm)
        return 0

    raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
