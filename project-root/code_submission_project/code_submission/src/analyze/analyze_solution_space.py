"""
Solution-space complexity analysis for MILP/FCP/PCP strategies.
"""

import argparse
import os
import re
import time
from itertools import combinations

import gurobipy as gp
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
from gurobipy import GRB

from test_FCP import EdgeScoringGCN, bundle_to_product_set, process_data
from test_PCP import generate_progressive_bundles, top_m_selection

matplotlib.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False

DATASET_DIR_MAP = {
    "m10n10": "m10_n10_sample_100",
    "m20n10": "m20_n10_sample_100",
    "m30n10": "m30_n10_sample_100",
    "m10n20_BSP": "test_BSP_m10n20_1e_3",
    "m10n40_BSP": "test_BSP_m10n40_1e_3",
}
# Custom base path (relative to script_dir); default "Dataset" when not in map
DATASET_BASE_MAP = {
    "m10n20_BSP": "dataset2_4_2026",
    "m10n40_BSP": "dataset2_4_2026",
}
STRATEGIES = ["MILP", "FCP", "PCP"]
SUBADD_PREFIX = "subadd_"

bin2num = lambda x: int("".join(map(str, x.tolist())), 2)


def get_gurobi_model_stats(model):
    return {
        "num_vars": model.NumVars,
        "num_constrs": model.NumConstrs,
        "num_nzs": model.NumNZs,
        "num_bin_vars": model.NumBinVars,
        "num_int_vars": model.NumIntVars,
    }


def count_subadditivity_from_model(model):
    return sum(
        1
        for c in model.getConstrs()
        if getattr(c, "ConstrName", "") and c.ConstrName.startswith(SUBADD_PREFIX)
    )


def _apply_gurobi_logging_params(model, output_flag=1, log_file=None):
    model.Params.OutputFlag = int(output_flag)
    if int(output_flag) == 1:
        model.Params.LogToConsole = 1
    if log_file:
        log_dir = os.path.dirname(log_file)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        model.Params.LogFile = log_file


def _optimize_for_stats_and_validate_log(
    model,
    optimize_for_stats=True,
    stats_time_limit=0.0,
    log_file=None,
    output_flag=1,
):
    if not optimize_for_stats:
        return False

    if stats_time_limit is not None:
        model.Params.TimeLimit = max(0.0, float(stats_time_limit))

    model.optimize()

    if int(output_flag) == 1 and log_file:
        try:
            with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                txt = f.read()
            return bool(
                re.search(
                    r"Optimize a model with\s+\d+\s+rows,\s+\d+\s+columns\s+and\s+\d+\s+nonzeros",
                    txt,
                )
            )
        except OSError:
            return False
    return True


def _build_strategy_log_file(logs_dir, dataset_name, sample_name, strategy):
    sample_stem = os.path.splitext(os.path.basename(sample_name))[0]
    return os.path.join(logs_dir, dataset_name, f"{sample_stem}_{strategy}.log")


def _resolve_dataset_path(script_dir, dataset_name):
    base = DATASET_BASE_MAP.get(dataset_name, "Dataset")
    subdir = DATASET_DIR_MAP[dataset_name]
    return os.path.join(script_dir, base, subdir)


def _resolve_model_path(script_dir):
    model_paths = [
        os.path.join(script_dir, "best_model_edge.pt"),
        os.path.join(script_dir, "models_multi_layer_edge_update", "model_edge_4layer_seed1.pt"),
    ]
    for path in model_paths:
        if os.path.exists(path):
            return path
    return None


def _load_gcn_model(model_path):
    import __main__

    if not hasattr(__main__, "EdgeScoringGCN"):
        __main__.EdgeScoringGCN = EdgeScoringGCN

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = torch.load(model_path, map_location=device, weights_only=False)
    model.to(device)
    model.eval()
    if not hasattr(model, "forward"):
        raise AttributeError("Loaded model missing 'forward' method")
    return model, device


def _extract_nm_logits_or_probs(raw_out, n, m):
    if isinstance(raw_out, dict):
        if "logit_matrix" in raw_out:
            return raw_out["logit_matrix"].detach().cpu().numpy()
        if "edge_logits" in raw_out:
            return raw_out["edge_logits"].detach().cpu().numpy().reshape(n, m)
        raise ValueError("Unexpected model output keys.")
    return raw_out[:n, :].detach().cpu().numpy()


