import argparse
import json
import os
import time
from pathlib import Path
from typing import Dict, Tuple

# Prefer explicit academic license file when present
if not os.environ.get("GRB_LICENSE_FILE") and Path.home().joinpath('.gurobi', 'gurobi.lic').exists():
    os.environ["GRB_LICENSE_FILE"] = str(Path.home().joinpath('.gurobi', 'gurobi.lic'))

import gurobipy as gp
import msgpack
import msgpack_numpy as mnp
import numpy as np
from gurobipy import GRB


# CPBSD-A: preset preference rankings (approximation)
# Ranking rule used here: sort by potential surplus z_kn = v_kn - c_n (descending)


def load_instance(path: Path) -> Tuple[np.ndarray, np.ndarray]:
    with open(path, "rb") as f:
        obj = msgpack.load(f, object_hook=mnp.decode)
    v = np.asarray(obj["valuation_samples_V"], dtype=float)
    c = np.asarray(obj["production_cost_c"], dtype=float)
    return v, c


def build_xhat(v_kn: np.ndarray, c_n: np.ndarray) -> np.ndarray:
    """
    xhat[k,n,s] in {0,1} for s=1..N (index 1..N), preset by ranking z=v-c.
    """
    K, N = v_kn.shape
    xhat = np.zeros((K, N, N + 1), dtype=int)
    z = v_kn - c_n[None, :]
    for k in range(K):
        order = np.argsort(-z[k])
        for s in range(1, N + 1):
            chosen = order[:s]
            xhat[k, chosen, s] = 1
    return xhat


