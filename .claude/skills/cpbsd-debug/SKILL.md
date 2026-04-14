---
name: cpbsd-debug
description: Diagnose CPBSD or CPBSD-GCN code issues in the canonical code_submission directory with minimal edits and minimal-scope validation. Use this for stack traces, shape mismatches, data-format incompatibilities, missing scripts, broken imports, pipeline failures, and training-entry debugging.
---

# cpbsd-debug

## Purpose
This skill is for debugging CPBSD / CPBSD-GCN issues in the revenue-management project.

Use it when:
- there is a Python error, stack trace, import failure, or runtime crash
- a CPBSD data pipeline step fails
- solver / label / queue / manifest scripts break
- training entry scripts fail
- node feature / edge feature / data loading assumptions are inconsistent
- shape mismatch, key error, file-not-found, or compatibility issues appear

## Canonical Scope
Default editable code area:
- `code_submission`

Default output / artifact area:
- `experiments`

Legacy / reference-only unless explicitly requested:
- `CPBSD_GCN_acceleration_experiment`
- archived result-heavy snapshot directories

Do not edit legacy/reference directories by default.

## Debugging Rules
When using this skill:
1. First identify the exact failing command, file, or traceback.
2. Prefer evidence over guessing.
3. State the most likely failure point before editing code.
4. Prefer the smallest possible fix.
5. Do not broaden the scope silently.
6. Do not refactor unrelated code.
7. If multiple files may be involved, explain why.
8. Always validate with the smallest possible smoke test before any larger run.

## CPBSD Priorities
Prioritize checking:
- training entry script assumptions
- data loading and schema compatibility
- node feature and edge feature dimensions
- solver / label generation dependencies
- manifest / queue pipeline expectations
- file paths and environment assumptions
- imports and module paths

Unless explicitly requested, do NOT change:
- model architecture
- training loop
- loss function
- output format

## Before Editing
Always state:
- target file(s)
- exact symptom
- most likely root cause
- whether the planned fix is minimal or structural

## Validation Rules
- Run the smallest possible reproducer or smoke test first
- Do not launch long experiments unless explicitly requested
- If validation fails, report the new failure clearly before making additional edits
- Do not claim success without showing the validation command and result

## Output Format
Always report in this structure:

### Symptom
What failed

### Evidence
Relevant traceback, command, file path, or observed mismatch

### Likely Root Cause
Most likely reason for the failure

### Planned Fix
Which file(s) will be changed and why

### Validation
What minimal command or check was run, and what happened

### Remaining Risks / Next Step
What is still uncertain or what should be checked next
