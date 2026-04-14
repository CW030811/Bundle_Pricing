# Revenue-management Environment Status

## Current primary environment
- Path: `domains/revenue-management/project-root/code_submission_project/code_submission/.venv`
- Activation: `source domains/revenue-management/project-root/code_submission_project/code_submission/.venv/bin/activate`

## Current status note
- This file tracks the current recommended environment, not the historical migration log.
- Legacy backup environments and archived experiment copies may have been moved out of the workspace after cleanup.

## Dependency status
- No dependency definition file was found in the project root (requirements.txt / pyproject.toml / setup.py / environment.yml / Pipfile).
- The workspace still relies on the live `.venv` plus script defaults; no formal lockfile exists yet.

## Recommended default
- Use the new primary environment under `domains/revenue-management/.../code_submission/`.
- Run scripts from the `code_submission` root when relative paths are involved.

## Verified imports in current `.venv`
- OK: `numpy`, `pandas`, `msgpack`, `msgpack_numpy`, `tqdm`
- OK: `gurobipy`, `torch`, `torch_geometric`, `matplotlib`
- Validation basis: direct import check in the current workspace on 2026-03-21

## Gurobi Python binding
- gurobipy installed
- Import and minimal solve: OK
- License/config still matters at runtime; see `project-root/GUROBI_ACADEMIC_LICENSE_SETUP_2026-03-04.md`

## Practical dependency set
- Core numerical/data: `numpy`, `pandas`, `msgpack`, `msgpack_numpy`, `tqdm`
- Solver: `gurobipy`
- ML / graph stack: `torch`, `torch_geometric`
- Plotting / reporting: `matplotlib`

## Remaining gap
- The main risk is not missing imports now.
- The real gap is the absence of a canonical dependency file (`requirements.txt`, `pyproject.toml`, or `environment.yml`).
