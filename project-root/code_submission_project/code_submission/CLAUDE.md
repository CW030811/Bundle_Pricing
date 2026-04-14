# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Mixed Bundling Pricing Problem (MBPP) solver — an ML-augmented operations research system that combines a Graph Convolutional Network (GCN) for initial bundle predictions with hybrid MILP/LP optimization and local search for solution refinement. The goal is to find optimal product bundles and pricing for customer segments to maximize revenue.

**Problem parameters**: m customer segments, n products, with unit costs, shipping costs, customer utility matrices, and segment sizes as inputs.

## Environment Setup

- **Current environment**: `code_submission/.venv` (Python 3.9 series in the current workspace)
- **Activation**: `source .venv/bin/activate`
- **Historical Windows flow**: `pyg311` + `chcp 65001` belongs to an older workflow and should not be treated as the default
- **Gurobi license** must be configured (used for MILP/LP solving)
- **Key dependencies**: PyTorch, PyTorch Geometric (GENConv), Gurobi, NumPy, msgpack

```bash
source .venv/bin/activate
```

## Running Core Strategies

```bash
# Global Top-K Local Search (primary innovation, K = ceil(sqrt(m)))
python src/test/LS_Path_Test.py

# Original FCP + Local Search (baseline, 2*m neighbors per iteration)
python src/test/test_FCP_LS.py

# FCP — threshold-based prediction + single MILP solve
python src/test/test_FCP.py

# PCP — progressive bundle chains + MILP
python src/test/test_PCP.py

# Bundle Size Pricing
python src/test/test_BSP.py
```

Historical batch scripts are kept only for old Windows sessions and may point to outdated root-level paths.

## Data Generation

```bash
python src/data/generate_data_MB.py     # Mixed Bundling datasets
python src/data/generate_data_BSP.py    # Bundle Size Pricing datasets
python src/data/run_cpbsd_baselines_v2.py
```

Datasets are `.msgpack` files in `Dataset/` with fields: `product_num`, `segment_num`, `unit_cs`, `ship_cs`, `unit_us`, `Ns`, `opt_bundles`, `opt_prices`, `opt_rev`.

## Architecture

### Pipeline Flow

```
EdgeScoringGCN inference (bipartite graph: products <-> segments)
    -> Probability matrix P[m,n]
    -> Bundle prediction via threshold (pred_assort[k,j] = 1 if P[k,j] >= threshold)
    -> Initial MILP solve (baseline revenue)
    -> Local Search loop (LP-based neighbor evaluation, greedy acceptance)
    -> Final MILP verification
```

### Key Files

| File | Purpose |
|------|---------|
| `src/test/LS_Path_Test.py` | Global Top-K local search strategy — generates at most 2*K neighbors (K=ceil(sqrt(m))) instead of 2*m, reducing LP calls by ~64% |
| `src/test/test_FCP_LS.py` | Original local search + all shared utility functions (MILP solver, LP solver, neighbor generation, GCN inference) |
| `src/test/test_FCP.py` | Fixed Choice Prediction — threshold method + single MILP |
| `src/test/test_PCP.py` | Progressive Choice Prediction — Top-M selection + progressive bundle chains |
| `src/test/test_BSP.py` | Bundle Size Pricing strategy |
| `src/train/Training_edge-final.py` | GCN model training (EdgeScoringGCN with GENConv layers) |
| `best_model_edge.pt` | Trained model weights |
| `src/data/generate_data_MB.py` / `src/data/generate_data_BSP.py` | Dataset generators using Gurobi for optimal solutions |
| `src/data/run_cpbsd_baselines_v2.py` | Current CPBSD smoke / sanity-check entry |

### GCN Model (EdgeScoringGCN)

- Input: 4 features per node, bipartite graph of products and segments
- 2 directional GENConv stacks (left-to-right + right-to-left), hidden_channels=128
- Edge scoring via bilinear attention: `s_e = h_src^T U h_dst`
- Loss: BCEWithLogitsLoss on per-edge probabilities
- Training script requires `bundle_utils.read_data` for data loading

### Optimization Solvers

- **MILP**: Full optimization with Gurobi (MIPGap=1e-2, TimeLimit=600s)
- **LP**: Fast approximation for neighbor evaluation during local search (Method=-1 auto, Presolve=2)
- Local search stopping: max_iterations=50, tolerance=1e-6

## Key Configuration Points

Dataset paths and solver parameters are hardcoded in each script:
- Dataset dict in `src/test/test_FCP_LS.py` and `src/test/LS_Path_Test.py`
- Model path: `best_model_edge.pt` (same directory as scripts)
- Top-K formula in `src/test/LS_Path_Test.py`: `K = int(ceil(sqrt(m)))`
- Max samples per dataset: `max_samples_per_dataset = 1000`

## Analysis Scripts

Multiple `analyze_*.py` and `compare_*.py` scripts generate CSV results and comparison reports. Key entry points:
- `analyze_all_results.py` — aggregate analysis across strategies
- `compare_strategies_m10n10.py` — head-to-head strategy comparison

## Language Note

Documentation files (`.md`) and code comments are primarily in Chinese. Variable names and function signatures use English.
