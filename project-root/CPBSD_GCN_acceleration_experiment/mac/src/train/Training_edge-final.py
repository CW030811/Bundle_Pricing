"""
Edge-Scoring GCN Model Training Script

Objective: Minimize changes to the original Training.py structure while
changing the output head to "edge-scoring", using BCEWithLogitsLoss to supervise each edge,
making the model naturally adaptive to segment_num (no need to fix out_channels=segment_num).

Main differences:
- Model: Change from GEN_GCN(out_channels=m) to EdgeScoringGCN (no out_channels).
- Labels: Don't use batch.y; change to data.edge_label (shape=(E,)).
- Loss: CrossEntropyLoss -> BCEWithLogitsLoss (optional pos_weight).

Save paths, logging and curve plotting, early stopping logic, etc., all remain consistent with the original Training.py.
"""

from __future__ import annotations
import os
import random
from typing import List, Tuple, Optional

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import GENConv
from torch_geometric.loader import DataLoader
from torch.utils.tensorboard import SummaryWriter
import matplotlib.pyplot as plt
import glob
from datetime import datetime

from bundle_utils import read_data  # Directly reuse original data reading

class EdgeScoringGCN(nn.Module):
    def __init__(
        self,
        in_channels: int = 4,
        hidden_channels: int = 128,
        num_layers: int = 2,
        edge_dim: int = 1,
        score_type: str = 'bilinear',  # 'bilinear' | 'dot' | 'mlp'
        proj_dim: int | None = None,   # for 'dot'
        use_edge_attr: bool = True,
        dropout: float = 0.5,
    ) -> None:
        super().__init__()
        self.use_edge_attr = use_edge_attr
        self.score_type = score_type

        # Directional GENConv stacks: left->right and right->left
        self.l2r = nn.ModuleList()
        self.r2l = nn.ModuleList()
        c_in = in_channels
        for _ in range(num_layers):
            self.l2r.append(GENConv(c_in, hidden_channels, edge_dim=edge_dim))
            self.r2l.append(GENConv(c_in, hidden_channels, edge_dim=edge_dim))
            c_in = hidden_channels

        self.dropout = nn.Dropout(dropout)

        # Edge-scoring head
        if score_type == 'bilinear':
            self.U = nn.Parameter(torch.empty(hidden_channels, hidden_channels))
            nn.init.xavier_uniform_(self.U)
        elif score_type == 'dot':
            d = proj_dim or hidden_channels
            self.proj_p = nn.Linear(hidden_channels, d, bias=False)
            self.proj_s = nn.Linear(hidden_channels, d, bias=False)
        elif score_type == 'mlp':
            d_in = hidden_channels * 2 + (edge_dim if use_edge_attr else 0)
            self.mlp = nn.Sequential(
                nn.Linear(d_in, hidden_channels),
                nn.ReLU(),
                nn.Linear(hidden_channels, 1),
            )
        else:
            raise ValueError(f"Unknown score_type={score_type}")

        if use_edge_attr and score_type in ('bilinear', 'dot'):
            self.edge_mlp = nn.Sequential(
                nn.Linear(edge_dim, hidden_channels),
                nn.ReLU(),
                nn.Linear(hidden_channels, 1),
            )

    def forward(self, data):
        x, edge_index, edge_attr, side_ind = data.x, data.edge_index, data.edge_attr, data.side_ind
        rev_edge_index = edge_index.flip(dims=[0])

        # Encoder: blend left-to-right and right-to-left messages
        for l2r_conv, r2l_conv in zip(self.l2r, self.r2l):
            r_x = l2r_conv(x, edge_index, edge_attr)
            l_x = r2l_conv(x, rev_edge_index, edge_attr)
            x = F.relu(r_x * (1 - side_ind) + l_x * side_ind)
            x = self.dropout(x)

        z = x  # node embeddings, shape (N, H)
        src, dst = edge_index  # edge endpoints

        # Edge scoring
        if self.score_type == 'bilinear':
            # s_e = h_src^T U h_dst
            s = torch.einsum('ei,ij,ej->e', z[src], self.U, z[dst])
            if self.use_edge_attr:
                s = s + self.edge_mlp(edge_attr).squeeze(-1)
        elif self.score_type == 'dot':
            s = (self.proj_p(z[src]) * self.proj_s(z[dst])).sum(dim=-1)
            if self.use_edge_attr:
                s = s + self.edge_mlp(edge_attr).squeeze(-1)
        else:  # 'mlp'
            feats = [z[src], z[dst]]
            if self.use_edge_attr:
                feats.append(edge_attr)
            s = self.mlp(torch.cat(feats, dim=-1)).squeeze(-1)

        out = { 'edge_logits': s }

        # Optional matrix view for single-graph inference
        if hasattr(data, 'product_num') and hasattr(data, 'segment_num'):
            try:
                n = int(data.product_num)
                m = int(data.segment_num)
                if s.numel() == n * m:
                    out['logit_matrix'] = s.view(n, m)
            except Exception:
                pass

        return out


