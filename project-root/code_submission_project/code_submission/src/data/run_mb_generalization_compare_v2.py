import csv
import json
import os
from pathlib import Path
import sys

import msgpack
import msgpack_numpy as mnp
import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.append(str(SCRIPT_DIR))

from generate_data_CPBSD import generate_batch, sample_valuations, valuation_means
from solve_mb_bsp_on_cpbsd_v2 import extract_mb_policy_info, eval_mb_policy, json_default, solve_mb


ROOT = Path(
    os.environ.get(
        "MB_GENERALIZATION_COMPARE_V2_ROOT",
        "/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/mb_generalization_compare_v2",
    )
)

N_PRODUCTS = 5
DIST_FAMILY = "normal"
RHO = 0.0
HETEROGENEITY = "full"
COST_SCENARIO = "hvhm"
TIME_LIMIT = 300.0
MIP_GAP = 1e-2
N_INSTANCES = 5
SEED_BASE = 20260310
IN_SAMPLE_KS = [50, 100]
OUT_SAMPLE_KS = [2000, 5000]


def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)


def load_msgpack(path: Path):
    with open(path, "rb") as f:
        return msgpack.load(f, object_hook=mnp.decode)


def sample_out_vals(setup: dict, out_k: int) -> np.ndarray:
    rng = np.random.default_rng(int(setup["seed"]) + 100000 + out_k)
    means = valuation_means(int(setup["n_products"]), setup["heterogeneity"])
    return sample_valuations(
        k=out_k,
        means=means,
        family=setup["dist_family"],
        rho=float(setup["rho"]),
        rng=rng,
    )


def summarize(rows):
    groups = {}
    for row in rows:
        groups.setdefault(int(row["k_in"]), []).append(row)

    out = []
    for k_in, g in sorted(groups.items()):
        runtime = np.array([float(r["runtime"]) for r in g], dtype=float)
        objective = np.array([float(r["objective_raw"]) for r in g], dtype=float)
        rev_in = np.array([float(r["revenue_in_sample"]) for r in g], dtype=float)
        rev_2000 = np.array([float(r["revenue_out_sample_k2000"]) for r in g], dtype=float)
        rev_5000 = np.array([float(r["revenue_out_sample_k5000"]) for r in g], dtype=float)
        out.append(
            {
                "k_in": k_in,
                "instances": len(g),
                "status_counts": {status: sum(1 for r in g if r["status_text"] == status) for status in sorted(set(r["status_text"] for r in g))},
                "runtime_mean": float(runtime.mean()),
                "runtime_median": float(np.median(runtime)),
                "objective_raw_mean": float(objective.mean()),
                "revenue_in_sample_mean": float(rev_in.mean()),
                "revenue_out_sample_k2000_mean": float(rev_2000.mean()),
                "revenue_out_sample_k5000_mean": float(rev_5000.mean()),
                "generalization_ratio_k2000_over_in_mean": float((rev_2000 / rev_in).mean()),
                "generalization_ratio_k5000_over_in_mean": float((rev_5000 / rev_in).mean()),
                "generalization_drop_k2000_mean": float((rev_in - rev_2000).mean()),
                "generalization_drop_k5000_mean": float((rev_in - rev_5000).mean()),
            }
        )
    return out


