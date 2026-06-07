# Sync Guide

## First Computer

1. Run `scripts/prepare_sync.py` from the `skills-backupdate` skill.
2. Review `docs/SKILLS_INDEX.md`, `docs/UPDATE_REPORT.md`, and `manifest/file-inventory.json`.
3. Create a private GitHub repo named `my-codex-skills` if it does not exist.
4. Commit and push only after reviewing large and suspicious file warnings.

## Other Computer

Clone the private repo, then dry-run the installer:

```powershell
python scripts\install_skills.py --repo-dir . --target-skills-root "$env:USERPROFILE\.codex\skills" --dry-run
```

If the dry-run looks correct:

```powershell
python scripts\install_skills.py --repo-dir . --target-skills-root "$env:USERPROFILE\.codex\skills"
```

The installer backs up conflicting target skill folders and does not delete local-only skills.
