import argparse
from pathlib import Path

import msgpack
import msgpack_numpy as mnp
import numpy as np

from solve_cpbsd_milp import solve as solve_milp
from generate_data_CPBSD import generate_batch


def bcs_choice(vk, p, d):
    N = len(p)
    best_surplus = 0.0
    best_s = 0
    best_idx = []
    for s in range(1, N + 1):
        util = vk - p + d[s]
        idx = np.argpartition(util, -s)[-s:]
        surplus = float(util[idx].sum())
        if surplus > best_surplus + 1e-9:
            best_surplus = surplus
            best_s = s
            best_idx = sorted(idx)
    if best_surplus <= 1e-9:
        return 0, [], 0.0
    return best_s, best_idx, best_surplus


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--N", type=int, default=5)
    ap.add_argument("--K", type=int, default=30)
    ap.add_argument("--seed", type=int, default=902)
    ap.add_argument("--time-limit", type=float, default=120)
    ap.add_argument("--out-dir", type=str, default="/Users/sensen/.openclaw/workspace/tmp_cpbsd_diag")
    ap.add_argument("--full-matrix", action="store_true")
    args = ap.parse_args()

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    inst = generate_batch(
        out_dir=str(out),
        n_products=args.N,
        k_samples=args.K,
        dist_family="normal",
        rho=0.0,
        heterogeneity="full",
        cost_scenario="hvhm",
        n_instances=1,
        seed=args.seed,
    )[0]

    obj = msgpack.load(open(inst, "rb"), object_hook=mnp.decode)
    v = obj["valuation_samples_V"]
    c = obj["production_cost_c"]

    milp = solve_milp(v, c, mip_gap=1e-2, time_limit=args.time_limit, output_flag=0)
    sol = milp["solution"]
    N = v.shape[1]
    K = v.shape[0]
    p = np.array(sol["p"])
    d = np.array(sol["d"])
    x = sol["x"]

    mismatch = 0
    examples = []
    for k in range(K):
        s_m = 0
        idx_m = []
        for s in range(1, N + 1):
            idx = [i for i in range(N) if x[k][i][s] == 1]
            if len(idx) == s:
                s_m = s
                idx_m = sorted(idx)
                break
        if s_m == 0:
            surplus_m = 0.0
        else:
            util = v[k] - p + d[s_m]
            surplus_m = float(util[idx_m].sum())

        s_b, idx_b, surplus_b = bcs_choice(v[k], p, d)
        if abs(surplus_m - surplus_b) > 1e-6:
            mismatch += 1
            if len(examples) < 3:
                examples.append((k, s_m, idx_m, surplus_m, s_b, idx_b, surplus_b))

    print(f"K {K} mismatch {mismatch}")
    print(f"MILP ObjVal {sol['objective']} gap {milp.get('mip_gap')}")

    # detailed per-customer output
    for k in range(K):
        # MILP selection
        s_m = 0
        idx_m = []
        for s in range(1, N + 1):
            idx = [i for i in range(N) if x[k][i][s] == 1]
            if len(idx) == s:
                s_m = s
                idx_m = sorted(idx)
                break
        if s_m == 0:
            surplus_m = 0.0
            revenue_m = 0.0
        else:
            util = v[k] - p + d[s_m]
            surplus_m = float(util[idx_m].sum())
            revenue_m = float((p[idx_m] - c[idx_m]).sum() - s_m * d[s_m])

        s_b, idx_b, surplus_b = bcs_choice(v[k], p, d)
        if s_b == 0:
            revenue_b = 0.0
        else:
            revenue_b = float((p[idx_b] - c[idx_b]).sum() - s_b * d[s_b])

        print("\n--- Customer k=%d ---" % k)
        print("MILP: s=%s idx=%s surplus=%.6f revenue=%.6f w=%.6f" % (
            s_m, idx_m, surplus_m, revenue_m, float(sol['w'][k])
        ))
        print("BCS : s=%s idx=%s surplus=%.6f revenue=%.6f" % (
            s_b, idx_b, surplus_b, revenue_b
        ))
        # show w_s, alpha for this k
        print("w_s:", [float(sol['w_s'][k][s]) for s in range(1, N + 1)])
        print("alpha:", [float(sol['alpha'][k][s]) for s in range(1, N + 1)])
        # q and beta for active selection sizes
        if s_m > 0:
            print("q (selected):", [float(sol['q'][k][i][s_m]) for i in idx_m])
            print("beta (selected):", [float(sol['beta'][k][i][s_m]) for i in idx_m])
        if args.full_matrix:
            # full q/beta matrices for this k
            q_full = [[float(sol['q'][k][i][s]) for s in range(1, N + 1)] for i in range(N)]
            beta_full = [[float(sol['beta'][k][i][s]) for s in range(1, N + 1)] for i in range(N)]
            print("q_full:", q_full)
            print("beta_full:", beta_full)

    if examples:
        print("examples", examples)


if __name__ == "__main__":
    main()
