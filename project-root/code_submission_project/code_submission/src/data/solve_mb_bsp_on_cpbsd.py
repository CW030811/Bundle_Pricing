"""Compatibility entrypoint for MB/BSP experiments.

This legacy import path now routes MB solves to the Appendix C-aligned
implementation in `solve_mb_bsp_on_cpbsd_v2.py`. The pre-Appendix MB
formulation is preserved in `solve_mb_bsp_on_cpbsd_legacy.py`.
"""

import argparse
import json
from pathlib import Path
from typing import Dict, Tuple

import numpy as np

from solve_mb_bsp_on_cpbsd_v2 import (
    MB_FORMULATION_VERSION,
    build_assortments,
    eval_bsp_policy,
    eval_mb_policy,
    json_default,
    load_instance,
    normalize_numeric_keys,
    solve_bsp as _solve_bsp_appendix,
    solve_mb as _solve_mb_appendix,
)


def solve_mb(v_kn: np.ndarray, c_n: np.ndarray, time_limit: float = 300.0, mip_gap: float = 1e-2, output_flag: int = 0):
    """Solve MB using the Appendix C-aligned formulation.

    For backward compatibility, `bundle_prices` points to the full bundle
    price menu so older experiment drivers keep evaluating the full policy.
    """
    result = _solve_mb_appendix(v_kn, c_n, time_limit=time_limit, mip_gap=mip_gap, output_flag=output_flag)
    bundle_prices_full = normalize_numeric_keys(result.get("bundle_prices_full") or {})
    if bundle_prices_full:
        result["bundle_prices"] = bundle_prices_full
    return result


def solve_bsp(v_kn: np.ndarray, c_n: np.ndarray, time_limit: float = 300.0, mip_gap: float = 1e-2, output_flag: int = 0):
    return _solve_bsp_appendix(v_kn, c_n, time_limit=time_limit, mip_gap=mip_gap, output_flag=output_flag)


def eval_mb_out_of_sample(v_kn: np.ndarray, c_n: np.ndarray, bundle_prices: Dict, assortments: np.ndarray) -> float:
    return eval_mb_policy(v_kn, c_n, bundle_prices, assortments)


def eval_bsp_out_of_sample(v_kn: np.ndarray, c_n: np.ndarray, size_prices: Dict) -> float:
    return eval_bsp_policy(v_kn, c_n, size_prices)


def _json_clean_dict(d: Dict) -> Dict:
    return {str(k): v for k, v in normalize_numeric_keys(d).items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--instance", required=True)
    ap.add_argument("--method", choices=["mb", "bsp"], required=True)
    ap.add_argument("--time-limit", type=float, default=300.0)
    ap.add_argument("--mip-gap", type=float, default=1e-2)
    ap.add_argument("--output-flag", type=int, default=0)
    ap.add_argument("--save-json", type=str, default="")
    args = ap.parse_args()

    v_kn, c_n = load_instance(Path(args.instance))
    if args.method == "mb":
        res = solve_mb(v_kn, c_n, time_limit=args.time_limit, mip_gap=args.mip_gap, output_flag=args.output_flag)
        for key in ("bundle_prices", "bundle_prices_full", "bundle_prices_selected"):
            if isinstance(res.get(key), dict):
                res[key] = _json_clean_dict(res[key])
    else:
        res = solve_bsp(v_kn, c_n, time_limit=args.time_limit, mip_gap=args.mip_gap, output_flag=args.output_flag)
        if isinstance(res.get("size_prices"), dict):
            res["size_prices"] = _json_clean_dict(res["size_prices"])

    text = json.dumps(res, ensure_ascii=False, indent=2, default=json_default)
    print(text)
    if args.save_json:
        Path(args.save_json).write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
