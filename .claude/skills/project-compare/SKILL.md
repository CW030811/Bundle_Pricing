---
name: project-compare
description: Compare the canonical CPBSD codebase in code_submission with outputs or legacy/reference directories before making changes. Use this when analyzing training entry points, solver scripts, data generation, label pipelines, adaptation gaps, or directory roles.
---

# project-compare

## Purpose
This skill compares the canonical CPBSD codebase with experiment outputs or legacy/reference directories.

Use it to:
- identify where active CPBSD logic really lives
- compare current code against legacy/reference implementations
- locate adaptation gaps for CPBSD-GCN tasks
- determine whether a directory is active code, output-only, or legacy
- produce a safe comparison before code changes

## Canonical Scope
Active code:
- `code_submission`

Active output:
- `experiments`

Legacy / reference-only unless explicitly requested:
- `CPBSD_GCN_acceleration_experiment`
- archived or nested result-heavy experiment snapshot directories

Do not edit files by default. This is an analysis and comparison skill unless the user explicitly asks for code changes.

## Directory Identification Rules
When determining whether a directory is active code, prioritize whether it contains:
1. solver scripts
2. data generation scripts
3. training entry scripts
4. label generation / queue scripts
5. current environment files such as `.venv`

If a directory mainly contains json/csv/png/msgpack/pt outputs and lacks the above entry scripts, treat it as output-only or legacy by default.

## Comparison Rules
When using this skill:
1. First identify the target functionality, module, or directory role to compare.
2. Read relevant files from `code_submission`.
3. Read corresponding files from `experiments` or legacy/reference directories only if relevant.
4. Explain similarities and differences clearly.
5. Separate:
   - active canonical logic
   - output-only artifacts
   - legacy/reference logic
   - missing adaptation points
   - unclear / risky areas
6. Prefer concrete file-level comparison over vague summaries.
7. If file mapping is uncertain, say so explicitly.

## Focus for CPBSD Tasks
Pay special attention to:
- data generation
- solver scripts
- label generation
- queue / manifest pipeline
- training entry scripts
- node features
- edge features
- data loading
- graph construction compatibility
- model input/output assumptions

Unless explicitly requested, do NOT recommend changing:
- model architecture
- training loop
- loss function
- output format

## Output Format
Always report in this structure:

### Comparison Target
What functionality, module, or directory role is being compared

### Files Read
List files from:
- `code_submission`
- `experiments` and/or legacy/reference directories if used

### Active Canonical Logic
What appears to be part of the current main CPBSD pipeline

### Legacy / Output-only Findings
What appears to be archived, duplicated, output-only, or no longer the main execution path

### Missing Adaptation Points
What still seems incompatible, missing, or unfinished

### Risk Notes
Any uncertainty, file mapping ambiguity, or likely breakpoints

### Suggested Next Read / Next Edit
What file or module should be inspected or changed next
