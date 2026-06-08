# skills-backupdate Workflow Reference

## Repository Defaults

- Repository name: `my-codex-skills`.
- Recommended local path: `C:\Users\NotAway\Documents\Codex\my-codex-skills`.
- Repository visibility: private.

## Review Gates

Ask the user before:

- Pushing to GitHub for the first time.
- Creating a GitHub repository.
- Updating a local skill from an upstream GitHub source.
- Uploading files flagged as suspicious or larger than the configured thresholds.
- Enabling periodic automation.

## GitHub Repository Creation

Prefer the GitHub CLI when authenticated:

```powershell
gh auth status
gh repo create <github-account>/my-codex-skills --private --source C:\Users\NotAway\Documents\Codex\my-codex-skills --remote origin
```

If `gh` is missing or unauthenticated, instruct the user to create a private repository named `my-codex-skills` on GitHub, then add it as the local remote.

## Update Checks

The scanner detects source hints but does not mutate skills. `scripts/update_check.py` uses lightweight `git ls-remote` checks for GitHub sources. It does not shallow clone, download full upstream content, or overwrite local skills.

If a possible update is reported, ask the user before any local skill update. Before applying an update, create a timestamped backup of the current skill folder or ensure the skill is recoverable from Git.

## Optimized Backup Flow

Use:

```powershell
python scripts\backup_flow.py --repo-dir C:\Users\NotAway\Documents\Codex\my-codex-skills --skills-root C:\Users\NotAway\.codex\skills --dry-run
```

The flow runs:

1. Lightweight update check.
2. Repository-versus-local skill comparison.
3. Optional install of repository-only skills only when `--install-extra NAME` or `--install-all-extra` is passed.
4. Backup refresh after checks and optional installs.

Default mode minimizes token and storage use by reading only skill metadata, using remote reference checks, avoiding upstream downloads, and cleaning stale skill folders from the backup repository before copying current allowed files.

## Large and Sensitive Files

Default thresholds:

- Single file: 10 MB.
- Single skill folder: 100 MB.

Suspicious files are skipped from copy by default. The user can override manually after reading the risk summary.

## Other Computer Install

Use:

```powershell
python scripts\install_skills.py --repo-dir . --target-skills-root "$env:USERPROFILE\.codex\skills" --dry-run
python scripts\install_skills.py --repo-dir . --target-skills-root "$env:USERPROFILE\.codex\skills"
```

The install script backs up conflicting target skill folders and never deletes target-only skills.

## Pull and Apply Mode

For a cloned `my-codex-skills` repository on another computer, use:

```powershell
python scripts\sync_skills.py pull --repo-dir .
python scripts\sync_skills.py apply --repo-dir . --target-skills-root "$env:USERPROFILE\.codex\skills"
```

`apply` defaults to a dry-run. To write changes after reviewing the plan:

```powershell
python scripts\sync_skills.py apply --repo-dir . --target-skills-root "$env:USERPROFILE\.codex\skills" --confirm
```

The mode uses `git pull --ff-only`, so it stops instead of creating merge commits when the local backup repo has divergent commits.