# Fix PyTorch 2.6 weights_only issue - add safe global variables
if hasattr(torch.serialization, 'add_safe_globals'):
    torch.serialization.add_safe_globals([EdgeScoringGCN])

# Matplotlib font configuration
plt.rcParams["font.sans-serif"] = ["DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def _split_indices(n: int, val_ratio: float, seed: int = 42) -> Tuple[List[int], List[int]]:
    """Manually split train/validation indices to avoid extra sklearn dependency
    Returns (train_indices, val_indices)
    """
    indices = list(range(n))
    random.Random(seed).shuffle(indices)
    val_size = int(round(n * val_ratio))
    val_indices = indices[:val_size]
    train_indices = indices[val_size:]
    # Prevent extreme cases where it's empty
    if len(train_indices) == 0 and n > 0:
        train_indices, val_indices = indices[:-1], indices[-1:]
    return train_indices, val_indices


def _ensure_dirs(*dirs: str) -> None:
    for d in dirs:
        os.makedirs(d, exist_ok=True)


def _clean_previous_run_artifacts(model_dir: str, keep_best: bool = True) -> None:
    """Clean artifacts generated by previous training runs in the dataset directory to avoid accumulating obsolete files.
    - Default to keep best_model.pt
    - Clean model.pt, model-*.pt, train_loss*.csv, val_loss*.csv, training_curves*.png
    """
    patterns = [
        os.path.join(model_dir, "model-*.pt"),
        os.path.join(model_dir, "train_loss*.csv"),
        os.path.join(model_dir, "val_loss*.csv"),
        os.path.join(model_dir, "training_curves*.png"),
    ]
    target_model_pt = os.path.join(model_dir, "model.pt")
    if os.path.exists(target_model_pt):
        try:
            os.remove(target_model_pt)
        except Exception:
            pass

    for pat in patterns:
        for f in glob.glob(pat):
            try:
                os.remove(f)
            except Exception:
                pass

    if not keep_best:
        best_path = os.path.join(model_dir, "best_model_edge.pt")
        if os.path.exists(best_path):
            try:
                os.remove(best_path)
            except Exception:
                pass


def _attach_edge_labels_to_data(data, meta):
    """Generate supervision labels for each edge based on opt_bundles in meta.
    - Edge construction order in read_data is: for i in products, for j in segments
    - Corresponding labels should be: label[i,j] = opt_bundles[j, i]
    """
    product_num = int(meta[0])
    segment_num = int(meta[1])
    opt_bundles = np.asarray(meta[8])  # shape (segment_num, product_num)
    # Vectorized: transpose then flatten by row, order same as edge construction in read_data (product i first, then segment j)
    edge_label = torch.tensor(opt_bundles.T.reshape(-1), dtype=torch.float)
    data.edge_label = edge_label
    # This training script doesn't use data.y. To avoid dimension mismatch when DataLoader concatenates y with different m, set it to empty tensor.
    try:
        data.y = torch.empty(0, dtype=torch.long)
    except Exception:
        pass
    data.product_num = product_num
    data.segment_num = segment_num
    return data


def train(
    data_dir: str = "./dataset",
    train_subdir: str = "train/",
    epochs: int = 500,
    batch_size: int = 512,
    learning_rate: float = 0.01,
    hidden_channels: int = 128,
    segment_num: int = 10,           # Only for logging and compatibility; model no longer depends on it
    save_interval: int = 100,
    val_ratio: float = 0.2,          # 8:2 split
    early_stopping_patience: int = 50,
    save_best_as_model_pt: bool = True,
    seed: int = 42,
    cleanup_before_train: bool = True,
    cleanup_keep_best: bool = True,
) -> Tuple[torch.nn.Module, np.ndarray, Optional[np.ndarray]]:
    """Train EdgeScoringGCN model
    Parameter descriptions same as original Training.py; segment_num kept for compatibility (model doesn't need out_channels).
    Returns: model, train_loss_hist, val_loss_hist
    """
    torch.manual_seed(seed)
    np.random.seed(seed)
    random.seed(seed)

    # Device
    if torch.cuda.is_available():
        device = torch.device('cuda')
        print(f"CUDA available: {torch.cuda.get_device_name()}")
        try:
            print(f"   GPU memory: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")
        except Exception:
            pass
    else:
        device = torch.device('cpu')
        print("CUDA not available, using CPU training")

    train_path = os.path.join(data_dir, train_subdir)
    model_dir = os.path.join(data_dir, "models")
    charts_root = os.path.join(data_dir, "charts")
    log_dir = os.path.join(data_dir, "log")
    if os.path.exists(log_dir) and not os.path.isdir(log_dir):
        alt_log_dir = os.path.join(data_dir, "tensorboard_logs")
        print(f"Warning: Detected {log_dir} exists but is not a directory, using {alt_log_dir} as log directory")
        log_dir = alt_log_dir
    _ensure_dirs(model_dir, charts_root, log_dir)

    # Clean historical artifacts
    if cleanup_before_train:
        _clean_previous_run_artifacts(model_dir, keep_best=cleanup_keep_best)

    # TensorBoard logging
    try:
        writer = SummaryWriter(log_dir=log_dir)
    except Exception as e:
        print(f"Warning: TensorBoard initialization failed, trying fallback. Reason: {e}")
        alt_log_dir = os.path.join(model_dir, "tb_logs")
        _ensure_dirs(alt_log_dir)
        try:
            writer = SummaryWriter(log_dir=alt_log_dir)
            print(f"Info: Fallback to {alt_log_dir} as log directory")
        except Exception as e2:
            print(f"Warning: Fallback still failed, will disable TensorBoard logging. Reason: {e2}")
            class _DummyWriter:
                def add_scalar(self, *args, **kwargs):
                    pass
                def flush(self):
                    pass
                def close(self):
                    pass
            writer = _DummyWriter()

    # Load data
    if not os.path.exists(train_path):
        raise FileNotFoundError(f"Training data path does not exist: {train_path}")

    file_list = [f for f in os.listdir(train_path) if f != ".DS_Store"]
    file_list.sort()
    dataset = []

    print("Start reading the dataset…")
    for i, fname in enumerate(file_list, 1):
        dat, meta = read_data(os.path.join(train_path, fname))
        dat = _attach_edge_labels_to_data(dat, meta)
        dataset.append(dat)
        if i % 100 == 0:
            print(f"Loaded data: {i}/{len(file_list)}")
    print(f"Total loaded {len(dataset)} samples")

    # Split 8:2 train/validation
    train_idx, val_idx = _split_indices(len(dataset), val_ratio, seed)
    train_data = [dataset[i] for i in train_idx]
    val_data = [dataset[i] for i in val_idx]

    print("Data split results:")
    print(f"  Training set: {len(train_data)} ({(1-val_ratio)*100:.1f}%)")
    print(f"  Validation set: {len(val_data)} ({val_ratio*100:.1f}%)")

    train_loader = DataLoader(train_data, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_data, batch_size=batch_size, shuffle=False) if val_data else None

    # Class imbalance: one-time statistics of pos_weight based on training set to avoid per-batch fluctuation
    total_pos = 0.0
    total_cnt = 0
    for dat in train_data:
        el = dat.edge_label
        total_pos += float(el.sum().item())
        total_cnt += int(el.numel())
    pos_rate = (total_pos / max(1, total_cnt)) if total_cnt > 0 else 0.0
    pos_rate = float(min(max(pos_rate, 1e-6), 1 - 1e-6))
    pos_weight_value = (1.0 - pos_rate) / pos_rate
    pos_weight_tensor = torch.tensor(pos_weight_value, dtype=torch.float, device=device)
    criterion_bce = nn.BCEWithLogitsLoss(pos_weight=pos_weight_tensor)
    print(f"Global positive rate pos_rate={pos_rate:.6f}, using pos_weight={pos_weight_value:.3f}")

    # Initialize model (consistent with original script style)
    print(f"Initializing EdgeScoringGCN (hidden_channels={hidden_channels})")
    model = EdgeScoringGCN(
        in_channels=4,
        hidden_channels=hidden_channels,
        num_layers=3,
        edge_dim=1,
        score_type='bilinear',  # Can switch to 'dot' / 'mlp'
        use_edge_attr=True,
        dropout=0.5,
    )
    model = model.to(device)
    print(f"Model moved to device: {device}")

    # Imbalance option: use BCE with pos_weight
    def _make_bce(labels: torch.Tensor):
        p = labels.mean()
        p = torch.clamp(p, min=1e-6, max=1-1e-6)
        pos_weight = (1 - p) / p
        return nn.BCEWithLogitsLoss(pos_weight=pos_weight)

    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)

    def _eval(model_: torch.nn.Module, loader: Optional[DataLoader]) -> float:
        if loader is None or len(loader) == 0:
            return float("inf")
        model_.eval()
        total = 0.0
        with torch.no_grad():
            for batch in loader:
                batch = batch.to(device)
                out = model_(batch)
                logits = out['edge_logits'].view(-1)
                labels = batch.edge_label.to(logits.dtype).view(-1)
                loss = criterion_bce(logits, labels)
                total += float(loss.item())
        return total / max(1, len(loader))

    best_val = float("inf")
    patience = 0
    best_model_path = os.path.join(model_dir, "best_model_edge.pt")

    train_hist: List[Tuple[int, float]] = []
    val_hist: List[Tuple[int, float]] = []

    print(f"\nStarting training for {epochs} epochs...")
    for epoch in range(epochs):
        # Training
        model.train()
        total_train = 0.0
        for batch in train_loader:
            batch = batch.to(device)
            out = model(batch)
            logits = out['edge_logits'].view(-1)
            labels = batch.edge_label.to(logits.dtype).view(-1)
            optimizer.zero_grad()
            loss = criterion_bce(logits, labels)
            loss.backward()
            optimizer.step()
            total_train += float(loss.item())

        avg_train = total_train / max(1, len(train_loader))
        writer.add_scalar("Loss/train", avg_train, epoch)
        train_hist.append((epoch, avg_train))

        # Validation
        avg_val = _eval(model, val_loader)
        if val_loader is not None and np.isfinite(avg_val):
            writer.add_scalar("Loss/validation", avg_val, epoch)
            val_hist.append((epoch, avg_val))

            # Best model saving + early stopping
            if avg_val < best_val - 1e-12:
                best_val = avg_val
                patience = 0
                model_cpu = model.cpu()
                torch.save(model_cpu, best_model_path)
                model = model_cpu.to(device)  # Move back to continue training
                print(f"  New best model: val_loss={avg_val:.6f} (epoch={epoch})")
            else:
                patience += 1
                if patience >= early_stopping_patience:
                    print(f"  Early stopping triggered (no improvement for {early_stopping_patience} consecutive epochs)")
                    break

        # Logging
        if epoch % 100 == 0:
            if val_loader is not None and np.isfinite(avg_val):
                print(f"Epoch {epoch:3d} | train={avg_train:.6f} | val={avg_val:.6f}")
            else:
                print(f"Epoch {epoch:3d} | train={avg_train:.6f}")

        # Intermediate checkpoint
        if epoch % save_interval == 0 and epoch > 0:
            ckpt_path = os.path.join(model_dir, f"model-{epoch}.pt")
            model_cpu = model.cpu()
            torch.save(model_cpu, ckpt_path)
            model = model_cpu.to(device)
            # Optional: save history
            np.savetxt(os.path.join(model_dir, f"train_loss-{epoch}.csv"), np.array(train_hist), delimiter=",")
            if val_hist:
                np.savetxt(os.path.join(model_dir, f"val_loss-{epoch}.csv"), np.array(val_hist), delimiter=",")
            print(f"  Saved checkpoint: {ckpt_path}")

    # Save after training ends
    final_model_path = os.path.join(model_dir, "model_edge.pt")
    if save_best_as_model_pt and os.path.exists(best_model_path):
        best_model = torch.load(best_model_path, weights_only=False)
        torch.save(best_model, final_model_path)
    else:
        model_cpu = model.cpu()
        torch.save(model_cpu, final_model_path)

    # Save complete loss history
    train_hist_np = np.array(train_hist, dtype=float)
    np.savetxt(os.path.join(model_dir, "train_loss_edge.csv"), train_hist_np, delimiter=",")
    if val_hist:
        val_hist_np = np.array(val_hist, dtype=float)
        np.savetxt(os.path.join(model_dir, "val_loss_edge.csv"), val_hist_np, delimiter=",")
    else:
        val_hist_np = None

    # Plot curves
    run_tag = datetime.now().strftime("%Y%m%d-%H%M%S")
    chart_dir = os.path.join(charts_root, f"run_{run_tag}_edge")
    _ensure_dirs(chart_dir)

    plt.figure(figsize=(10, 7))
    if val_hist:
        plt.plot(train_hist_np[:, 0], train_hist_np[:, 1], label="Training Loss", color="C0")
        plt.plot(val_hist_np[:, 0], val_hist_np[:, 1], label="Validation Loss", color="C3")
        title = f"Training & Validation Loss (epochs={epochs}, batch={batch_size}, lr={learning_rate}, hidden={hidden_channels})"
        plt.title(title)
    else:
        plt.plot(train_hist_np[:, 0], train_hist_np[:, 1], label="Training Loss", color="C0")
        title = f"Training Loss (epochs={epochs}, batch={batch_size}, lr={learning_rate}, hidden={hidden_channels})"
        plt.title(title)
    plt.xlabel("Epoch")
    plt.ylabel("Loss")
    plt.grid(True, alpha=0.3)
    plt.legend(title="Details")
    plt.tight_layout()
    fig_name = f"loss_curves_e{epochs}_b{batch_size}_h{hidden_channels}_lr{learning_rate}_edge.png"
    fig_path = os.path.join(chart_dir, fig_name)
    plt.savefig(fig_path, dpi=300, bbox_inches="tight")
    plt.close()

    writer.flush()
    writer.close()

    print("\nTraining completed!")
    print(f"  Final model: {final_model_path}")
    if os.path.exists(best_model_path):
        print(f"  Best model: {best_model_path} (val={best_val:.6f})")
    print(f"  Training curve: {fig_path}")
    print(f"  Chart directory: {chart_dir}")

    return model, train_hist_np, val_hist_np


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Train Edge-Scoring GCN with 8:2 val split, best-save, and early stopping")
    parser.add_argument("--data_dir", type=str, default="./dataset")
    parser.add_argument("--train_subdir", type=str, default="train/")
    parser.add_argument("--epochs", type=int, default=500)
    parser.add_argument("--batch_size", type=int, default=512)
    parser.add_argument("--lr", type=float, default=0.01)
    parser.add_argument("--hidden", type=int, default=128)
    parser.add_argument("--segments", type=int, default=10)
    parser.add_argument("--save_interval", type=int, default=100)
    parser.add_argument("--val_ratio", type=float, default=0.2)
    parser.add_argument("--patience", type=int, default=50)
    parser.add_argument("--no_cleanup", action="store_true", help="Disable cleanup of old artifacts before training")
    parser.add_argument("--remove_best", action="store_true", help="Don't keep best_model.pt when cleaning")
    args = parser.parse_args()

    train(
        data_dir=args.data_dir,
        train_subdir=args.train_subdir,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.lr,
        hidden_channels=args.hidden,
        segment_num=args.segments,
        save_interval=args.save_interval,
        val_ratio=args.val_ratio,
        early_stopping_patience=args.patience,
        cleanup_before_train=(not args.no_cleanup),
        cleanup_keep_best=(not args.remove_best),
    )