def analyze_milp_strategy(
    n,
    m,
    unit_cs,
    ship_cs,
    unit_us,
    Ns,
    output_flag=1,
    optimize_for_stats=True,
    stats_time_limit=0.0,
    log_file=None,
):
    build_start = time.time()

    B = 2 ** n
    segment_ind = np.arange(m)
    bundle_ind = np.arange(B)

    assortments = np.array([list(map(int, format(num, f"0{n}b"))) for num in range(B)], dtype=int)
    costs = (np.sum(assortments * unit_cs, axis=1) + ship_cs) * 0.2
    Rs = np.sqrt(unit_us.dot(assortments.T))
    Rbar = np.max(Rs)

    model = gp.Model("Bundle MILP")
    _apply_gurobi_logging_params(model, output_flag=output_flag, log_file=log_file)

    p = model.addVars(B, vtype=GRB.CONTINUOUS, lb=0, name="p")
    theta = model.addVars(m, B, vtype=GRB.BINARY, name="theta")
    s = model.addVars(m, vtype=GRB.CONTINUOUS, name="s")
    S = model.addVars(m, B, vtype=GRB.CONTINUOUS, lb=0, name="S")
    Z = model.addVars(m, B, vtype=GRB.CONTINUOUS, name="Z")
    P = model.addVars(m, B, vtype=GRB.CONTINUOUS, lb=0, name="P")

    model.setObjective(gp.quicksum(Ns[k, 0] * Z[k, i] for k in segment_ind for i in bundle_ind), GRB.MAXIMIZE)
    model.addConstrs((s[k] >= Rs[k, i] - p[i] for i in bundle_ind for k in segment_ind))

    for i in bundle_ind:
        tmp_assort = assortments[i, :]
        set_inds = np.where(tmp_assort)[0]
        for num in range(1, int(sum(tmp_assort)) // 2 + 1):
            for inds in combinations(set_inds, num):
                assort1 = np.zeros(n, dtype=int)
                assort1[list(inds)] = 1
                assort2 = tmp_assort - assort1
                b1, b2 = bin2num(assort1), bin2num(assort2)
                model.addConstr(
                    p[bin2num(tmp_assort)] <= p[b1] + p[b2],
                    name=f"{SUBADD_PREFIX}{bin2num(tmp_assort)}_{b1}_{b2}",
                )

    model.addConstrs((P[k, i] >= p[i] - Rbar * (1 - theta[k, i]) for i in bundle_ind for k in segment_ind))
    model.addConstrs((P[k, i] <= p[i] for i in bundle_ind for k in segment_ind))
    model.addConstrs((s[k] >= gp.quicksum(Rs[k, i] * theta[j, i] - P[j, i] for i in bundle_ind) for k in segment_ind for j in segment_ind))
    model.addConstrs((Z[k, i] == P[k, i] - costs[k, i] * theta[k, i] for i in bundle_ind for k in segment_ind))
    model.addConstrs((S[k, i] == Rs[k, i] * theta[k, i] - P[k, i] for i in bundle_ind for k in segment_ind))
    model.addConstrs((s[k] == gp.quicksum(S[k, i] for i in bundle_ind) for k in segment_ind))
    model.addConstrs((gp.quicksum(theta[k, i] for i in bundle_ind) == 1 for k in segment_ind))
    model.addConstrs((S[k, 0] == 0 for k in segment_ind))

    model.update()
    build_time = time.time() - build_start

    logged_ok = _optimize_for_stats_and_validate_log(
        model,
        optimize_for_stats=optimize_for_stats,
        stats_time_limit=stats_time_limit,
        log_file=log_file,
        output_flag=output_flag,
    )

    stats = get_gurobi_model_stats(model)
    return {
        "strategy": "MILP",
        "bundle_space_size": B,
        "total_variables": stats["num_vars"],
        "total_constraints": stats["num_constrs"],
        "num_nzs": stats["num_nzs"],
        "num_bin_vars": stats["num_bin_vars"],
        "subadditivity_constraints": count_subadditivity_from_model(model),
        "build_time": build_time,
        "gurobi_log_file": log_file or "",
        "gurobi_model_scale_logged": bool(logged_ok),
    }


def analyze_fcp_strategy(
    n,
    m,
    unit_cs,
    ship_cs,
    unit_us,
    Ns,
    gcn_model,
    graph_data,
    device,
    output_flag=1,
    optimize_for_stats=True,
    stats_time_limit=0.0,
    log_file=None,
):
    gcn_model.eval()
    with torch.no_grad():
        graph_data = graph_data.to(device)
        raw_out = gcn_model(graph_data)
        logits_nm = _extract_nm_logits_or_probs(raw_out, n, m)
        if isinstance(raw_out, dict):
            pred_assort = (logits_nm.T >= 0.0).astype(int)
        else:
            pred_assort = (np.exp(logits_nm) / (np.exp(logits_nm) + np.exp(1)) >= 0.5).astype(int).T

    bundle_dic = {}
    for i in range(m):
        bundle_idx = bin2num(pred_assort[i, :])
        bundle_dic.setdefault(bundle_idx, []).append(i)
    predicted_bundles = list(bundle_dic.keys())

    predicted_assortments = np.array([list(map(int, format(bundle_id, f"0{n}b"))) for bundle_id in predicted_bundles])
    Rs_predicted = np.sqrt(unit_us.dot(predicted_assortments.T))
    cs_base = np.sum(predicted_assortments * unit_cs, axis=1)
    cs_predicted = (cs_base + ship_cs) * 0.2
    bundle_to_idx = {bundle_id: idx for idx, bundle_id in enumerate(predicted_bundles)}
    Rbar = np.max(Rs_predicted)

    build_start = time.time()
    model = gp.Model("Bundle MILP")
    _apply_gurobi_logging_params(model, output_flag=output_flag, log_file=log_file)
    model.Params.MIPGap = 1e-2

    segment_ind = np.arange(m)
    p = model.addVars(predicted_bundles, vtype=GRB.CONTINUOUS, lb=0, name="p")
    theta = model.addVars(m, predicted_bundles, vtype=GRB.BINARY, name="theta")
    s = model.addVars(m, vtype=GRB.CONTINUOUS, name="s")
    S = model.addVars(m, predicted_bundles, vtype=GRB.CONTINUOUS, lb=0, name="S")
    Z = model.addVars(m, predicted_bundles, vtype=GRB.CONTINUOUS, name="Z")
    P = model.addVars(m, predicted_bundles, vtype=GRB.CONTINUOUS, lb=0, name="P")

    model.setObjective(gp.quicksum(Ns[k, 0] * Z[k, i] for k in segment_ind for i in predicted_bundles), GRB.MAXIMIZE)
    model.addConstrs((s[k] >= Rs_predicted[k, bundle_to_idx[i]] - p[i] for i in predicted_bundles for k in segment_ind))

    bundle_product_sets = {bundle_id: bundle_to_product_set(bundle_id, n) for bundle_id in predicted_bundles}
    for k in predicted_bundles:
        if k == 0:
            continue
        k_set = bundle_product_sets[k]
        if len(k_set) == 0:
            continue
        for i in predicted_bundles:
            for j in predicted_bundles:
                if i >= j:
                    continue
                i_set = bundle_product_sets[i]
                j_set = bundle_product_sets[j]
                union_set = i_set.union(j_set)
                if k_set.issubset(union_set) and k_set != i_set and k_set != j_set:
                    model.addConstr(p[k] <= p[i] + p[j], name=f"{SUBADD_PREFIX}{k}_{i}_{j}")

    model.addConstrs((P[k, i] >= p[i] - Rbar * (1 - theta[k, i]) for i in predicted_bundles for k in segment_ind))
    model.addConstrs((P[k, i] <= p[i] for i in predicted_bundles for k in segment_ind))
    model.addConstrs((s[k] >= gp.quicksum(Rs_predicted[k, bundle_to_idx[i]] * theta[j, i] - P[j, i] for i in predicted_bundles) for k in segment_ind for j in segment_ind))
    model.addConstrs((Z[k, i] == P[k, i] - cs_predicted[k, bundle_to_idx[i]] * theta[k, i] for i in predicted_bundles for k in segment_ind))
    model.addConstrs((S[k, i] == Rs_predicted[k, bundle_to_idx[i]] * theta[k, i] - P[k, i] for i in predicted_bundles for k in segment_ind))
    model.addConstrs((s[k] == gp.quicksum(S[k, i] for i in predicted_bundles) for k in segment_ind))
    model.addConstrs((gp.quicksum(theta[k, i] for i in predicted_bundles) == 1 for k in segment_ind))
    if 0 in predicted_bundles:
        model.addConstrs((S[k, 0] == 0 for k in segment_ind))

    model.update()
    build_time = time.time() - build_start

    logged_ok = _optimize_for_stats_and_validate_log(
        model,
        optimize_for_stats=optimize_for_stats,
        stats_time_limit=stats_time_limit,
        log_file=log_file,
        output_flag=output_flag,
    )

    stats = get_gurobi_model_stats(model)
    return {
        "strategy": "FCP",
        "bundle_space_size": len(predicted_bundles),
        "total_variables": stats["num_vars"],
        "total_constraints": stats["num_constrs"],
        "num_nzs": stats["num_nzs"],
        "num_bin_vars": stats["num_bin_vars"],
        "subadditivity_constraints": count_subadditivity_from_model(model),
        "build_time": build_time,
        "gurobi_log_file": log_file or "",
        "gurobi_model_scale_logged": bool(logged_ok),
    }


def analyze_pcp_strategy(
    n,
    m,
    unit_cs,
    ship_cs,
    unit_us,
    Ns,
    gcn_model,
    graph_data,
    device,
    output_flag=1,
    optimize_for_stats=True,
    stats_time_limit=0.0,
    log_file=None,
):
    gcn_model.eval()
    with torch.no_grad():
        graph_data = graph_data.to(device)
        raw_out = gcn_model(graph_data)
        logits_nm = _extract_nm_logits_or_probs(raw_out, n, m)
        if isinstance(raw_out, dict):
            sigmoid_output = 1.0 / (1.0 + np.exp(-logits_nm))
        else:
            sigmoid_output = np.exp(logits_nm) / (np.exp(logits_nm) + np.exp(1))

    selected_products = top_m_selection(sigmoid_output, m=n, threshold=0.5)
    feasible_bundles = generate_progressive_bundles(selected_products, n)
    feasible_bundles_list = list(feasible_bundles)

    feasible_assortments = np.array([list(map(int, format(bundle_id, f"0{n}b"))) for bundle_id in feasible_bundles_list])
    Rs_feasible = np.sqrt(unit_us.dot(feasible_assortments.T))
    cs_base = np.sum(feasible_assortments * unit_cs, axis=1)
    cs_feasible = (cs_base + ship_cs) * 0.2
    bundle_to_idx = {bundle_id: idx for idx, bundle_id in enumerate(feasible_bundles_list)}
    Rbar = np.max(Rs_feasible)

    build_start = time.time()
    model = gp.Model("optimized_MILP_v2")
    _apply_gurobi_logging_params(model, output_flag=output_flag, log_file=log_file)
    model.Params.MIPGap = 1e-2

    segment_ind = np.arange(m)
    p = model.addVars(feasible_bundles_list, lb=0.0, vtype=GRB.CONTINUOUS, name="p")
    theta = model.addVars(m, feasible_bundles_list, vtype=GRB.BINARY, name="theta")
    s = model.addVars(m, vtype=GRB.CONTINUOUS, name="s")
    S = model.addVars(m, feasible_bundles_list, lb=0.0, vtype=GRB.CONTINUOUS, name="S")
    Z = model.addVars(m, feasible_bundles_list, vtype=GRB.CONTINUOUS, name="Z")
    P = model.addVars(m, feasible_bundles_list, lb=0.0, vtype=GRB.CONTINUOUS, name="P")

    model.setObjective(gp.quicksum(Ns[k, 0] * Z[k, i] for k in segment_ind for i in feasible_bundles_list), GRB.MAXIMIZE)
    model.addConstrs((s[k] >= Rs_feasible[k, bundle_to_idx[i]] - p[i] for i in feasible_bundles_list for k in segment_ind))

    bundle_product_sets = {bundle_id: bundle_to_product_set(bundle_id, n) for bundle_id in feasible_bundles_list}
    for segment_idx, selected_list in enumerate(selected_products):
        if len(selected_list) <= 1:
            continue
        progressive_bundles = []
        for i in range(1, len(selected_list) + 1):
            bundle_array = np.zeros(n, dtype=int)
            for product_idx in selected_list[:i]:
                bundle_array[product_idx] = 1
            bundle_idx = bin2num(bundle_array)
            if bundle_idx in feasible_bundles_list:
                progressive_bundles.append(bundle_idx)
        for i in range(len(progressive_bundles) - 1):
            model.addConstr(
                p[progressive_bundles[i]] <= p[progressive_bundles[i + 1]],
                name=f"{SUBADD_PREFIX}prog_s{segment_idx}_{i}",
            )

    def _is_progressive_redundant(k_set, i_set, j_set):
        return (k_set.issubset(i_set) and k_set != i_set) or (k_set.issubset(j_set) and k_set != j_set)

    added_constraints = set()
    for k in feasible_bundles_list:
        if k == 0:
            continue
        k_set = bundle_product_sets[k]
        if len(k_set) == 0:
            continue
        for i in feasible_bundles_list:
            for j in feasible_bundles_list:
                if i >= j:
                    continue
                i_set = bundle_product_sets[i]
                j_set = bundle_product_sets[j]
                union_set = i_set.union(j_set)
                if (
                    k_set.issubset(union_set)
                    and k_set != i_set
                    and k_set != j_set
                    and not _is_progressive_redundant(k_set, i_set, j_set)
                ):
                    key = (k, min(i, j), max(i, j))
                    if key not in added_constraints:
                        model.addConstr(p[k] <= p[i] + p[j], name=f"{SUBADD_PREFIX}cross_{k}_{i}_{j}")
                        added_constraints.add(key)

    model.addConstrs((P[k, i] >= p[i] - Rbar * (1 - theta[k, i]) for i in feasible_bundles_list for k in segment_ind))
    model.addConstrs((P[k, i] <= p[i] for i in feasible_bundles_list for k in segment_ind))
    model.addConstrs((s[k] >= gp.quicksum(Rs_feasible[k, bundle_to_idx[i]] * theta[j, i] - P[j, i] for i in feasible_bundles_list) for k in segment_ind for j in segment_ind))
    model.addConstrs((Z[k, i] == P[k, i] - cs_feasible[k, bundle_to_idx[i]] * theta[k, i] for i in feasible_bundles_list for k in segment_ind))
    model.addConstrs((S[k, i] == Rs_feasible[k, bundle_to_idx[i]] * theta[k, i] - P[k, i] for i in feasible_bundles_list for k in segment_ind))
    model.addConstrs((s[k] == gp.quicksum(S[k, i] for i in feasible_bundles_list) for k in segment_ind))
    model.addConstrs((gp.quicksum(theta[k, i] for i in feasible_bundles_list) == 1 for k in segment_ind))
    if 0 in feasible_bundles:
        model.addConstrs((S[k, 0] == 0 for k in segment_ind))

    model.update()
    build_time = time.time() - build_start

    logged_ok = _optimize_for_stats_and_validate_log(
        model,
        optimize_for_stats=optimize_for_stats,
        stats_time_limit=stats_time_limit,
        log_file=log_file,
        output_flag=output_flag,
    )

    stats = get_gurobi_model_stats(model)
    return {
        "strategy": "PCP",
        "bundle_space_size": len(feasible_bundles_list),
        "total_variables": stats["num_vars"],
        "total_constraints": stats["num_constrs"],
        "num_nzs": stats["num_nzs"],
        "num_bin_vars": stats["num_bin_vars"],
        "subadditivity_constraints": count_subadditivity_from_model(model),
        "build_time": build_time,
        "gurobi_log_file": log_file or "",
        "gurobi_model_scale_logged": bool(logged_ok),
    }


def _validate_batch_coverage(all_results, datasets, samples_per_dataset):
    for dataset_name in datasets:
        for strategy in STRATEGIES:
            n_ok = len(all_results[dataset_name][strategy])
            if n_ok != samples_per_dataset:
                raise RuntimeError(
                    f"Coverage check failed: {dataset_name}-{strategy} has N={n_ok}, expected {samples_per_dataset}."
                )


def _to_avg_dataframe(all_results, datasets):
    metrics = [
        ("bundle_space_size", "Bundle Space Size"),
        ("total_variables", "Total Variables"),
        ("total_constraints", "Total Constraints"),
        ("num_nzs", "NumNZs"),
        ("subadditivity_constraints", "Subadditivity Constraints"),
        ("build_time", "Model Build Time (s)"),
    ]
    rows = []
    for dataset_name in datasets:
        for strategy in STRATEGIES:
            lst = all_results[dataset_name][strategy]
            row = {"Dataset": dataset_name, "Strategy": strategy, "N": len(lst)}
            for key, label in metrics:
                vals = [x[key] for x in lst if key in x]
                if vals:
                    row[label] = float(np.mean(vals))
                    row[f"{label}_std"] = float(np.std(vals)) if len(vals) > 1 else 0.0
            rows.append(row)
    return pd.DataFrame(rows)


def _print_required_subtables(df, datasets, samples_per_dataset):
    print("\n" + "=" * 80)
    print("Three required subtables")
    print("=" * 80)
    table_cols = ["Strategy", "Bundle Space Size", "Total Variables", "Total Constraints", "Model Build Time (s)"]
    for dataset_name in datasets:
        sub = df[df["Dataset"] == dataset_name].copy()
        sub["Strategy"] = pd.Categorical(sub["Strategy"], categories=STRATEGIES, ordered=True)
        sub = sub.sort_values("Strategy").reset_index(drop=True)
        print(f"\n--- {dataset_name} (N={samples_per_dataset}) ---")
        print(sub[table_cols].to_string(index=False))


def main(
    dataset_name="m10n10",
    sample_index=1,
    output_flag=1,
    optimize_for_stats=True,
    stats_time_limit=0.0,
    logs_dir="gurobi_stats_logs",
):
    if dataset_name not in DATASET_DIR_MAP:
        raise ValueError(f"Unknown dataset '{dataset_name}'. Supported: {list(DATASET_DIR_MAP.keys())}")

    script_dir = os.path.dirname(os.path.abspath(__file__))
    dataset_path = _resolve_dataset_path(script_dir, dataset_name)
    sample_files = sorted([f for f in os.listdir(dataset_path) if f.endswith(".msgpack")])
    if not sample_files:
        raise RuntimeError(f"No samples found in: {dataset_path}")

    idx = min(max(0, sample_index - 1), len(sample_files) - 1)
    sample_name = sample_files[idx]
    sample_file = os.path.join(dataset_path, sample_name)
    graph_data, miscellaneous = process_data(sample_file)
    n, m, unit_cs, ship_cs, unit_us, Ns, *_ = miscellaneous

    model_path = _resolve_model_path(script_dir)
    if model_path is None:
        raise RuntimeError("Model file not found for FCP/PCP evaluation.")
    gcn_model, device = _load_gcn_model(model_path)

    shared_kwargs = dict(
        output_flag=output_flag,
        optimize_for_stats=optimize_for_stats,
        stats_time_limit=stats_time_limit,
    )
    results = []
    for strategy in STRATEGIES:
        log_file = _build_strategy_log_file(logs_dir, dataset_name, sample_name, strategy)
        if strategy == "MILP":
            r = analyze_milp_strategy(n, m, unit_cs, ship_cs, unit_us, Ns, log_file=log_file, **shared_kwargs)
        elif strategy == "FCP":
            r = analyze_fcp_strategy(
                n, m, unit_cs, ship_cs, unit_us, Ns, gcn_model, graph_data, device, log_file=log_file, **shared_kwargs
            )
        else:
            r = analyze_pcp_strategy(
                n, m, unit_cs, ship_cs, unit_us, Ns, gcn_model, graph_data, device, log_file=log_file, **shared_kwargs
            )
        if optimize_for_stats and int(output_flag) == 1 and not r.get("gurobi_model_scale_logged", False):
            raise RuntimeError(f"Missing model-size line in log: {r.get('gurobi_log_file', log_file)}")
        results.append(r)

    df = pd.DataFrame(results)
    col_map = {
        "strategy": "Strategy",
        "bundle_space_size": "Bundle Space Size",
        "total_variables": "Total Variables",
        "total_constraints": "Total Constraints",
        "num_nzs": "NumNZs",
        "subadditivity_constraints": "Subadditivity Constraints",
        "build_time": "Model Build Time (s)",
        "gurobi_log_file": "Gurobi Log File",
        "gurobi_model_scale_logged": "Gurobi Model Size Logged",
    }
    df = df[[c for c in col_map if c in df.columns]].rename(columns=col_map)
    out = f"solution_space_comparison_{dataset_name}.csv"
    df.to_csv(out, index=False, encoding="utf-8-sig")
    print(df.to_string(index=False))
    print(f"\nSaved: {out}")


def main_batch(
    datasets=None,
    samples_per_dataset=10,
    output_flag=1,
    optimize_for_stats=True,
    stats_time_limit=0.0,
    logs_dir="gurobi_stats_logs",
    output_suffix="",
):
    if datasets is None:
        datasets = ["m10n10", "m20n10", "m30n10"]
    datasets = [d for d in datasets if d]

    script_dir = os.path.dirname(os.path.abspath(__file__))
    model_path = _resolve_model_path(script_dir)
    if model_path is None:
        raise RuntimeError("Model file not found for FCP/PCP evaluation.")
    gcn_model, device = _load_gcn_model(model_path)
    print("GCN model loaded.")

    all_results = {ds: {st: [] for st in STRATEGIES} for ds in datasets}
    raw_rows = []

    for dataset_name in datasets:
        if dataset_name not in DATASET_DIR_MAP:
            raise ValueError(f"Unsupported dataset: {dataset_name}")

        dataset_path = _resolve_dataset_path(script_dir, dataset_name)
        sample_files = sorted([f for f in os.listdir(dataset_path) if f.endswith(".msgpack")])
        if len(sample_files) < samples_per_dataset:
            raise RuntimeError(
                f"{dataset_name} has only {len(sample_files)} samples, but {samples_per_dataset} are required."
            )

        chosen_files = sample_files[:samples_per_dataset]
        print("\n" + "=" * 80)
        print(f"Dataset {dataset_name}: first {samples_per_dataset} samples")
        print("=" * 80)

        for i, sample_name in enumerate(chosen_files, start=1):
            sample_file = os.path.join(dataset_path, sample_name)
            graph_data, miscellaneous = process_data(sample_file)
            n, m, unit_cs, ship_cs, unit_us, Ns, *_ = miscellaneous
            print(f"  [{i}/{samples_per_dataset}] {sample_name} (n={n}, m={m})")

            for strategy in STRATEGIES:
                log_file = _build_strategy_log_file(logs_dir, dataset_name, sample_name, strategy)
                kwargs = dict(
                    output_flag=output_flag,
                    optimize_for_stats=optimize_for_stats,
                    stats_time_limit=stats_time_limit,
                    log_file=log_file,
                )

                if strategy == "MILP":
                    result = analyze_milp_strategy(n, m, unit_cs, ship_cs, unit_us, Ns, **kwargs)
                elif strategy == "FCP":
                    result = analyze_fcp_strategy(
                        n, m, unit_cs, ship_cs, unit_us, Ns, gcn_model, graph_data, device, **kwargs
                    )
                else:
                    result = analyze_pcp_strategy(
                        n, m, unit_cs, ship_cs, unit_us, Ns, gcn_model, graph_data, device, **kwargs
                    )

                if optimize_for_stats and int(output_flag) == 1 and not result.get("gurobi_model_scale_logged", False):
                    raise RuntimeError(
                        f"{dataset_name}/{sample_name}/{strategy} missing model-size line in log: "
                        f"{result.get('gurobi_log_file', log_file)}"
                    )

                all_results[dataset_name][strategy].append(result)
                raw_rows.append(
                    {
                        "Dataset": dataset_name,
                        "Sample Index (1-based)": i,
                        "Sample File": sample_name,
                        "Strategy": strategy,
                        "Bundle Space Size": result["bundle_space_size"],
                        "Total Variables": result["total_variables"],
                        "Total Constraints": result["total_constraints"],
                        "NumNZs": result.get("num_nzs"),
                        "Subadditivity Constraints": result.get("subadditivity_constraints"),
                        "Model Build Time (s)": result["build_time"],
                        "Gurobi Log File": result.get("gurobi_log_file", log_file),
                        "Gurobi Model Size Logged": result.get("gurobi_model_scale_logged", False),
                    }
                )

    _validate_batch_coverage(all_results, datasets, samples_per_dataset)

    raw_df = pd.DataFrame(raw_rows)
    raw_out = f"solution_space_comparison_batch_raw{output_suffix}.csv"
    raw_df.to_csv(raw_out, index=False, encoding="utf-8-sig")
    print(f"\nSaved raw results: {raw_out}")

    df = _to_avg_dataframe(all_results, datasets)
    avg_out = f"solution_space_comparison_batch_avg{output_suffix}.csv"
    df.to_csv(avg_out, index=False, encoding="utf-8-sig")
    print(f"Saved average results: {avg_out}")

    metric_names = [
        "Bundle Space Size",
        "Total Variables",
        "Total Constraints",
        "NumNZs",
        "Subadditivity Constraints",
        "Model Build Time (s)",
    ]
    df_by_strategy = df.groupby("Strategy", as_index=False).agg({**{m: "mean" for m in metric_names}, "N": "sum"})
    df_by_strategy["Strategy"] = pd.Categorical(df_by_strategy["Strategy"], categories=STRATEGIES, ordered=True)
    df_by_strategy = df_by_strategy.sort_values("Strategy").reset_index(drop=True)
    df_by_strategy = df_by_strategy[["Strategy", "N"] + metric_names]
    df_by_strategy.to_csv(f"solution_space_comparison_by_strategy_avg{output_suffix}.csv", index=False, encoding="utf-8-sig")

    print("\n" + "=" * 80)
    print(f"Average table (N={samples_per_dataset} per dataset and strategy)")
    print("=" * 80)
    print(df[["Dataset", "Strategy", "N"] + metric_names].to_string(index=False))

    _print_required_subtables(df, datasets, samples_per_dataset)
    return df


def plot_solution_space_tables(df, output_path="solution_space_comparison_tables.png", datasets=None):
    table_cols = ["Bundle Space Size", "Total Variables", "Total Constraints", "Model Build Time (s)"]
    if datasets is None:
        datasets = df["Dataset"].unique().tolist()
    n_ds = len(datasets)

    fig, axes = plt.subplots(1, n_ds, figsize=(4.7 * n_ds, 5))
    if n_ds == 1:
        axes = [axes]

    def _fmt_cell(v):
        if isinstance(v, (int, np.integer)):
            return f"{v:,}"
        if isinstance(v, float):
            if v >= 1000:
                return f"{v:,.0f}"
            if v >= 1:
                return f"{v:.2f}"
            return f"{v:.4f}"
        return str(v)

    for idx, ds in enumerate(datasets):
        ax = axes[idx]
        sub = df[df["Dataset"] == ds].copy()
        if len(sub) == 0:
            ax.text(0.5, 0.5, f"{ds}\nNo data", ha="center", va="center")
            ax.set_axis_off()
            continue

        sub["Strategy"] = pd.Categorical(sub["Strategy"], categories=STRATEGIES, ordered=True)
        sub = sub.sort_values("Strategy").reset_index(drop=True)

        cols = [c for c in table_cols if c in sub.columns]
        cell_data = [[row["Strategy"]] + [_fmt_cell(row[c]) for c in cols] for _, row in sub.iterrows()]
        header = ["Strategy"] + cols
        table_data = [header] + cell_data

        table = ax.table(cellText=table_data, loc="center", cellLoc="center", colWidths=[0.12] + [0.22] * len(cols))
        table.auto_set_font_size(False)
        table.set_fontsize(9)
        table.scale(1.2, 2.2)

        for i in range(len(header)):
            table[(0, i)].set_facecolor("#4472C4")
            table[(0, i)].set_text_props(color="white", fontweight="bold")
        for i in range(1, len(table_data)):
            for j in range(len(header)):
                if i % 2 == 0:
                    table[(i, j)].set_facecolor("#E7E6E6")

        n_value = int(sub["N"].iloc[0]) if "N" in sub.columns else 0
        ax.set_title(f"{ds} (N={n_value})", fontsize=12)
        ax.axis("off")

    n_val = int(df["N"].iloc[0]) if "N" in df.columns and len(df) > 0 else 0
    plt.suptitle(f"Solution Space Complexity (Gurobi Model Stats, Average over N={n_val} samples per dataset)", fontsize=14, y=1.02)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved figure: {output_path}")


def _parse_args():
    parser = argparse.ArgumentParser(description="Analyze MILP/FCP/PCP solution-space complexity.")
    parser.add_argument("--batch", nargs=2, metavar=("DATASETS", "SAMPLES"))
    parser.add_argument("--output-suffix", type=str, default="", help="Suffix for output files (e.g. _BSP)")
    parser.add_argument("--output-flag", type=int, default=1)
    parser.add_argument("--optimize-for-stats", type=int, choices=[0, 1], default=1)
    parser.add_argument("--stats-time-limit", type=float, default=0.0)
    parser.add_argument("--logs-dir", type=str, default="gurobi_stats_logs")
    parser.add_argument("dataset_name", nargs="?", default="m10n10")
    parser.add_argument("sample_index", nargs="?", type=int, default=1)
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    optimize_for_stats = bool(args.optimize_for_stats)

    if args.batch:
        datasets = [x.strip() for x in args.batch[0].split(",") if x.strip()]
        n_samples = int(args.batch[1])
        suffix = args.output_suffix or ""
        df = main_batch(
            datasets=datasets,
            samples_per_dataset=n_samples,
            output_flag=args.output_flag,
            optimize_for_stats=optimize_for_stats,
            stats_time_limit=args.stats_time_limit,
            logs_dir=args.logs_dir,
            output_suffix=suffix,
        )
        if df is not None and len(df) > 0:
            plot_solution_space_tables(df, output_path=f"solution_space_comparison_tables{suffix}.png", datasets=datasets)
    else:
        main(
            dataset_name=args.dataset_name,
            sample_index=args.sample_index,
            output_flag=args.output_flag,
            optimize_for_stats=optimize_for_stats,
            stats_time_limit=args.stats_time_limit,
            logs_dir=args.logs_dir,
        )
