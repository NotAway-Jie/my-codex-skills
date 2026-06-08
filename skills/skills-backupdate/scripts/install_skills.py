#!/usr/bin/env python3
"""Install backed-up Codex skills from my-codex-skills onto another computer."""

from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from pathlib import Path


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def copytree(src: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)


def main() -> int:
    parser = argparse.ArgumentParser(description="Install skills from a skills backup repository.")
    parser.add_argument("--repo-dir", default=".")
    parser.add_argument("--target-skills-root", default=str(Path.home() / ".codex" / "skills"))
    parser.add_argument("--backup-dir", default="")
    parser.add_argument("--skill", action="append", default=[], help="Install only the named skill; repeat for multiple skills.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    repo_dir = Path(args.repo_dir).expanduser().resolve()
    source_root = repo_dir / "skills"
    target_root = Path(args.target_skills_root).expanduser().resolve()
    backup_root = Path(args.backup_dir).expanduser().resolve() if args.backup_dir else target_root / "_backups" / timestamp()

    if not source_root.exists():
        raise SystemExit(f"Missing source skills directory: {source_root}")

    requested = set(args.skill)
    planned = []
    seen = set()
    for skill_dir in sorted(source_root.iterdir()):
        if not skill_dir.is_dir():
            continue
        if requested and skill_dir.name not in requested:
            continue
        seen.add(skill_dir.name)
        target = target_root / skill_dir.name
        action = "add" if not target.exists() else "overwrite-with-backup"
        planned.append((action, skill_dir, target))

    missing = sorted(requested - seen)
    if missing:
        raise SystemExit("Requested skill(s) not found in backup: " + ", ".join(missing))

    for action, src, dest in planned:
        print(f"{action}: {src.name} -> {dest}")

    if args.dry_run:
        print("dry_run=true; no files written")
        return 0

    target_root.mkdir(parents=True, exist_ok=True)
    for action, src, dest in planned:
        if dest.exists():
            backup_dest = backup_root / dest.name
            backup_dest.parent.mkdir(parents=True, exist_ok=True)
            copytree(dest, backup_dest)
        copytree(src, dest)

    print(f"installed={len(planned)}")
    if backup_root.exists():
        print(f"backups={backup_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
#!/usr/bin/env python3
"""Install backed-up Codex skills from my-codex-skills onto another computer."""

from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from pathlib import Path


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def copytree(src: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)


def main() -> int:
    parser = argparse.ArgumentParser(description="Install skills from a skills backup repository.")
    parser.add_argument("--repo-dir", default=".")
    parser.add_argument("--target-skills-root", default=str(Path.home() / ".codex" / "skills"))
    parser.add_argument("--backup-dir", default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    repo_dir = Path(args.repo_dir).expanduser().resolve()
    source_root = repo_dir / "skills"
    target_root = Path(args.target_skills_root).expanduser().resolve()
    backup_root = Path(args.backup_dir).expanduser().resolve() if args.backup_dir else target_root / "_backups" / timestamp()

    if not source_root.exists():
        raise SystemExit(f"Missing source skills directory: {source_root}")

    planned = []
    for skill_dir in sorted(source_root.iterdir()):
        if not skill_dir.is_dir():
            continue
        target = target_root / skill_dir.name
        action = "add" if not target.exists() else "overwrite-with-backup"
        planned.append((action, skill_dir, target))

    for action, src, dest in planned:
        print(f"{action}: {src.name} -> {dest}")

    if args.dry_run:
        print("dry_run=true; no files written")
        return 0

    target_root.mkdir(parents=True, exist_ok=True)
    for action, src, dest in planned:
        if dest.exists():
            backup_dest = backup_root / dest.name
            backup_dest.parent.mkdir(parents=True, exist_ok=True)
            copytree(dest, backup_dest)
        copytree(src, dest)

    print(f"installed={len(planned)}")
    if backup_root.exists():
        print(f"backups={backup_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
