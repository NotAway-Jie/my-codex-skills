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

The scanner detects source hints but does not mutate skills. If a skill has a GitHub URL, compare local files with upstream only after user approval. Before applying an update, create a timestamped backup of the current skill folder or ensure the skill is recoverable from Git.

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
