# Sync Guide

## First Computer

1. Run `scripts/backup_flow.py` from the `skills-backupdate` skill.
2. Review `docs/LOCAL_UPDATE_CHECK.md`, `docs/SKILLS_INDEX.md`, `docs/UPDATE_REPORT.md`, and `manifest/file-inventory.json`.
3. Confirm any local skill updates or repository-only skill installs before applying them.
4. Create a private GitHub repo named `my-codex-skills` if it does not exist.
5. Commit and push only after reviewing large and suspicious file warnings.

Preview the optimized workflow:

```powershell
python C:\Users\NotAway\.codex\skills\skills-backupdate\scripts\backup_flow.py --skills-root C:\Users\NotAway\.codex\skills --repo-dir C:\Users\NotAway\Documents\Codex\my-codex-skills --dry-run
```

Run the workflow:

```powershell
python C:\Users\NotAway\.codex\skills\skills-backupdate\scripts\backup_flow.py --skills-root C:\Users\NotAway\.codex\skills --repo-dir C:\Users\NotAway\Documents\Codex\my-codex-skills
```

## Other Computer

Clone the private repo, then dry-run the installer:

```powershell
python scripts\install_skills.py --repo-dir . --target-skills-root "$env:USERPROFILE\.codex\skills" --dry-run
```

If the dry-run looks correct:

```powershell
python scripts\install_skills.py --repo-dir . --target-skills-root "$env:USERPROFILE\.codex\skills"
```

Install only selected skills with repeated `--skill` flags:

```powershell
python scripts\install_skills.py --repo-dir . --target-skills-root "$env:USERPROFILE\.codex\skills" --skill skills-backupdate --dry-run
```

The installer backs up conflicting target skill folders and does not delete local-only skills.

## Pull and Apply

After the repo is cloned, preview the latest backup on another computer with:

```powershell
python scripts\sync_skills.py apply --repo-dir . --target-skills-root "$env:USERPROFILE\.codex\skills"
```

This command runs `git pull --ff-only` and then dry-runs the installer.

To write changes after reviewing the plan:

```powershell
python scripts\sync_skills.py apply --repo-dir . --target-skills-root "$env:USERPROFILE\.codex\skills" --confirm
```

## Check Upstream Sources

Check detected GitHub sources without applying updates:

```powershell
python scripts\update_check.py --skills-root "$env:USERPROFILE\.codex\skills"
```
