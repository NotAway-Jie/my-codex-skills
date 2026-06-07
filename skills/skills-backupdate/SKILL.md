---
name: skills-backupdate
description: Back up, document, and synchronize the user's personal Codex skills to a private GitHub repository. Use when the user asks to scan existing skills, explain what each skill does, create or update a private skills backup repository, prepare GitHub sync artifacts, check GitHub-sourced skills for available updates, install skills on another computer, or configure a future recurring skills backup/check workflow.
---

# Skills Backupdate

Use this skill to maintain the user's personal Codex skills with a conservative, review-first workflow. The default repository is a private GitHub repo named `my-codex-skills`.

## Core Rules

- Manage personal skills under `C:\Users\NotAway\.codex\skills`.
- Include this skill, `skills-backupdate`, in backups.
- Do not modify `.system` skills or plugin cache skills.
- Do not store GitHub tokens, passwords, cookies, sessions, or credentials.
- Prefer manual trigger. Do not create recurring automation unless the user explicitly asks and provides a schedule.
- Generate reports before changing local skills, updating GitHub-sourced skills, or pushing risky content.
- Treat GitHub-sourced skill updates as review-first: report available updates, then wait for explicit confirmation before changing files.

## Quick Start

For a normal scan and sync preparation:

```powershell
python C:\Users\NotAway\.codex\skills\skills-backupdate\scripts\prepare_sync.py --skills-root C:\Users\NotAway\.codex\skills --repo-dir C:\Users\NotAway\Documents\Codex\my-codex-skills
```

If the bundled Codex Python is needed, use:

```powershell
C:\Users\NotAway\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe C:\Users\NotAway\.codex\skills\skills-backupdate\scripts\prepare_sync.py --skills-root C:\Users\NotAway\.codex\skills --repo-dir C:\Users\NotAway\Documents\Codex\my-codex-skills
```

The command creates or refreshes a local repo-shaped folder with:

- `skills/` copied personal skill sources.
- `docs/SKILLS_INDEX.md` human-readable skill index.
- `docs/UPDATE_REPORT.md` GitHub source and update-status report.
- `docs/SYNC_GUIDE.md` instructions for another computer.
- `manifest/skills-manifest.json` and `manifest/file-inventory.json` for incremental review.
- `scripts/install_skills.py` for dry-run and install on another computer.

## Workflow

1. Run `scripts/prepare_sync.py` in dry-run or normal mode.
2. Review the risk summary in terminal and generated reports.
3. If a private GitHub repo does not exist, check `gh auth status`.
4. If authenticated, create the private repo with `gh repo create <account>/my-codex-skills --private`.
5. Initialize or reuse the local repo directory, commit generated artifacts, and push only after reviewing sensitive and large-file warnings.
6. When the user asks to check updates, use `docs/UPDATE_REPORT.md` to show GitHub-sourced skills and ask before updating any local skill.
7. When the user asks to enable a schedule, use the app's automation tool to create the requested recurrence. Keep manual trigger available.

## Script Tasks

- `scripts/scan_skills.py`: scan personal skills, summarize `SKILL.md`, detect GitHub source hints, hash allowed files, and flag skipped/suspicious files.
- `scripts/prepare_sync.py`: build the local repository structure and copy safe skill files.
- `scripts/install_skills.py`: install backed-up skills onto another computer with `--dry-run` and backup-before-overwrite behavior.

For detailed operating guidance, read `references/workflow.md` only when needed.
