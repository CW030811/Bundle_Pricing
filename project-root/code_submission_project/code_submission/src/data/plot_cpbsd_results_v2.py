from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


DEFAULT_METHOD_ORDER = ["CPBSD-MILP", "CPBSD-A", "MB", "BSP", "FCP-pruned-MB"]
DEFAULT_METHOD_LABELS = {
    "CPBSD-MILP": "CPBSD-MILP",
    "CPBSD-A": "CPBSD-A",
    "MB": "MB",
    "BSP": "BSP",
    "FCP-pruned-MB": "FCP-pruned-MB",
}


def _is_number(value):
    return isinstance(value, (int, float, np.integer, np.floating))


def _method_sort_key(method, method_order):
    if method in method_order:
        return (0, method_order.index(method))
    return (1, method)


def _collect_ratio_series(rows, *, n, ref_method, method_order, method_labels):
    by_instance = {}
    for row in rows:
        if row.get("n") != n or row.get("error_message"):
            continue
        by_instance.setdefault(row["instance_id"], {})
        by_instance[row["instance_id"]].setdefault(row["method"], row)

    methods = sorted(
        {
            method
            for instance_rows in by_instance.values()
            for method in instance_rows
            if method != ref_method
        },
        key=lambda method: _method_sort_key(method, method_order),
    )

    labels = []
    in_sample = []
    out_sample = []
    for method in methods:
        in_values = []
        out_values = []
        for instance_rows in by_instance.values():
            ref_row = instance_rows.get(ref_method)
            method_row = instance_rows.get(method)
            if ref_row is None or method_row is None:
                continue
            ref_in = ref_row.get("revenue_in_sample")
            ref_out = ref_row.get("revenue_out_sample")
            cur_in = method_row.get("revenue_in_sample")
            cur_out = method_row.get("revenue_out_sample")
            if _is_number(ref_in) and ref_in != 0 and _is_number(cur_in):
                in_values.append(float(cur_in) / float(ref_in))
            if _is_number(ref_out) and ref_out != 0 and _is_number(cur_out):
                out_values.append(float(cur_out) / float(ref_out))
        if in_values or out_values:
            labels.append(method_labels.get(method, method))
            in_sample.append(in_values if in_values else [np.nan])
            out_sample.append(out_values if out_values else [np.nan])

    return labels, in_sample, out_sample


def _style_boxplot(boxplot, facecolor, edgecolor):
    for patch in boxplot["boxes"]:
        patch.set(facecolor=facecolor, edgecolor=edgecolor, linewidth=1.0)
    for key in ("whiskers", "caps", "medians"):
        for artist in boxplot[key]:
            artist.set(color=edgecolor, linewidth=1.0)


def plot_ratio_boxplot(
    rows,
    *,
    out_dir: Path,
    n: int,
    ref_method: str,
    title: str,
    method_order=None,
    method_labels=None,
):
    method_order = list(method_order) if method_order is not None else list(DEFAULT_METHOD_ORDER)
    method_labels = {**DEFAULT_METHOD_LABELS, **(method_labels or {})}
    labels, in_sample, out_sample = _collect_ratio_series(
        rows,
        n=n,
        ref_method=ref_method,
        method_order=method_order,
        method_labels=method_labels,
    )
    if not labels:
        return None

    out_dir.mkdir(parents=True, exist_ok=True)
    x = np.arange(len(labels), dtype=float)
    fig_width = max(6.0, 1.3 * len(labels) + 2.0)
    fig, ax = plt.subplots(figsize=(fig_width, 4.8), dpi=180)
    ax.set_facecolor("#ebebeb")
    fig.patch.set_facecolor("white")

    box_in = ax.boxplot(
        in_sample,
        positions=x - 0.18,
        widths=0.32,
        patch_artist=True,
        showfliers=False,
        manage_ticks=False,
    )
    box_out = ax.boxplot(
        out_sample,
        positions=x + 0.18,
        widths=0.32,
        patch_artist=True,
        showfliers=False,
        manage_ticks=False,
    )
    _style_boxplot(box_in, "#74c0e3", "#2b8cbe")
    _style_boxplot(box_out, "#2b8cbe", "#1f5d84")

    flat_values = [
        value
        for series in in_sample + out_sample
        for value in series
        if np.isfinite(value)
    ]
    if flat_values:
        ax.axhline(float(np.mean(flat_values)), color="#666666", linestyle="--", linewidth=1.0, label="Mean")
        ax.axhline(float(np.median(flat_values)), color="#444444", linestyle="-.", linewidth=1.0, label="Median")
    ax.axhline(1.0, color="#cc6d2d", linestyle="--", linewidth=1.2, label=ref_method)

    ax.plot([], [], color="#74c0e3", linewidth=6, label="In-sample")
    ax.plot([], [], color="#2b8cbe", linewidth=6, label="Out-of-sample")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel(f"Revenue Ratio vs {ref_method}")
    ax.set_title(title)
    ax.grid(axis="y", color="white", linewidth=1.0)
    ax.set_axisbelow(True)
    ax.legend(loc="upper left", ncol=2, fontsize=8, frameon=True)
    fig.tight_layout()

    filename = f"boxplot_ratio_vs_{ref_method.lower().replace('-', '_')}_n{n}.png"
    path = out_dir / filename
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path