def solve_cpbsd_a(
    v_kn: np.ndarray,
    c_n: np.ndarray,
    mip_gap=1e-2,
    time_limit=300.0,
    output_flag=0,
    big_m=None,
    p_ub=None,
    d_ub=None,
):
    K, N = v_kn.shape
    S = list(range(1, N + 1))
    K_idx = range(K)
    N_idx = range(N)

    vmax = float(np.max(v_kn))
    if p_ub is None:
        p_ub = vmax
    if d_ub is None:
        d_ub = p_ub
    if big_m is None:
        big_m = max(0.0, p_ub)

    xhat = build_xhat(v_kn, c_n)

    m = gp.Model("CPBSD_A")

    p = m.addVars(N_idx, lb=0.0, ub=p_ub, vtype=GRB.CONTINUOUS, name="p")
    d = m.addVars(S, lb=0.0, ub=d_ub, vtype=GRB.CONTINUOUS, name="d")

    y = m.addVars(K_idx, S, vtype=GRB.BINARY, name="y")
    q = m.addVars(K_idx, N_idx, S, lb=0.0, vtype=GRB.CONTINUOUS, name="q")
    w_s = m.addVars(K_idx, S, lb=0.0, vtype=GRB.CONTINUOUS, name="w_s")
    w = m.addVars(K_idx, lb=0.0, vtype=GRB.CONTINUOUS, name="w")
    alpha = m.addVars(K_idx, S, lb=-GRB.INFINITY, vtype=GRB.CONTINUOUS, name="alpha")
    beta = m.addVars(K_idx, N_idx, S, lb=0.0, vtype=GRB.CONTINUOUS, name="beta")

    # x_expr = xhat * y
    def x_expr(k, n, s):
        if xhat[k, n, s] == 0:
            return 0.0
        return y[k, s]

    m.setObjective(
        (1.0 / K)
        * gp.quicksum(q[k, n, s] - c_n[n] * x_expr(k, n, s) for k in K_idx for n in N_idx for s in S),
        GRB.MAXIMIZE,
    )

    # Same core constraints, with x replaced by xhat*y
    m.addConstrs((w[k] >= s * alpha[k, s] + gp.quicksum(beta[k, n, s] for n in N_idx) for k in K_idx for s in S), name="c9")
    m.addConstrs((alpha[k, s] + beta[k, n, s] >= v_kn[k, n] - p[n] + d[s] for k in K_idx for n in N_idx for s in S), name="c10")

    m.addConstrs((gp.quicksum(y[k, s] for s in S) <= 1 for k in K_idx), name="c12")

    # (13) enforced under preset ranking via y
    m.addConstrs((gp.quicksum(x_expr(k, n, s) for n in N_idx) == s * y[k, s] for k in K_idx for s in S), name="c13")

    # (16)(17)
    m.addConstrs((q[k, n, s] >= p[n] - d[s] - big_m * (1 - x_expr(k, n, s)) for k in K_idx for n in N_idx for s in S), name="c16")
    m.addConstrs((q[k, n, s] <= p[n] - d[s] for k in K_idx for n in N_idx for s in S), name="c17")

    # (18)(19)
    m.addConstrs((w_s[k, s] == gp.quicksum(v_kn[k, n] * x_expr(k, n, s) - q[k, n, s] for n in N_idx) for k in K_idx for s in S), name="c18")
    m.addConstrs((w[k] == gp.quicksum(w_s[k, s] for s in S) for k in K_idx), name="c19")

    # (20)
    m.addConstrs((w[k] >= gp.quicksum(v_kn[k, n] * x_expr(j, n, s) - q[j, n, s] for n in N_idx for s in S)
                  for k in K_idx for j in K_idx if j != k), name="c20")

    # (21)(22)
    m.addConstrs((s * d[s] >= s1 * d[s1] + (s - s1) * d[s - s1] for s in S for s1 in range(1, s)), name="c21")
    m.addConstr(d[1] == 0.0, name="c22_d1")

    m.setParam("MIPGap", mip_gap)
    m.setParam("TimeLimit", time_limit)
    m.setParam("OutputFlag", output_flag)

    t0 = time.time()
    m.optimize()
    t1 = time.time()

    out = {
        "solver_status": int(m.Status),
        "sol_count": m.SolCount,
        "runtime": m.Runtime,
        "wall_time": t1 - t0,
        "node_count": float(m.NodeCount),
        "K": K,
        "N": N,
        "big_M": big_m,
        "p_ub": p_ub,
        "d_ub": d_ub,
        "mip_gap": float(m.MIPGap) if m.SolCount > 0 else None,
        "best_bound": float(m.ObjBound) if m.SolCount > 0 else None,
    }

    if m.SolCount > 0:
        out["objective"] = float(m.ObjVal)
        out["p"] = [p[n].X for n in N_idx]
        out["d"] = [0.0] + [d[s].X for s in S]

    return out


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--instance", type=str, default="")
    ap.add_argument("--N", type=int, default=10)
    ap.add_argument("--K", type=int, default=100)
    ap.add_argument("--seed", type=int, default=20260304)
    ap.add_argument("--mip-gap", type=float, default=1e-2)
    ap.add_argument("--time-limit", type=float, default=300)
    ap.add_argument("--output-flag", type=int, default=0)
    ap.add_argument("--big-m", type=float, default=-1.0)
    ap.add_argument("--p-ub", type=float, default=-1.0)
    ap.add_argument("--d-ub", type=float, default=-1.0)
    ap.add_argument("--save-json", type=str, default="")
    return ap.parse_args()


def main():
    args = parse_args()

    if args.instance:
        v_kn, c_n = load_instance(Path(args.instance))
    else:
        rng = np.random.default_rng(args.seed)
        v_kn = np.maximum(rng.normal(2.0, 0.8, size=(args.K, args.N)), 0.0)
        c_n = rng.uniform(0.1, 1.2, size=args.N)

    big_m = None if args.big_m <= 0 else args.big_m
    p_ub = None if args.p_ub <= 0 else args.p_ub
    d_ub = None if args.d_ub <= 0 else args.d_ub

    res = solve_cpbsd_a(
        v_kn,
        c_n,
        mip_gap=args.mip_gap,
        time_limit=args.time_limit,
        output_flag=args.output_flag,
        big_m=big_m,
        p_ub=p_ub,
        d_ub=d_ub,
    )
    text = json.dumps(res, ensure_ascii=False, indent=2)
    print(text)
    if args.save_json:
        p = Path(args.save_json)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
