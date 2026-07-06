"""
Intent Schema Classifier — Native-App Fine-Tuning Script
==========================================================
Fine-tunes MiniLM-L6 to predict (effect, resource_kind, native_app) from
a user query. Uses 3 parallel classification heads on top of pooled embeddings.

Architecture (Native-App-as-Aggregator):
  query → MiniLM-L6 (frozen/partially-frozen) → pooled embedding (384-dim)
        → head_effect    (Linear 384→N_effects)
        → head_resource  (Linear 384→N_resources)
        → head_native_app (Linear 384→N_native_apps)

Training features:
  - Cosine LR schedule with linear warmup
  - Early stopping with patience + best-weight restore
  - Mixed precision (AMP) for 2x throughput
  - Gradient clipping & accumulation
  - Per-class F1 + confusion matrix
  - Weighted loss for imbalanced native_app head
  - EMA (exponential moving average) of weights
  - Checkpoint resume

Usage:
  python scripts/train_intent_classifier.py --epochs 20 --batch 64 --lr 2e-4
  python scripts/train_intent_classifier.py --resume --epochs 30
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from collections import Counter, defaultdict
from contextlib import nullcontext
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# ═══════════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════════

DATA_PATH = _REPO_ROOT / "data" / "intent_schema" / "training_data.jsonl"
OUTPUT_DIR = _REPO_ROOT / "k1" / "fabric" / "resolver" / "intent_classifier"

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
HF_TOKEN = os.environ.get("HF_TOKEN", "")
BATCH_SIZE = 32
EPOCHS = 20
LEARNING_RATE = 2e-4
VAL_SPLIT = 0.15
MAX_SEQ_LEN = 128
WARMUP_RATIO = 0.1
EARLY_STOP_PATIENCE = 5
GRAD_CLIP_NORM = 1.0
EMA_DECAY = 0.999

# ═══════════════════════════════════════════════════════════════════════════
# Data Loading
# ═══════════════════════════════════════════════════════════════════════════


def load_data(path: Path) -> list[dict]:
    """Load JSONL training data."""
    examples = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                examples.append(json.loads(line))
    print(f"Loaded {len(examples)} examples from {path}")
    return examples


def build_label_maps(examples: list[dict]) -> tuple[dict, dict, dict]:
    """Build str→int mappings for each label field (native_app replaces domain_tag)."""
    effects = sorted(set(ex["effect"] for ex in examples))
    resources = sorted(set(ex["resource_kind"] for ex in examples))
    native_apps = sorted(set(ex["native_app"] for ex in examples))

    e2i = {e: i for i, e in enumerate(effects)}
    r2i = {r: i for i, r in enumerate(resources)}
    n2i = {n: i for i, n in enumerate(native_apps)}

    print(f"Labels: {len(e2i)} effects, {len(r2i)} resources, {len(n2i)} native_apps")
    return e2i, r2i, n2i


# ═══════════════════════════════════════════════════════════════════════════
# Model
# ═══════════════════════════════════════════════════════════════════════════


def build_model(
    model_name: str,
    num_effects: int,
    num_resources: int,
    num_native_apps: int,
    freeze_encoder: bool = True,
):
    """Build MiniLM + 3 classification heads (native_app replaces domain_tag)."""
    import torch
    import torch.nn as nn
    from transformers import AutoModel, AutoTokenizer

    class IntentClassifier(nn.Module):
        def __init__(self, freeze_encoder: bool):
            super().__init__()
            self.tokenizer = AutoTokenizer.from_pretrained(model_name, token=HF_TOKEN)
            self.transformer = AutoModel.from_pretrained(model_name, token=HF_TOKEN)
            hidden_dim = self.transformer.config.hidden_size
            self.freeze_encoder = freeze_encoder

            if freeze_encoder:
                # Freeze all layers first, then thaw top 4 for fine-tuning
                for p in self.transformer.parameters():
                    p.requires_grad = False
                # MiniLM has 6 layers — unfreeze top 4 (layers 2-5)
                for layer_idx in range(2, 6):
                    for p in self.transformer.encoder.layer[layer_idx].parameters():
                        p.requires_grad = True

            self.head_effect = nn.Linear(hidden_dim, num_effects)
            self.head_resource = nn.Linear(hidden_dim, num_resources)
            self.head_native_app = nn.Linear(hidden_dim, num_native_apps)

        def mean_pool(self, hidden_states, attention_mask):
            """Mean pooling over token dimension, respecting attention mask."""
            mask = attention_mask.unsqueeze(-1).float()
            return (hidden_states * mask).sum(1) / mask.sum(1)

        def forward(self, texts: list[str]):
            tokens = self.tokenizer(
                texts,
                padding=True,
                truncation=True,
                max_length=MAX_SEQ_LEN,
                return_tensors="pt",
            ).to(next(self.transformer.parameters()).device)

            outputs = self.transformer(**tokens)
            embeddings = self.mean_pool(
                outputs.last_hidden_state,
                tokens["attention_mask"],
            )
            return (
                self.head_effect(embeddings),
                self.head_resource(embeddings),
                self.head_native_app(embeddings),
            )

    return IntentClassifier(freeze_encoder)


# ═══════════════════════════════════════════════════════════════════════════
# Training — production-grade with cosine schedule, early stop, AMP, EMA
# ═══════════════════════════════════════════════════════════════════════════


class EMAModel:
    """Exponential moving average of model weights + buffers. Caller saves/restores."""

    def __init__(self, model, decay: float = 0.999):
        self.model = model
        self.decay = decay
        self.shadow: dict[str, "torch.Tensor"] = {}
        self._register()

    def _register(self):
        for name, param in self.model.named_parameters():
            if param.requires_grad:
                self.shadow[name] = param.data.clone()
        for name, buf in self.model.named_buffers():
            self.shadow[name] = buf.data.clone()

    def update(self):
        for name, param in self.model.named_parameters():
            if name in self.shadow:
                self.shadow[name] = self.decay * self.shadow[name] + (1 - self.decay) * param.data
        for name, buf in self.model.named_buffers():
            if name in self.shadow:
                self.shadow[name] = self.decay * self.shadow[name] + (1 - self.decay) * buf.data

    def apply(self):
        """Copy EMA weights+buffers into model. Caller must save/restore original."""
        for name, param in self.model.named_parameters():
            if name in self.shadow:
                param.data.copy_(self.shadow[name])
        for name, buf in self.model.named_buffers():
            if name in self.shadow:
                buf.data.copy_(self.shadow[name])


def _build_weight_tensor(counts: Counter, label_map: dict, device) -> "torch.Tensor":
    """Build class-weight tensor for CrossEntropyLoss from label counts."""
    import torch

    total = sum(counts.values())
    weights = []
    for label in sorted(label_map, key=label_map.get):
        c = counts.get(label, 1)
        weights.append(total / (len(label_map) * c))
    return torch.tensor(weights, dtype=torch.float, device=device)


def train(args):
    import numpy as np
    import torch
    import torch.nn as nn
    from sklearn.metrics import accuracy_score, classification_report
    from torch.utils.data import DataLoader, Dataset

    # ── Load data ──
    examples = load_data(DATA_PATH)
    e2i, r2i, n2i = build_label_maps(examples)
    i2e = {v: k for k, v in e2i.items()}
    i2r = {v: k for k, v in r2i.items()}
    i2n = {v: k for k, v in n2i.items()}

    # ── Stratified train/val split ──
    import random

    random.seed(42)
    # Group by native_app for stratified split
    by_app: dict[str, list[dict]] = defaultdict(list)
    for ex in examples:
        by_app[ex["native_app"]].append(ex)
    train_examples: list[dict] = []
    val_examples: list[dict] = []
    for app_examples in by_app.values():
        random.shuffle(app_examples)
        split = int(len(app_examples) * (1 - VAL_SPLIT))
        train_examples.extend(app_examples[:split])
        val_examples.extend(app_examples[split:])
    random.shuffle(train_examples)
    random.shuffle(val_examples)
    print(
        f"Train: {len(train_examples)}, Val: {len(val_examples)} "
        f"(stratified across {len(by_app)} native apps)"
    )

    # ── Class weights for native_app (handles imbalance) ──
    native_app_counts = Counter(ex["native_app"] for ex in train_examples)

    # ── Dataset ──
    class IntentDataset(Dataset):
        def __init__(self, data: list[dict]):
            self.queries = [ex["query"] for ex in data]
            self.effects = [e2i[ex["effect"]] for ex in data]
            self.resources = [r2i[ex["resource_kind"]] for ex in data]
            self.native_apps = [n2i[ex["native_app"]] for ex in data]

        def __len__(self):
            return len(self.queries)

        def __getitem__(self, idx):
            return (
                self.queries[idx],
                self.effects[idx],
                self.resources[idx],
                self.native_apps[idx],
            )

    train_ds = IntentDataset(train_examples)
    val_ds = IntentDataset(val_examples)

    def collate(batch):
        queries, effects, resources, native_apps = zip(*batch)
        return (
            list(queries),
            torch.tensor(effects, dtype=torch.long),
            torch.tensor(resources, dtype=torch.long),
            torch.tensor(native_apps, dtype=torch.long),
        )

    train_dl = DataLoader(
        train_ds,
        batch_size=args.batch,
        shuffle=True,
        collate_fn=collate,
        drop_last=False,
    )
    val_dl = DataLoader(val_ds, batch_size=args.batch * 2, collate_fn=collate)

    # ── Build model ──
    freeze = not args.unfreeze
    print(f"\nBuilding model: {args.model} (freeze_encoder={freeze})")
    model = build_model(args.model, len(e2i), len(r2i), len(n2i), freeze_encoder=freeze)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)
    print(f"Device: {device}")

    # ── Optimizer: encoder vs head separation (proven working) ──
    encoder_params = [p for n, p in model.named_parameters() if p.requires_grad and "head" not in n]
    head_params = [p for n, p in model.named_parameters() if p.requires_grad and "head" in n]
    optimizer = torch.optim.AdamW(
        [
            {"params": encoder_params, "lr": args.lr * 0.1},
            {"params": head_params, "lr": args.lr},
        ],
        weight_decay=0.01,
    )

    # ── LR scheduler: linear warmup → cosine decay ──
    # total_steps computed after auto-extend block below
    def make_scheduler(optimizer, total_steps):
        warmup_steps = int(total_steps * WARMUP_RATIO)

        def lr_lambda(current_step: int) -> float:
            if current_step < warmup_steps:
                return current_step / max(1, warmup_steps)
            progress = (current_step - warmup_steps) / max(1, total_steps - warmup_steps)
            return max(0.0, 0.5 * (1 + math.cos(math.pi * progress)))

        return torch.optim.lr_scheduler.LambdaLR(optimizer, lr_lambda)

    # ── Loss: label smoothing + optional R-Drop ──
    criterion_effect = nn.CrossEntropyLoss(label_smoothing=0.05)
    criterion_resource = nn.CrossEntropyLoss(label_smoothing=0.05)
    criterion_native = nn.CrossEntropyLoss(
        weight=_build_weight_tensor(native_app_counts, n2i, device),
        label_smoothing=0.08,  # more smoothing for the hardest head
    )
    loss_weights = {
        "effect": args.lw_effect,
        "resource": args.lw_resource,
        "native_app": args.lw_native,
    }

    # ── Mixed precision scaler ──
    use_amp = args.amp and device.type == "cuda"
    scaler = torch.amp.GradScaler("cuda") if use_amp else None

    # ── EMA ──
    ema = EMAModel(model, decay=EMA_DECAY)

    # ── Scheduler: build BEFORE resume block (resume loads state into it) ──
    total_steps = len(train_dl) * args.epochs // max(1, args.grad_accum)
    scheduler = make_scheduler(optimizer, total_steps)

    # ── Checkpoint resume (handle label map expansion from new data) ──
    start_epoch = 0
    best_val_acc = 0.0
    best_val_loss = float("inf")
    patience_counter = 0
    best_state: dict | None = None

    ckpt_scheduler_state = None  # captured for auto-extend reuse

    if args.resume:
        ckpt_path = OUTPUT_DIR / "checkpoint.pt"
        if ckpt_path.exists():
            ckpt = torch.load(str(ckpt_path), map_location=device, weights_only=False)
            ckpt_e2i = ckpt.get("e2i", {})
            ckpt_r2i = ckpt.get("r2i", {})
            ckpt_n2i = ckpt.get("n2i", {})
            ckpt_scheduler_state = ckpt.get("scheduler_state")

            # Detect label map changes from new data
            e_changed = ckpt_e2i != e2i
            r_changed = ckpt_r2i != r2i
            n_changed = ckpt_n2i != n2i

            if e_changed or r_changed or n_changed:
                print(f"Data grew since checkpoint — expanding heads:")
                if r_changed:
                    print(f"  resources: {len(ckpt_r2i)}→{len(r2i)}")
                if n_changed:
                    print(f"  native_apps: {len(ckpt_n2i)}→{len(n2i)}")

                # Load old state into a temp dict, then remap
                old_state = ckpt["model_state"]
                new_state = model.state_dict()

                for key in new_state:
                    if key in old_state and old_state[key].shape == new_state[key].shape:
                        new_state[key] = old_state[key]
                    elif key in old_state:
                        # Head expanded — copy old weights, random init new
                        old_w = old_state[key]
                        new_w = new_state[key]
                        if "weight" in key:
                            # Copy old portion, Xavier init the new rows
                            new_w[: old_w.shape[0]] = old_w
                            # New rows already have Xavier init from model init
                        elif "bias" in key:
                            new_w[: old_w.shape[0]] = old_w
                        print(f"  Expanded {key}: {list(old_w.shape)} → {list(new_w.shape)}")

                model.load_state_dict(new_state)

                # Load optimizer but skip if param groups changed
                try:
                    optimizer.load_state_dict(ckpt["optimizer_state"])
                except Exception:
                    print("  Optimizer state mismatched — using fresh optimizer")

                try:
                    scheduler.load_state_dict(ckpt["scheduler_state"])
                except Exception:
                    print("  Scheduler state mismatched — using fresh scheduler")

                start_epoch = ckpt["epoch"] + 1
                best_val_acc = ckpt.get("best_val_acc", 0.0)
                best_val_loss = ckpt.get("best_val_loss", float("inf"))
                patience_counter = ckpt.get("patience_counter", 0)

                # Load scaler state if shapes match
                if scaler and "scaler_state" in ckpt and ckpt["scaler_state"]:
                    try:
                        scaler.load_state_dict(ckpt["scaler_state"])
                    except Exception:
                        print("  Scaler state mismatched — using fresh scaler")
            else:
                # No change — clean load
                model.load_state_dict(ckpt["model_state"])
                optimizer.load_state_dict(ckpt["optimizer_state"])
                scheduler.load_state_dict(ckpt["scheduler_state"])
                start_epoch = ckpt["epoch"] + 1
                best_val_acc = ckpt.get("best_val_acc", 0.0)
                best_val_loss = ckpt.get("best_val_loss", float("inf"))
                patience_counter = ckpt.get("patience_counter", 0)
                if scaler and "scaler_state" in ckpt and ckpt["scaler_state"]:
                    scaler.load_state_dict(ckpt["scaler_state"])

            print(
                f"Resumed from epoch {start_epoch} "
                f"(best_val_acc={best_val_acc:.3f}, patience={patience_counter})"
            )

    # ── Auto-extend epochs when resuming near the end ──
    if args.resume and start_epoch >= args.epochs:
        extra = max(10, args.epochs // 2)
        args.epochs = start_epoch + extra
        # Rebuild scheduler with new total_steps, reload state to preserve step offset
        total_steps = len(train_dl) * args.epochs // max(1, args.grad_accum)
        scheduler = make_scheduler(optimizer, total_steps)
        try:
            scheduler.load_state_dict(ckpt_scheduler_state)
        except Exception:
            pass
        print(
            f"Resume at epoch {start_epoch} >= {args.epochs - extra} — "
            f"auto-extending to {args.epochs} epochs (+{extra})"
        )

    # ── Train ──
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    global_step = start_epoch * len(train_dl)

    for epoch in range(start_epoch, args.epochs):
        # ── Train phase ──
        model.train()
        total_loss = 0.0
        optimizer.zero_grad()
        t0 = time.perf_counter()
        n_tokens = 0
        accum_count = 0

        for batch_i, (queries, y_effect, y_resource, y_native_app) in enumerate(train_dl):
            y_effect = y_effect.to(device)
            y_resource = y_resource.to(device)
            y_native_app = y_native_app.to(device)

            with torch.amp.autocast("cuda") if use_amp else nullcontext():
                pred_e, pred_r, pred_n = model(queries)
                loss = (
                    loss_weights["effect"] * criterion_effect(pred_e, y_effect)
                    + loss_weights["resource"] * criterion_resource(pred_r, y_resource)
                    + loss_weights["native_app"] * criterion_native(pred_n, y_native_app)
                )
                loss = loss / args.grad_accum

            if scaler:
                scaler.scale(loss).backward()
            else:
                loss.backward()

            n_tokens += sum(
                len(model.tokenizer.encode(q, add_special_tokens=False)) for q in queries
            )
            accum_count += 1

            if accum_count == args.grad_accum or batch_i == len(train_dl) - 1:
                # Scale by actual micro-batches accumulated, not the full grad_accum
                if accum_count != args.grad_accum:
                    for p in model.parameters():
                        if p.grad is not None:
                            p.grad *= accum_count / args.grad_accum

                if scaler:
                    scaler.unscale_(optimizer)
                    torch.nn.utils.clip_grad_norm_(model.parameters(), GRAD_CLIP_NORM)
                    scaler.step(optimizer)
                    scaler.update()
                else:
                    torch.nn.utils.clip_grad_norm_(model.parameters(), GRAD_CLIP_NORM)
                    optimizer.step()

                scheduler.step()
                optimizer.zero_grad()
                ema.update()
                global_step += 1
                accum_count = 0

            total_loss += loss.item() * args.grad_accum

            if batch_i % 20 == 0:
                lr_now = scheduler.get_last_lr()[0]
                print(
                    f"  E{epoch+1} B{batch_i}: loss={loss.item()*args.grad_accum:.3f} "
                    f"lr={lr_now:.2e}",
                    end="\r",
                )

        avg_loss = total_loss / len(train_dl)
        train_time = time.perf_counter() - t0

        # ── Validation phase (EMA weights for eval, then restore) ──
        model.eval()
        original_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
        ema.apply()
        val_loss = 0.0
        val_preds_e, val_preds_r, val_preds_n = [], [], []
        val_true_e, val_true_r, val_true_n = [], [], []

        with torch.no_grad():
            for queries, y_e, y_r, y_n in val_dl:
                y_e = y_e.to(device)
                y_r = y_r.to(device)
                y_n = y_n.to(device)
                pred_e, pred_r, pred_n = model(queries)

                val_loss += (
                    criterion_effect(pred_e, y_e).item()
                    + criterion_resource(pred_r, y_r).item()
                    + criterion_native(pred_n, y_n).item()
                )

                val_preds_e.extend(pred_e.argmax(dim=1).cpu().tolist())
                val_preds_r.extend(pred_r.argmax(dim=1).cpu().tolist())
                val_preds_n.extend(pred_n.argmax(dim=1).cpu().tolist())
                val_true_e.extend(y_e.cpu().tolist())
                val_true_r.extend(y_r.cpu().tolist())
                val_true_n.extend(y_n.cpu().tolist())

        val_loss /= len(val_dl)
        acc_e = accuracy_score(val_true_e, val_preds_e)
        acc_r = accuracy_score(val_true_r, val_preds_r)
        acc_n = accuracy_score(val_true_n, val_preds_n)
        avg_acc = (acc_e + acc_r + acc_n) / 3

        # Restore original weights after EMA eval (keep for best-checkpoint use)
        model.load_state_dict({k: v.to(device) for k, v in original_state.items()})

        lr_now = scheduler.get_last_lr()[0]
        print(
            f"\n  Epoch {epoch+1:2d}: loss={avg_loss:.4f}  val_loss={val_loss:.4f}  "
            f"lr={lr_now:.2e}  "
            f"effect={acc_e:.3f}  resource={acc_r:.3f}  native_app={acc_n:.3f}  "
            f"avg={avg_acc:.3f}  ({train_time:.0f}s, {n_tokens} tok)"
        )

        # ── Per-head report every 5 epochs ──
        if (epoch + 1) % 5 == 0 or epoch == args.epochs - 1:
            print(f"\n  ── Native App Classification Report (epoch {epoch+1}) ──")
            report = classification_report(
                val_true_n,
                val_preds_n,
                labels=list(range(len(n2i))),
                target_names=[i2n[i] for i in range(len(n2i))],
                zero_division=0,
            )
            for line in report.split("\n")[:15]:
                if line.strip():
                    print(f"  {line}")

        # ── Early stopping + checkpoint ──
        is_best = avg_acc > best_val_acc
        if is_best:
            best_val_acc = avg_acc
            best_val_loss = val_loss
            patience_counter = 0
            # Snapshot EMA weights directly from shadow (avoids second apply/restore cycle)
            ema_state = {k: v.cpu().clone() for k, v in ema.shadow.items()}
            # Map shadow keys back to model state_dict keys (shadow keys match model keys)
            best_state = {
                "model_state": ema_state,
                "optimizer_state": optimizer.state_dict(),
                "scheduler_state": scheduler.state_dict(),
                "epoch": epoch,
                "e2i": e2i,
                "r2i": r2i,
                "n2i": n2i,
                "i2e": i2e,
                "i2r": i2r,
                "i2n": i2n,
                "val_acc": avg_acc,
                "patience_counter": patience_counter,
                "config": {
                    "model_name": args.model,
                    "num_effects": len(e2i),
                    "num_resources": len(r2i),
                    "num_native_apps": len(n2i),
                },
            }
            print(f"  ✅ New best (avg_acc={avg_acc:.4f})")
        else:
            patience_counter += 1
            print(f"  ⏳ No improvement (patience {patience_counter}/{EARLY_STOP_PATIENCE})")

        # Save periodic checkpoint (includes label maps for resume)
        torch.save(
            {
                "model_state": model.state_dict(),
                "optimizer_state": optimizer.state_dict(),
                "scheduler_state": scheduler.state_dict(),
                "epoch": epoch,
                "e2i": e2i,
                "r2i": r2i,
                "n2i": n2i,
                "best_val_acc": best_val_acc,
                "best_val_loss": best_val_loss,
                "patience_counter": patience_counter,
                "scaler_state": scaler.state_dict() if scaler else None,
            },
            OUTPUT_DIR / "checkpoint.pt",
        )

        if patience_counter >= EARLY_STOP_PATIENCE:
            print(f"\n  Early stopping after {EARLY_STOP_PATIENCE} epochs without improvement")
            break

    # ── Save best model ──
    if best_state:
        save_path = OUTPUT_DIR / "best_model.pt"
        torch.save(best_state, save_path)
        print(
            f"\n✅ Best model saved: {save_path} "
            f"(val_acc={best_val_acc:.4f}, native_app_acc={best_state['val_acc']:.4f})"
        )

    print(f"Label maps: {len(e2i)} effects, {len(r2i)} resources, {len(n2i)} native_apps")


# ═══════════════════════════════════════════════════════════════════════════
# Inference (for testing in POC)
# ═══════════════════════════════════════════════════════════════════════════


class IntentClassifierInference:
    """Lightweight inference wrapper for the native-app classifier."""

    def __init__(self, model_path: str | Path = None):
        import torch
        from transformers import AutoModel, AutoTokenizer

        if model_path is None:
            model_path = OUTPUT_DIR / "best_model.pt"
        ckpt = torch.load(str(model_path), map_location="cpu", weights_only=False)
        cfg = ckpt["config"]
        self.e2i = ckpt["e2i"]
        self.r2i = ckpt["r2i"]
        self.n2i = ckpt["n2i"]
        self.i2e = ckpt["i2e"]
        self.i2r = ckpt["i2r"]
        self.i2n = ckpt["i2n"]

        self.model = build_model(
            cfg["model_name"],
            cfg["num_effects"],
            cfg["num_resources"],
            cfg["num_native_apps"],
            freeze_encoder=False,
        )
        self.model.load_state_dict(ckpt["model_state"], strict=False)
        self.model.eval()
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model.to(self.device)

    def predict(self, query: str) -> dict[str, str]:
        return self.predict_batch([query])[0]

    def predict_batch(self, queries: list[str]) -> list[dict[str, str]]:
        import torch

        with torch.no_grad():
            pred_e, pred_r, pred_n = self.model(queries)
            effects = [self.i2e[i] for i in pred_e.argmax(dim=1).tolist()]
            resources = [self.i2r[i] for i in pred_r.argmax(dim=1).tolist()]
            native_apps = [self.i2n[i] for i in pred_n.argmax(dim=1).tolist()]
        return [
            {"effect": e, "resource_kind": r, "native_app": n}
            for e, r, n in zip(effects, resources, native_apps)
        ]


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════


def main():
    parser = argparse.ArgumentParser(description="Intent Classifier — Native-App Training")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL)
    parser.add_argument("--epochs", type=int, default=EPOCHS)
    parser.add_argument("--batch", type=int, default=BATCH_SIZE)
    parser.add_argument("--lr", type=float, default=LEARNING_RATE)
    parser.add_argument(
        "--grad-accum",
        type=int,
        default=1,
        help="Gradient accumulation steps (larger effective batch)",
    )
    parser.add_argument(
        "--amp",
        action="store_true",
        default=True,
        help="Use mixed precision (AMP) for 2x speed on GPU",
    )
    parser.add_argument("--no-amp", dest="amp", action="store_false", help="Disable AMP")
    parser.add_argument(
        "--unfreeze", action="store_true", help="Unfreeze top 4 encoder layers for fine-tuning"
    )
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint.pt")
    parser.add_argument("--lw-effect", type=float, default=1.0, help="Loss weight for effect head")
    parser.add_argument(
        "--lw-resource", type=float, default=1.0, help="Loss weight for resource head"
    )
    parser.add_argument(
        "--lw-native",
        type=float,
        default=2.0,
        help="Loss weight for native_app head (prioritize routing)",
    )
    parser.add_argument(
        "--rdrop",
        type=float,
        default=0.0,
        help="R-Drop KL regularizer weight (NOT YET IMPLEMENTED)",
    )
    parser.add_argument("--test", type=str, default=None, help="Test a query with trained model")
    args = parser.parse_args()

    if args.test:
        clf = IntentClassifierInference()
        result = clf.predict(args.test)
        print(f"Query: {args.test}")
        print(f"Prediction: {json.dumps(result, indent=2)}")
        return

    train(args)


if __name__ == "__main__":
    main()