def main():
    ensure_dir(ROOT)
    rows = []

    for k_in in IN_SAMPLE_KS:
        data_dir = ROOT / f"data_k{k_in}"
        result_dir = ROOT / f"results_k{k_in}"
        ensure_dir(data_dir)
        ensure_dir(result_dir)

        generate_batch(
            out_dir=str(data_dir),
            n_products=N_PRODUCTS,
            k_samples=k_in,
            dist_family=DIST_FAMILY,
            rho=RHO,
            heterogeneity=HETEROGENEITY,
            cost_scenario=COST_SCENARIO,
            n_instances=N_INSTANCES,
            seed=SEED_BASE,
        )

        for instance_idx in range(1, N_INSTANCES + 1):
            instance_path = data_dir / (
                f"cpbsd_instance_{instance_idx:03d}_N{N_PRODUCTS}_K{k_in}_{DIST_FAMILY}_rho{RHO}_{HETEROGENEITY}_{COST_SCENARIO}.msgpack"
            )
            obj = load_msgpack(instance_path)
            setup = obj["setup"]
            v_kn = np.asarray(obj["valuation_samples_V"], dtype=float)
            c_n = np.asarray(obj["production_cost_c"], dtype=float)

            res = solve_mb(v_kn, c_n, time_limit=TIME_LIMIT, mip_gap=MIP_GAP, output_flag=0)
            result_path = result_dir / f"mb_instance_{instance_idx:03d}.json"
            result_path.write_text(json.dumps(res, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")

            mb_info = extract_mb_policy_info(res)
            prices = mb_info["bundle_prices_full"]
            assortments = mb_info["assortments"]

            revenue_in = eval_mb_policy(v_kn, c_n, prices, assortments)
            revenue_out = {}
            for out_k in OUT_SAMPLE_KS:
                v_out = sample_out_vals(setup, out_k)
                revenue_out[out_k] = eval_mb_policy(v_out, c_n, prices, assortments)

            rows.append(
                {
                    "instance_id": f"k{k_in}_inst{instance_idx:03d}",
                    "k_in": k_in,
                    "seed": int(setup["seed"]),
                    "n_products": int(setup["n_products"]),
                    "dist_family": setup["dist_family"],
                    "rho": float(setup["rho"]),
                    "heterogeneity": setup["heterogeneity"],
                    "cost_scenario": setup["cost_scenario"],
                    "time_limit": TIME_LIMIT,
                    "solver_status": int(res["solver_status"]),
                    "status_text": {2: "OPTIMAL", 9: "TIME_LIMIT"}.get(int(res["solver_status"]), str(res["solver_status"])),
                    "runtime": float(res["runtime"]) if res.get("runtime") is not None else None,
                    "wall_time": float(res["wall_time"]) if res.get("wall_time") is not None else None,
                    "mip_gap": float(res["mip_gap"]) if res.get("mip_gap") is not None else None,
                    "objective_raw": float(res["objective"]) if res.get("objective") is not None else None,
                    "revenue_in_sample": float(revenue_in),
                    "revenue_out_sample_k2000": float(revenue_out[2000]),
                    "revenue_out_sample_k5000": float(revenue_out[5000]),
                    "generalization_ratio_k2000_over_in": float(revenue_out[2000] / revenue_in),
                    "generalization_ratio_k5000_over_in": float(revenue_out[5000] / revenue_in),
                    "bundle_space_size": int(mb_info["bundle_space_size"]) if mb_info["bundle_space_size"] is not None else None,
                    "bundle_price_count_full": int(mb_info["bundle_price_count_full"]),
                    "bundle_price_count_selected": int(mb_info["bundle_price_count_selected"]),
                    "result_path": str(result_path),
                }
            )

    summary = summarize(rows)

    details_csv = ROOT / "mb_generalization_compare_details.csv"
    with details_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    summary_json = ROOT / "mb_generalization_compare_summary.json"
    summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    report_md = ROOT / "mb_generalization_compare_summary.md"
    lines = [
        "# MB Generalization Compare v2",
        "",
        f"- Setup: N={N_PRODUCTS}, dist={DIST_FAMILY}, rho={RHO}, heterogeneity={HETEROGENEITY}, cost={COST_SCENARIO}",
        f"- Time limit: {TIME_LIMIT}s",
        f"- Tie-breaking: equal surplus -> choose higher firm profit bundle",
        "",
        "## Aggregate Summary",
        "",
        "| K in-sample | Instances | Status | Runtime Mean (s) | Runtime Median (s) | Revenue In Mean | Revenue Out K=2000 Mean | Revenue Out K=5000 Mean | Gen Ratio 2000/In | Gen Ratio 5000/In |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in summary:
        status = ", ".join(f"{k}:{v}" for k, v in item["status_counts"].items())
        lines.append(
            f"| {item['k_in']} | {item['instances']} | {status} | {item['runtime_mean']:.2f} | {item['runtime_median']:.2f} | "
            f"{item['revenue_in_sample_mean']:.4f} | {item['revenue_out_sample_k2000_mean']:.4f} | {item['revenue_out_sample_k5000_mean']:.4f} | "
            f"{item['generalization_ratio_k2000_over_in_mean']:.4f} | {item['generalization_ratio_k5000_over_in_mean']:.4f} |"
        )
    report_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({"details_csv": str(details_csv), "summary_json": str(summary_json), "summary_md": str(report_md), "summary": summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
