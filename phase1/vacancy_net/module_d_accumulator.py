"""
Module D: % ACCUMULATOR (Remainder)

Structural role: Organ of accumulation. Collects what falls through
distinction. Produces the signal that drives ⟳.

State (per code k, updated every batch):
  - δ̄_k: running mean of residuals (drift signal)
  - Var_k: running variance (⤢ = heterogeneity)
  - C_kk': cross-code correlation
  - usage_k: how often each code is used
  - d%/dt: rate of change of Var_k

Type: Structural (statistical tracker, no trainable parameters).
"""

import torch
import numpy as np


class RemainderAccumulator:
    """
    Accumulates %-statistics from residuals delta = z_e - e_k.

    All statistics are EMA-smoothed. Reset at ⟳ events.
    """

    def __init__(self, K_eff: int, latent_dim: int, ema_decay: float = 0.99,
                 cross_corr_interval: int = 50, device: str = 'cpu'):
        self.K_eff = K_eff
        self.latent_dim = latent_dim
        self.ema = ema_decay
        self.cross_corr_interval = cross_corr_interval
        self.device = device

        self.reset(K_eff)
        self._batch_counter = 0

    def reset(self, K_eff: int = None):
        """Reset all statistics. Called at ⟳ events."""
        if K_eff is not None:
            self.K_eff = K_eff
        K = self.K_eff
        d = self.latent_dim

        self.delta_mean = torch.zeros(K, d, device=self.device)   # δ̄_k
        self.delta_var = torch.zeros(K, device=self.device)        # Var_k (⤢)
        self.cross_corr = torch.zeros(K, K, device=self.device)    # C_kk'
        self.usage_count = torch.zeros(K, device=self.device)      # usage_k
        self.d_percent_dt = torch.zeros(K, device=self.device)     # rate of change
        self._batch_counter = 0

        # History for logging
        self.var_history = []
        self.usage_history = []

    @torch.no_grad()
    def update(self, delta: torch.Tensor, indices: torch.Tensor):
        """
        Update running statistics from one batch.

        Args:
            delta: (B, d, h, w) — residuals from Module B
            indices: (B, h, w) — code assignments from Module B
        """
        B, d, h, w = delta.shape

        # Flatten spatial dims
        delta_flat = delta.permute(0, 2, 3, 1).reshape(-1, d)  # (N, d)
        indices_flat = indices.reshape(-1)  # (N,)

        for k in range(self.K_eff):
            mask = (indices_flat == k)
            count_k = mask.sum().float()

            if count_k == 0:
                continue

            delta_k = delta_flat[mask]  # (n_k, d)

            # Running mean (drift signal)
            new_mean = delta_k.mean(dim=0)
            self.delta_mean[k] = (
                self.ema * self.delta_mean[k]
                + (1 - self.ema) * new_mean
            )

            # Running variance (⤢ = heterogeneity)
            new_var = delta_k.var()
            old_var = self.delta_var[k].clone()
            self.delta_var[k] = (
                self.ema * old_var
                + (1 - self.ema) * new_var
            )

            # Rate of change
            self.d_percent_dt[k] = new_var - old_var

            # Usage count (EMA)
            self.usage_count[k] = (
                self.ema * self.usage_count[k]
                + (1 - self.ema) * count_k
            )

        # Cross-code correlation (less frequent for efficiency)
        self._batch_counter += 1
        if self._batch_counter % self.cross_corr_interval == 0:
            self._update_cross_correlation()

        # Record history
        self.var_history.append(self.delta_var.clone().cpu())
        self.usage_history.append(self.usage_count.clone().cpu())

    def _update_cross_correlation(self):
        """
        C_kk' = correlation between mean residuals of codes.
        Measures redundancy between codes.
        """
        # Normalize mean residuals
        norms = self.delta_mean.norm(dim=1, keepdim=True).clamp(min=1e-8)
        normed = self.delta_mean / norms
        # Correlation matrix
        self.cross_corr = normed @ normed.t()

    def get_overloaded_codes(self, percentile: float = 0.90) -> torch.Tensor:
        """Codes where Var_k exceeds the percentile threshold."""
        if self.delta_var.sum() == 0:
            return torch.tensor([], dtype=torch.long, device=self.device)
        threshold = torch.quantile(self.delta_var, percentile)
        return torch.where(self.delta_var > threshold)[0]

    def get_redundant_pairs(self, c_critical: float = 0.8):
        """Pairs of codes with high cross-correlation (boundary is wrong)."""
        pairs = []
        for k1 in range(self.K_eff):
            for k2 in range(k1 + 1, self.K_eff):
                if self.cross_corr[k1, k2] > c_critical:
                    pairs.append((k1, k2))
        return pairs

    def get_dead_codes(self, usage_critical: float = None) -> torch.Tensor:
        """Codes with usage below threshold (dead codes → Π)."""
        if usage_critical is None:
            usage_critical = 1.0 / (10.0 * self.K_eff)
        total_usage = self.usage_count.sum()
        if total_usage == 0:
            return torch.tensor([], dtype=torch.long, device=self.device)
        relative_usage = self.usage_count / total_usage
        return torch.where(relative_usage < usage_critical)[0]

    def get_drifted_codes(self, factor: float = 2.0) -> torch.Tensor:
        """Codes whose mean residual norm exceeds factor × mean."""
        drift_norms = self.delta_mean.norm(dim=1)
        mean_drift = drift_norms.mean()
        if mean_drift == 0:
            return torch.tensor([], dtype=torch.long, device=self.device)
        return torch.where(drift_norms > factor * mean_drift)[0]

    def get_stats_snapshot(self) -> dict:
        """Return current %-statistics for logging."""
        return {
            'delta_mean': self.delta_mean.clone().cpu(),
            'delta_var': self.delta_var.clone().cpu(),
            'cross_corr': self.cross_corr.clone().cpu(),
            'usage_count': self.usage_count.clone().cpu(),
            'd_percent_dt': self.d_percent_dt.clone().cpu(),
        }
