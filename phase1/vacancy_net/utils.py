"""
Utilities for ∅-NET Phase 1.
Logging, plotting, checkpoint saving.
"""

import os
import json
import time
import torch
import numpy as np
from datetime import datetime


class TrainingLogger:
    """Structured logging of all training events."""

    def __init__(self, log_dir: str, name: str = 'training'):
        os.makedirs(log_dir, exist_ok=True)
        self.log_dir = log_dir
        self.name = name
        self.log_path = os.path.join(log_dir, f'{name}_log.jsonl')
        self.metrics_path = os.path.join(log_dir, f'{name}_metrics.json')

        self._entries = []
        self._metrics = {
            'loss_recon': [],
            'loss_commit': [],
            'loss_total': [],
            'K_eff': [],
            'utilization': [],
            'perplexity': [],
            'tension_state': [],
            'replicant_events': [],
            'delta_observations': [],
            'pca_spectra': [],
            'var_k_snapshots': [],
            'fid_scores': [],
            'epoch_times': [],
        }
        self._start_time = time.time()

    def log_batch(self, epoch: int, batch: int, losses: dict,
                  K_eff: int = None, tension: str = None, **kwargs):
        """Log one batch of training."""
        entry = {
            'time': time.time() - self._start_time,
            'epoch': epoch,
            'batch': batch,
            **losses,
        }
        if K_eff is not None:
            entry['K_eff'] = K_eff
        if tension is not None:
            entry['tension'] = tension
        entry.update(kwargs)

        self._entries.append(entry)
        self._metrics['loss_recon'].append(losses.get('L_recon', 0))
        self._metrics['loss_commit'].append(losses.get('L_commit', 0))
        self._metrics['loss_total'].append(losses.get('L_total', 0))
        if K_eff is not None:
            self._metrics['K_eff'].append(K_eff)

    def log_replicant_event(self, event: dict):
        """Log a ⟳ event."""
        self._metrics['replicant_events'].append(event)

    def log_delta_observation(self, obs: dict):
        """Log Object Δ metrics."""
        self._metrics['delta_observations'].append(obs)

    def log_epoch_metrics(self, epoch: int, metrics: dict):
        """Log end-of-epoch metrics."""
        entry = {'epoch': epoch, **metrics}
        if 'utilization' in metrics:
            self._metrics['utilization'].append(metrics['utilization'])
        if 'perplexity' in metrics:
            self._metrics['perplexity'].append(metrics['perplexity'])
        if 'fid' in metrics:
            self._metrics['fid_scores'].append(metrics['fid'])

    def log_var_snapshot(self, var_k: np.ndarray, epoch: int):
        """Log Var_k distribution snapshot."""
        self._metrics['var_k_snapshots'].append({
            'epoch': epoch,
            'var_k': var_k.tolist() if isinstance(var_k, np.ndarray)
                     else var_k.cpu().numpy().tolist(),
        })

    def log_pca_spectrum(self, eigenvalues: np.ndarray, epoch: int):
        """Log PCA spectrum."""
        self._metrics['pca_spectra'].append({
            'epoch': epoch,
            'eigenvalues': eigenvalues.tolist(),
        })

    def save(self):
        """Save all logs to disk."""
        # Save raw entries
        with open(self.log_path, 'w') as f:
            for entry in self._entries:
                f.write(json.dumps(entry, default=_json_default) + '\n')

        # Save metrics summary
        with open(self.metrics_path, 'w') as f:
            json.dump(self._metrics, f, default=_json_default, indent=2)

    def print_summary(self, epoch: int, n_batches: int):
        """Print epoch summary."""
        recent_recon = np.mean(
            self._metrics['loss_recon'][-n_batches:]) if self._metrics['loss_recon'] else 0
        recent_commit = np.mean(
            self._metrics['loss_commit'][-n_batches:]) if self._metrics['loss_commit'] else 0
        recent_total = np.mean(
            self._metrics['loss_total'][-n_batches:]) if self._metrics['loss_total'] else 0
        K = self._metrics['K_eff'][-1] if self._metrics['K_eff'] else '?'
        n_replicant = len(self._metrics['replicant_events'])

        elapsed = time.time() - self._start_time
        print(f"[Epoch {epoch:3d}] L_recon={recent_recon:.4f} "
              f"L_commit={recent_commit:.4f} L_total={recent_total:.4f} "
              f"K_eff={K} ⟳={n_replicant} t={elapsed:.0f}s")


def save_checkpoint(path: str, epoch: int, model_state: dict,
                    optimizer_state: dict = None, extra: dict = None):
    """Save training checkpoint."""
    checkpoint = {
        'epoch': epoch,
        'model_state': model_state,
        'timestamp': datetime.now().isoformat(),
    }
    if optimizer_state:
        checkpoint['optimizer_state'] = optimizer_state
    if extra:
        checkpoint['extra'] = extra
    torch.save(checkpoint, path)


def load_checkpoint(path: str, device: str = 'cpu') -> dict:
    """Load training checkpoint."""
    return torch.load(path, map_location=device)


def _json_default(obj):
    """JSON serializer for numpy/torch types."""
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, torch.Tensor):
        return obj.cpu().numpy().tolist()
    return str(obj)
