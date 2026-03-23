"""
Module B: ∅_sg (Self-Governing Vacancy)

Structural role: The vacancy. Irreversible quantization that destroys
within-cell information. Self-governed: its parameters are set by
⟳-protocol, not by the engineer (after initialization).

State:
  - codebook: (K_eff, d) — code vectors
  - K_eff: int — current effective cardinality (↕)
  - tau_k: (K_eff,) — per-code temperature (↔)

Invariants:
  - ∅ is always present: K_eff ≥ 2
  - tau_k > 0 always
  - Quantization is irreversible in forward pass

Type: Structural (parameterized operation, not a neural network).
"""

import torch
import torch.nn as nn
import torch.nn.functional as F


class SelfGoverningVacancy(nn.Module):
    """
    ∅_sg: z_e → e_k (hard), delta = z_e - e_k (remainder → Module D)

    Soft assignment for gradient flow (STE), hard assignment for forward pass.
    Per-code temperature τ_k modulates boundary softness.
    """

    def __init__(self, K: int, latent_dim: int, tau_init: float = 1.0,
                 ema_decay: float = 0.99):
        super().__init__()

        self.K_eff = K
        self.latent_dim = latent_dim
        self.ema_decay = ema_decay

        # Codebook vectors — registered as buffer (not parameter: updated via EMA)
        self.register_buffer('codebook', torch.randn(K, latent_dim))
        # Per-code temperature
        self.register_buffer('tau_k', torch.full((K,), tau_init))
        # EMA cluster size (for codebook EMA update)
        self.register_buffer('ema_count', torch.zeros(K))
        # EMA sum (for codebook EMA update)
        self.register_buffer('ema_sum', torch.zeros(K, latent_dim))
        # Whether codebook has been initialized via k-means
        self._initialized = False

    def initialize_from_data(self, z_e_flat: torch.Tensor):
        """
        Δ₀_initial: Initialize codebook via k-means on first batch(es).

        Args:
            z_e_flat: (N, d) — flattened encoder outputs from initial batches
        """
        from .module_h_initializer import kmeans_init
        codes = kmeans_init(z_e_flat, self.K_eff)
        self.codebook.copy_(codes)
        self.ema_sum.copy_(codes * 1.0)  # initialize EMA sum
        self.ema_count.fill_(1.0)
        self._initialized = True

    def forward(self, z_e: torch.Tensor):
        """
        Quantization: z_e → e_k + delta

        Args:
            z_e: (B, d, h, w) — encoder output

        Returns:
            e_k_ste: (B, d, h, w) — quantized (STE for backward)
            indices: (B, h, w) — which code selected
            delta: (B, d, h, w) — residual z_e - e_k (→ Module D)
        """
        B, d, h, w = z_e.shape

        # Reshape for distance computation: (B*h*w, d)
        z_flat = z_e.permute(0, 2, 3, 1).reshape(-1, d)

        # Compute squared distances to all codes: (B*h*w, K_eff)
        distances = (
            z_flat.pow(2).sum(dim=1, keepdim=True)
            - 2 * z_flat @ self.codebook.t()
            + self.codebook.pow(2).sum(dim=1, keepdim=True).t()
        )

        # Hard assignment (forward pass)
        indices_flat = distances.argmin(dim=1)  # (B*h*w,)

        # Quantized vectors
        e_k_flat = self.codebook[indices_flat]  # (B*h*w, d)

        # EMA codebook update (training only)
        if self.training:
            self._ema_update(z_flat, indices_flat)

        # Reshape back
        e_k = e_k_flat.reshape(B, h, w, d).permute(0, 3, 1, 2)
        indices = indices_flat.reshape(B, h, w)

        # STE: forward uses hard e_k, backward uses gradient through z_e
        e_k_ste = z_e + (e_k - z_e).detach()

        # Residual (falls into %) — NOT detached, this is the structural trace
        delta = z_e - e_k.detach()

        return e_k_ste, indices, delta

    def _ema_update(self, z_flat: torch.Tensor, indices: torch.Tensor):
        """EMA update for codebook vectors (not gradient-based)."""
        with torch.no_grad():
            # One-hot encode assignments
            onehot = F.one_hot(indices, self.K_eff).float()  # (N, K)

            # Update counts
            new_count = onehot.sum(dim=0)  # (K,)
            self.ema_count.mul_(self.ema_decay).add_(
                new_count, alpha=1 - self.ema_decay)

            # Update sums
            new_sum = onehot.t() @ z_flat  # (K, d)
            self.ema_sum.mul_(self.ema_decay).add_(
                new_sum, alpha=1 - self.ema_decay)

            # Laplace smoothing to avoid division by zero
            n = self.ema_count.sum()
            count_smoothed = (
                (self.ema_count + 1e-5) /
                (n + self.K_eff * 1e-5) * n
            )

            # Update codebook
            self.codebook.copy_(self.ema_sum / count_smoothed.unsqueeze(1))

    def replace_codebook(self, new_codebook: torch.Tensor,
                         new_tau: torch.Tensor):
        """
        Called by Module H at ⟳ events. Replaces codebook entirely.

        Args:
            new_codebook: (K_new, d)
            new_tau: (K_new,)
        """
        K_new = new_codebook.shape[0]
        assert K_new >= 2, "∅ requires K_eff ≥ 2 (single code = no vacancy)"

        self.K_eff = K_new
        # Resize buffers
        self.codebook = new_codebook.clone()
        self.tau_k = new_tau.clone()
        self.ema_count = torch.zeros(K_new, device=new_codebook.device)
        self.ema_sum = new_codebook.clone()

    def get_usage(self, indices: torch.Tensor) -> torch.Tensor:
        """Compute per-code usage from a batch of indices."""
        usage = torch.zeros(self.K_eff, device=indices.device)
        for k in range(self.K_eff):
            usage[k] = (indices == k).sum().float()
        total = indices.numel()
        return usage / max(total, 1)
