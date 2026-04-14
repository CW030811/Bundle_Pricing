# CPBSD / Revenue Management Project Guide

## Scope
This Claude session is for the revenue-management domain only.

## Canonical Directories
Main code directory:
- code_submission

Main experiment output directory:
- experiments

Legacy / reference-only unless explicitly requested:
- CPBSD_GCN_acceleration_experiment
- archived or nested experiment snapshot directories that mainly contain results

## Directory Roles
- Treat `code_submission` as the canonical CPBSD / CPBSD-GCN codebase.
- Default location for solver, data generation, training entry, label generation, queue logic, and main pipeline scripts is `code_submission`, especially under `src/data`.
- Treat `experiments` as the canonical output area for new experiment results, logs, manifests, labels, plots, and artifacts.
- Do not treat legacy snapshot folders as active execution directories unless explicitly instructed.

## Active-Code Identification Rule
When deciding whether a directory is an active code area, prioritize whether it contains:
1. solver scripts
2. data generation scripts
3. training entry scripts
4. label generation / queue scripts
5. current environment files such as `.venv`

If a directory mainly contains json/csv/png/msgpack/pt outputs and lacks the above entry scripts, treat it as output-only or legacy by default.

## Working Style
- Prefer minimal changes over refactoring.
- Do not silently broaden task scope.
- Before editing training logic, first identify the canonical active code path.
- If the requested change may affect multiple modules, first explain the affected files.

## CPBSD Task Rules
For CPBSD-GCN acceleration tasks:
- focus first on data loading, node features, edge features, compatibility layers, training entry assumptions, and label/data pipeline alignment
- do not change model architecture, training loop, loss function, or output format unless explicitly requested
- run the smallest possible smoke test before larger experiments
- avoid launching long full experiments unless explicitly requested

## File Safety
Default editable area:
- `code_submission`

Default output / artifact area:
- `experiments`

Default reference-only area:
- `CPBSD_GCN_acceleration_experiment`
- archived result-heavy directories

Before modifying any legacy/reference directory, explain:
1. why the canonical code directory is insufficient
2. which exact file will be changed
3. what downstream risk exists

## Response Requirements
Before each edit, state:
- target file(s)
- why they need to change
- whether the change is minimal or structural

After each coding task, report:
- Summary
- Files changed
- Purpose of each change
- Validation performed
- Remaining risks / next step

## Validation
For each coding task:
1. run the smallest possible smoke test first
2. preserve existing outputs unless instructed otherwise
3. if a test fails, diagnose before expanding the scope of edits
4. do not claim success without showing the validation command and result

## Important Paths
- /Users/sensen/.openclaw/workspace/domains/revenue-management/code_submission
- /Users/sensen/.openclaw/workspace/domains/revenue-management/experiments
- /Users/sensen/.openclaw/workspace/domains/revenue-management/CPBSD_GCN_acceleration_experiment
