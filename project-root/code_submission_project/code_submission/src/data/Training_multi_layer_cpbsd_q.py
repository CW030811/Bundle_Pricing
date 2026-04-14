"""
CPBSD edge-level GCN training script.

This adapts the original Training_multi_layer.py to the CPBSD data structure:
- Product node features: [c_n, mean_k(v_kn), 0, 0]
- Customer node features: [0, 0, K, rho_k], rho_k = (1/N) * sum_n 1(v_kn - c_n > 0)
- Edge features: [v_kn]
- Edge supervision: q_kn = sum_s q_kns extracted from CPBSD-MILP solution

The script pairs CPBSD instance msgpack files with CPBSD-MILP result json files and
trains an edge-scoring GCN as a regression model on q_kn.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import matplotlib.pyplot as plt
import msgpack
import msgpack_numpy as mnp
import numpy as np
import torch
import torch.nn as nn
from torch_geometric.data import Data
from torch_geometric.loader import DataLoader
from torch_geometric.nn import GENConv
from torch_geometric.utils import to_undirected

try:
    from torch.utils.tensorboard import SummaryWriter
except Exception:
    SummaryWriter = None


class EdgeScoringGCN(nn.Module):
    """Layer-wise edge updates with undirected message passing."""

    def __init__(
        self,
        in_channels: int = 4,
        hidden_channels: int = 128,
        num_layers: int = 2,
        edge_dim: int = 1,
        dropout: float = 0.5,
    ) -> None:
        super().__init__()
        self.hidden_channels = hidden_channels
        self.num_layers = num_layers

        self.convs = nn.ModuleList()
        self.edge_updates = nn.ModuleList()

        current_node_dim = in_channels
        current_edge_dim = edge_dim

        for _ in range(num_layers):
            self.convs.append(GENConv(current_node_dim, hidden_channels, edge_dim=current_edge_dim))
            self.edge_updates.append(
                nn.Sequential(
                    nn.Linear(hidden_channels * 2 + current_edge_dim, hidden_channels),
                    nn.ReLU(),
                    nn.Linear(hidden_channels, hidden_channels),
                    nn.LayerNorm(hidden_channels),
                )
            )
            current_node_dim = hidden_channels
            current_edge_dim = hidden_channels

        self.act = nn.ReLU()
        self.dropout = nn.Dropout(dropout)
        self.edge_head = nn.Linear(hidden_channels, 1)

    def forward(self, data):
        x, edge_index, edge_attr = data.x, data.edge_index, data.edge_attr
        src, dst = edge_index

        h = x
        current_edge_attr = edge_attr

        for layer_idx in range(self.num_layers):
            undirected_edge_index, undirected_edge_attr = to_undirected(
                edge_index,
                edge_attr=current_edge_attr,
                num_nodes=x.size(0),
            )
            h = self.act(self.convs[layer_idx](h, undirected_edge_index, undirected_edge_attr))
            h = self.dropout(h)
            edge_input = torch.cat([h[src], h[dst], current_edge_attr], dim=-1)
            current_edge_attr = self.edge_updates[layer_idx](edge_input)

        pred = self.edge_head(self.dropout(current_edge_attr)).squeeze(-1)
        out = {"edge_pred": pred}
        if hasattr(data, "product_num") and hasattr(data, "segment_num"):
            try:
                n = int(data.product_num)
                m = int(data.segment_num)
                if pred.numel() == n * m:
                    out["pred_matrix"] = pred.view(n, m)
            except Exception:
                pass
        return out


if hasattr(torch.serialization, "add_safe_globals"):
    torch.serialization.add_safe_globals([EdgeScoringGCN])

plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def _split_indices(n: int, val_ratio: float, seed: int = 42) -> Tuple[List[int], List[int]]:
    indices = list(range(n))
    random.Random(seed).shuffle(indices)
    val_size = int(round(n * val_ratio))
    val_indices = indices[:val_size]
    train_indices = indices[val_size:]
    if len(train_indices) == 0 and n > 0:
        train_indices, val_indices = indices[:-1], indices[-1:]
    return train_indices, val_indices


def _ensure_dirs(*dirs: str) -> None:
    for d in dirs:
        os.makedirs(d, exist_ok=True)


def _clean_previous_run_artifacts(model_dir: str, keep_best: bool = True, suffix: str = "") -> None:
    patterns = [
        os.path.join(model_dir, f"model_edge_cpbsd_q{suffix}.pt"),
        os.path.join(model_dir, f"best_model_edge_cpbsd_q{suffix}.pt"),
        os.path.join(model_dir, f"train_loss_edge_cpbsd_q{suffix}.csv"),
        os.path.join(model_dir, f"val_loss_edge_cpbsd_q{suffix}.csv"),
        os.path.join(model_dir, f"metrics_edge_cpbsd_q{suffix}.json"),
    ]
    for f in patterns:
        if keep_best and "best_model" in f:
            continue
        if os.path.exists(f):
            try:
                os.remove(f)
            except Exception:
                pass


def _match_instance_result_pairs(
    instance_dir: str,
    result_dir: str,
    result_suffix: str = "__cpbsd_milp.json",
    max_files: int = 0,
) -> List[Tuple[Path, Path]]:
    instance_dir_path = Path(instance_dir)
    result_dir_path = Path(result_dir)
    pairs = []
    instance_map = {path.stem: path for path in instance_dir_path.rglob("*.msgpack")}

    result_files = sorted(result_dir_path.glob(f"*{result_suffix}"))
    for result_path in result_files:
        stem = result_path.name[: -len(result_suffix)]
        instance_path = instance_map.get(stem)
        if instance_path is None:
            continue
        pairs.append((instance_path, result_path))
        if max_files > 0 and len(pairs) >= max_files:
            break
    return pairs


def _read_result_manifest(path: str) -> List[Tuple[Path, Path]]:
    rows = []
    with open(path, "r", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("has_solution", "").lower() not in {"true", "1"}:
                continue
            instance_path = Path(row["instance_path"])
            result_path = Path(row["result_path"])
            if instance_path.exists() and result_path.exists():
                rows.append((instance_path, result_path))
    return rows


def read_cpbsd_data(instance_path: str, result_path: str) -> Tuple[Data, Dict]:
    with open(instance_path, "rb") as f:
        instance = msgpack.load(f, object_hook=mnp.decode, strict_map_key=False)
    with open(result_path, "r", encoding="utf-8") as f:
        result = json.load(f)

    if "solution" not in result:
        raise ValueError(f"Result file has no solution: {result_path}")

    v_kn = np.asarray(instance["valuation_samples_V"], dtype=float)
    c_n = np.asarray(instance["production_cost_c"], dtype=float)
    q_kns = np.asarray(result["solution"]["q"], dtype=float)

    if q_kns.ndim != 3:
        raise ValueError(f"Expected q to be 3D (K,N,S+1), got shape {q_kns.shape}")

    k_count, n_products = v_kn.shape
    q_kn = q_kns.sum(axis=2)

    feature_mat = np.zeros((n_products + k_count, 4), dtype=float)
    feature_mat[:n_products, 0] = c_n
    feature_mat[:n_products, 1] = np.mean(v_kn, axis=0)

    rho_k = np.mean((v_kn - c_n[None, :]) > 0, axis=1)
    feature_mat[n_products:, 2] = float(k_count)
    feature_mat[n_products:, 3] = rho_k

    x = torch.tensor(feature_mat, dtype=torch.float)

    left_nodes = []
    right_nodes = []
    edge_attr = []
    edge_label = []
    for product_idx in range(n_products):
        for customer_idx in range(k_count):
            left_nodes.append(product_idx)
            right_nodes.append(customer_idx + n_products)
            edge_attr.append([v_kn[customer_idx, product_idx]])
            edge_label.append(q_kn[customer_idx, product_idx])

    edge_index = torch.tensor([left_nodes, right_nodes], dtype=torch.long)
    edge_attr = torch.tensor(edge_attr, dtype=torch.float)
    edge_label = torch.tensor(edge_label, dtype=torch.float)
    side_ind = torch.tensor(np.array([1] * n_products + [0] * k_count)[:, None], dtype=torch.long)

    data = Data(
        x=x,
        edge_index=edge_index,
        edge_attr=edge_attr,
        edge_label=edge_label,
        side_ind=side_ind,
        y=torch.empty(0, dtype=torch.long),
    )
    data.product_num = n_products
    data.segment_num = k_count

    meta = {
        "instance_path": str(instance_path),
        "result_path": str(result_path),
        "setup": instance.get("setup", {}),
        "product_num": n_products,
        "segment_num": k_count,
        "edge_label_mean": float(np.mean(edge_label.numpy())),
        "edge_label_max": float(np.max(edge_label.numpy())),
        "positive_edge_rate": float(np.mean(edge_label.numpy() > 0)),
        "solver_status": result.get("solver_status"),
        "solver_runtime": result.get("runtime"),
    }
    return data, meta


def train(
    instance_dir: str = "/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/cpbsd_main_n5/instances",
    result_dir: str = "/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/cpbsd_main_n5/results",
    model_dir: str = "/Users/sensen/.openclaw/workspace/domains/revenue-management/project-root/code_submission_project/code_submission/models_cpbsd_q",
    charts_dir: str = "/Users/sensen/.openclaw/workspace/domains/revenue-management/project-root/code_submission_project/code_submission/charts_cpbsd_q",
    log_dir: str = "/Users/sensen/.openclaw/workspace/domains/revenue-management/project-root/code_submission_project/code_submission/log_cpbsd_q",
    result_suffix: str = "__cpbsd_milp.json",
    train_manifest: str = "",
    eval_manifest: str = "",
    test_manifest: str = "",
    max_files: int = 0,
    epochs: int = 200,
    batch_size: int = 32,
    learning_rate: float = 1e-3,
    hidden_channels: int = 128,
    num_layers: int = 2,
    save_interval: int = 100,
    val_ratio: float = 0.2,
    early_stopping_patience: int = 30,
    seed: int = 42,
    cleanup_before_train: bool = True,
) -> Tuple[torch.nn.Module, np.ndarray, Optional[np.ndarray]]:
    torch.manual_seed(seed)
    np.random.seed(seed)
    random.seed(seed)

    if torch.cuda.is_available():
        device = torch.device("cuda")
        print(f"✅ CUDA可用: {torch.cuda.get_device_name()}")
    else:
        device = torch.device("cpu")
        print("⚠️ CUDA不可用，使用CPU训练")

    _ensure_dirs(model_dir, charts_dir, log_dir)
    suffix = f"_{num_layers}layer_seed{seed}"
    if cleanup_before_train:
        _clean_previous_run_artifacts(model_dir, keep_best=True, suffix=suffix)

    class _DummyWriter:
        def add_scalar(self, *args, **kwargs):
            pass
        def flush(self):
            pass
        def close(self):
            pass

    if SummaryWriter is None:
        writer = _DummyWriter()
    else:
        try:
            writer = SummaryWriter(log_dir=log_dir)
        except Exception:
            writer = _DummyWriter()

    explicit_split = bool(train_manifest or eval_manifest or test_manifest)
    if explicit_split:
        if not train_manifest or not eval_manifest:
            raise ValueError("When using explicit manifests, both train_manifest and eval_manifest are required.")
        split_pairs = {
            "train": _read_result_manifest(train_manifest),
            "eval": _read_result_manifest(eval_manifest),
            "test": _read_result_manifest(test_manifest) if test_manifest else [],
        }
    else:
        pairs = _match_instance_result_pairs(instance_dir, result_dir, result_suffix=result_suffix, max_files=max_files)
        if not pairs:
            raise FileNotFoundError(
                f"No matched instance/result pairs found under instance_dir={instance_dir}, result_dir={result_dir}, suffix={result_suffix}"
            )
        split_pairs = {"all": pairs}

    split_datasets: Dict[str, List[Data]] = {}
    split_metas: Dict[str, List[Dict]] = {}
    for split_name, pairs in split_pairs.items():
        if not pairs:
            split_datasets[split_name] = []
            split_metas[split_name] = []
            continue
        split_datasets[split_name] = []
        split_metas[split_name] = []
        print(f"Start reading the CPBSD dataset for split={split_name}...")
        for idx, (instance_path, result_path) in enumerate(pairs, 1):
            try:
                dat, meta = read_cpbsd_data(str(instance_path), str(result_path))
                split_datasets[split_name].append(dat)
                split_metas[split_name].append(meta)
            except Exception as exc:
                print(f"⚠️ Skip pair due to read failure: {instance_path.name} / {result_path.name}: {exc}")
            if idx % 50 == 0:
                print(f"Loaded data ({split_name}): {idx}/{len(pairs)}")

    if explicit_split:
        train_data = split_datasets["train"]
        val_data = split_datasets["eval"]
        test_data = split_datasets["test"]
        dataset = train_data + val_data + test_data
        metas = split_metas["train"] + split_metas["eval"] + split_metas["test"]
    else:
        dataset = split_datasets["all"]
        metas = split_metas["all"]
        if not dataset:
            raise RuntimeError("No CPBSD training samples were loaded successfully.")
        train_idx, val_idx = _split_indices(len(dataset), val_ratio, seed)
        train_data = [dataset[i] for i in train_idx]
        val_data = [dataset[i] for i in val_idx]
        test_data = []

    if not train_data or not val_data:
        raise RuntimeError("Training or validation split is empty after loading CPBSD labeled data.")

    print(f"📦 总计加载 {len(dataset)} 个样本")
    pos_rate = float(np.mean(np.concatenate([(d.edge_label.numpy() > 0).astype(float) for d in dataset])))
    print(f"📈 全局正边比例(q_kn>0): {pos_rate:.6f}")
    print(f"  训练集: {len(train_data)}")
    print(f"  验证集: {len(val_data)}")
    if test_data:
        print(f"  测试集: {len(test_data)}")

    train_loader = DataLoader(train_data, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_data, batch_size=batch_size, shuffle=False) if val_data else None
    test_loader = DataLoader(test_data, batch_size=batch_size, shuffle=False) if test_data else None

    model = EdgeScoringGCN(
        in_channels=4,
        hidden_channels=hidden_channels,
        num_layers=num_layers,
        edge_dim=1,
        dropout=0.5,
    ).to(device)

    raw_pos_rate = float(np.mean(np.concatenate([(d.edge_label.numpy() > 0).astype(float) for d in train_data])))
    raw_pos_rate = min(max(raw_pos_rate, 1e-6), 1 - 1e-6)
    positive_weight = min((1.0 - raw_pos_rate) / raw_pos_rate, 20.0)
    print(f"⚖️ 训练集正边比例(q_kn>0): {raw_pos_rate:.6f}, positive_weight={positive_weight:.3f}")

    criterion = nn.SmoothL1Loss(reduction="none")
    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)

    def compute_loss(pred: torch.Tensor, label: torch.Tensor) -> torch.Tensor:
        base = criterion(pred, label)
        weights = torch.ones_like(label)
        weights = torch.where(label > 0, weights * positive_weight, weights)
        return (base * weights).mean()

    def _eval(loader: Optional[DataLoader]) -> Tuple[float, float, float, float, float, float, float]:
        if loader is None or len(loader) == 0:
            return float("inf"), float("inf"), float("inf"), float("inf"), float("inf"), float("inf"), float("inf")
        model.eval()
        total_loss = 0.0
        total_mae = 0.0
        total_mse = 0.0
        total_pred_sum = 0.0
        total_pred_sq = 0.0
        total_label_sum = 0.0
        total_label_sq = 0.0
        total_items = 0
        count = 0
        with torch.no_grad():
            for batch in loader:
                batch = batch.to(device)
                pred = model(batch)["edge_pred"].view(-1)
                label = batch.edge_label.to(pred.dtype).view(-1)
                total_loss += float(compute_loss(pred, label).item())
                total_mae += float(torch.mean(torch.abs(pred - label)).item())
                total_mse += float(torch.mean((pred - label) ** 2).item())
                total_pred_sum += float(pred.sum().item())
                total_pred_sq += float((pred ** 2).sum().item())
                total_label_sum += float(label.sum().item())
                total_label_sq += float((label ** 2).sum().item())
                total_items += int(label.numel())
                count += 1
        pred_mean = total_pred_sum / max(1, total_items)
        label_mean = total_label_sum / max(1, total_items)
        pred_std = max(total_pred_sq / max(1, total_items) - pred_mean**2, 0.0) ** 0.5
        label_std = max(total_label_sq / max(1, total_items) - label_mean**2, 0.0) ** 0.5
        return total_loss / count, total_mae / count, total_mse / count, pred_mean, pred_std, label_mean, label_std

    best_val = float("inf")
    patience = 0
    best_model_path = os.path.join(model_dir, f"best_model_edge_cpbsd_q{suffix}.pt")
    final_model_path = os.path.join(model_dir, f"model_edge_cpbsd_q{suffix}.pt")
    metrics_path = os.path.join(model_dir, f"metrics_edge_cpbsd_q{suffix}.json")

    train_hist: List[Tuple[int, float]] = []
    val_hist: List[Tuple[int, float]] = []
    metrics = []

    print(f"\n开始训练 {epochs} 轮...")
    for epoch in range(epochs):
        model.train()
        total_train = 0.0
        total_train_mae = 0.0
        for batch in train_loader:
            batch = batch.to(device)
            pred = model(batch)["edge_pred"].view(-1)
            label = batch.edge_label.to(pred.dtype).view(-1)
            optimizer.zero_grad()
            loss = compute_loss(pred, label)
            loss.backward()
            optimizer.step()
            total_train += float(loss.item())
            total_train_mae += float(torch.mean(torch.abs(pred - label)).item())

        avg_train = total_train / max(1, len(train_loader))
        avg_train_mae = total_train_mae / max(1, len(train_loader))
        train_hist.append((epoch, avg_train))
        writer.add_scalar("Loss/train", avg_train, epoch)
        writer.add_scalar("MAE/train", avg_train_mae, epoch)

        avg_val, avg_val_mae, avg_val_mse, val_pred_mean, val_pred_std, val_label_mean, val_label_std = _eval(val_loader)
        if np.isfinite(avg_val):
            val_hist.append((epoch, avg_val))
            writer.add_scalar("Loss/validation", avg_val, epoch)
            writer.add_scalar("MAE/validation", avg_val_mae, epoch)
            writer.add_scalar("MSE/validation", avg_val_mse, epoch)

            if avg_val < best_val - 1e-12:
                best_val = avg_val
                patience = 0
                model_cpu = model.cpu()
                torch.save(model_cpu, best_model_path)
                model = model_cpu.to(device)
                print(f"  🎯 新最佳模型：val_loss={avg_val:.6f}, val_mae={avg_val_mae:.6f} (epoch={epoch})")
            else:
                patience += 1
                if patience >= early_stopping_patience:
                    print(f"  ⏹️ 触发早停（连续 {early_stopping_patience} 轮无改进）")
                    break

        metrics.append(
            {
                "epoch": epoch,
                "train_loss": avg_train,
                "train_mae": avg_train_mae,
                "val_loss": avg_val,
                "val_mae": avg_val_mae,
                "val_mse": avg_val_mse,
                "val_pred_mean": val_pred_mean,
                "val_pred_std": val_pred_std,
                "val_label_mean": val_label_mean,
                "val_label_std": val_label_std,
            }
        )

        if epoch % 20 == 0:
            if np.isfinite(avg_val):
                print(
                    f"Epoch {epoch:3d} | train_loss={avg_train:.6f} | train_mae={avg_train_mae:.6f} | "
                    f"val_loss={avg_val:.6f} | val_mae={avg_val_mae:.6f} | val_pred_std={val_pred_std:.6f}"
                )
            else:
                print(f"Epoch {epoch:3d} | train_loss={avg_train:.6f} | train_mae={avg_train_mae:.6f}")

        if epoch % save_interval == 0 and epoch > 0:
            ckpt_path = os.path.join(model_dir, f"model_edge_cpbsd_q{suffix}_epoch{epoch}.pt")
            model_cpu = model.cpu()
            torch.save(model_cpu, ckpt_path)
            model = model_cpu.to(device)

    if os.path.exists(best_model_path):
        best_model = torch.load(best_model_path, weights_only=False)
        torch.save(best_model, final_model_path)
    else:
        model_cpu = model.cpu()
        torch.save(model_cpu, final_model_path)

    train_hist_np = np.array(train_hist, dtype=float)
    np.savetxt(os.path.join(model_dir, f"train_loss_edge_cpbsd_q{suffix}.csv"), train_hist_np, delimiter=",")
    if val_hist:
        val_hist_np = np.array(val_hist, dtype=float)
        np.savetxt(os.path.join(model_dir, f"val_loss_edge_cpbsd_q{suffix}.csv"), val_hist_np, delimiter=",")
    else:
        val_hist_np = None

    train_eval = _eval(train_loader)
    val_eval = _eval(val_loader)
    test_eval = _eval(test_loader) if test_loader is not None else None

    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "config": {
                    "instance_dir": instance_dir,
                    "result_dir": result_dir,
                    "result_suffix": result_suffix,
                    "train_manifest": train_manifest,
                    "eval_manifest": eval_manifest,
                    "test_manifest": test_manifest,
                    "max_files": max_files,
                    "epochs": epochs,
                    "batch_size": batch_size,
                    "learning_rate": learning_rate,
                    "hidden_channels": hidden_channels,
                    "num_layers": num_layers,
                    "val_ratio": val_ratio,
                    "seed": seed,
                    "positive_weight": positive_weight,
                },
                "dataset_summary": {
                    "num_samples": len(dataset),
                    "num_train": len(train_data),
                    "num_val": len(val_data),
                    "num_test": len(test_data),
                    "global_positive_edge_rate": pos_rate,
                    "global_edge_label_mean": float(np.mean([m["edge_label_mean"] for m in metas])),
                    "global_edge_label_max": float(np.max([m["edge_label_max"] for m in metas])),
                },
                "split_metrics": {
                    "train": {
                        "loss": train_eval[0],
                        "mae": train_eval[1],
                        "mse": train_eval[2],
                        "pred_mean": train_eval[3],
                        "pred_std": train_eval[4],
                        "label_mean": train_eval[5],
                        "label_std": train_eval[6],
                    },
                    "eval": {
                        "loss": val_eval[0],
                        "mae": val_eval[1],
                        "mse": val_eval[2],
                        "pred_mean": val_eval[3],
                        "pred_std": val_eval[4],
                        "label_mean": val_eval[5],
                        "label_std": val_eval[6],
                    },
                    "test": None
                    if test_eval is None
                    else {
                        "loss": test_eval[0],
                        "mae": test_eval[1],
                        "mse": test_eval[2],
                        "pred_mean": test_eval[3],
                        "pred_std": test_eval[4],
                        "label_mean": test_eval[5],
                        "label_std": test_eval[6],
                    },
                },
                "metrics": metrics,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    run_tag = datetime.now().strftime("%Y%m%d-%H%M%S")
    chart_dir = os.path.join(charts_dir, f"run_{run_tag}_cpbsd_q_{num_layers}layer_seed{seed}")
    _ensure_dirs(chart_dir)

    plt.figure(figsize=(10, 7))
    plt.plot(train_hist_np[:, 0], train_hist_np[:, 1], label="Training Loss", color="C0")
    if val_hist_np is not None:
        plt.plot(val_hist_np[:, 0], val_hist_np[:, 1], label="Validation Loss", color="C3")
    plt.xlabel("Epoch")
    plt.ylabel("Weighted SmoothL1 Loss")
    plt.title(f"CPBSD q_kn Training Loss ({num_layers} layers, seed={seed})")
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    fig_path = os.path.join(chart_dir, f"loss_curves_cpbsd_q_{num_layers}layer_seed{seed}.png")
    plt.savefig(fig_path, dpi=300, bbox_inches="tight")
    plt.close()

    writer.flush()
    writer.close()

    print("\n✅ 训练完成！")
    print(f"  最终模型: {final_model_path}")
    print(f"  指标文件: {metrics_path}")
    print(f"  曲线图: {fig_path}")

    return model, train_hist_np, val_hist_np


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train CPBSD edge-scoring GCN with q_kn supervision")
    parser.add_argument("--instance_dir", type=str, default="/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/cpbsd_main_n5/instances")
    parser.add_argument("--result_dir", type=str, default="/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/cpbsd_main_n5/results")
    parser.add_argument("--model_dir", type=str, default="/Users/sensen/.openclaw/workspace/domains/revenue-management/project-root/code_submission_project/code_submission/models_cpbsd_q")
    parser.add_argument("--charts_dir", type=str, default="/Users/sensen/.openclaw/workspace/domains/revenue-management/project-root/code_submission_project/code_submission/charts_cpbsd_q")
    parser.add_argument("--log_dir", type=str, default="/Users/sensen/.openclaw/workspace/domains/revenue-management/project-root/code_submission_project/code_submission/log_cpbsd_q")
    parser.add_argument("--result_suffix", type=str, default="__cpbsd_milp.json")
    parser.add_argument("--train_manifest", type=str, default="")
    parser.add_argument("--eval_manifest", type=str, default="")
    parser.add_argument("--test_manifest", type=str, default="")
    parser.add_argument("--max_files", type=int, default=0, help="0 means use all matched pairs")
    parser.add_argument("--epochs", type=int, default=200)
    parser.add_argument("--batch_size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--hidden", type=int, default=128)
    parser.add_argument("--num_layers", type=int, default=2)
    parser.add_argument("--save_interval", type=int, default=100)
    parser.add_argument("--val_ratio", type=float, default=0.2)
    parser.add_argument("--patience", type=int, default=30)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--no_cleanup", action="store_true")
    args = parser.parse_args()

    train(
        instance_dir=args.instance_dir,
        result_dir=args.result_dir,
        model_dir=args.model_dir,
        charts_dir=args.charts_dir,
        log_dir=args.log_dir,
        result_suffix=args.result_suffix,
        train_manifest=args.train_manifest,
        eval_manifest=args.eval_manifest,
        test_manifest=args.test_manifest,
        max_files=args.max_files,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.lr,
        hidden_channels=args.hidden,
        num_layers=args.num_layers,
        save_interval=args.save_interval,
        val_ratio=args.val_ratio,
        early_stopping_patience=args.patience,
        seed=args.seed,
        cleanup_before_train=(not args.no_cleanup),
    )
