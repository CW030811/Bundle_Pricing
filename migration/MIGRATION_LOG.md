# Revenue-management Migration Log (Step5C)

> Note: this file is a point-in-time migration log. Entries such as `.venv_legacy_migrated_backup`, `experiments/cpbsd_baselines/`, and the earlier `torch/torch_geometric` install failure describe historical migration state only; current environment and active paths should defer to `migration/ENVIRONMENT_STATUS.md`, the domain `README.md`, and the live workspace layout.

## Moved paths
- /Users/sensen/.openclaw/workspace/revenue-management/* (excluding .venv, .DS_Store)
  -> domains/revenue-management/project-root/
- /Users/sensen/.openclaw/workspace/experiments/cpbsd_baselines/
  -> domains/revenue-management/experiments/cpbsd_baselines/
- /Users/sensen/.openclaw/workspace/memory/projects/revenue-management/
  -> domains/revenue-management/legacy-memory/project-memory/
- /Users/sensen/.openclaw/workspace/memory/revenue-management.md
  -> domains/revenue-management/legacy-memory/revenue-management.md

## Skipped
- /Users/sensen/.openclaw/workspace/revenue-management/.venv (path-sensitive env)
- /Users/sensen/.openclaw/workspace/revenue-management/.DS_Store

## Notes
- No content cleanup performed.
- Old paths remain only for skipped environment items.

## Environment rebuild (Step5E)
- New primary env root: domains/revenue-management/project-root/code_submission_project/code_submission/
- Existing migrated .venv renamed: .venv -> .venv_legacy_migrated_backup
- New clean .venv created at: domains/revenue-management/project-root/code_submission_project/code_submission/.venv
- Dependency file found: none (requirements/pyproject/setup/environment/Pipfile not found)
- Validation: python/pip ok
- Old legacy env preserved at: /Users/sensen/.openclaw/workspace/revenue-management/.venv

## Dependency install (low-risk core)
- Installed: numpy, pandas, msgpack, msgpack_numpy, tqdm
- Validation: import ok
- High-risk still pending: gurobipy, torch, torch_geometric

## Dependency install (gurobipy)
- Installed: gurobipy
- Validation: import ok, minimal solve ok
- High-risk pending: torch, torch_geometric

## Dependency install (torch & torch_geometric) — FAILED
- Attempted: torch, torch_geometric
- Failure stage: torch download/verification
- Error: ProxyError (503 tunnel) and wheel hash mismatch for torch-2.8.0 (cp39 macosx_11_0_arm64)
- Result: torch/torch_geometric not installed
