"""
BASELINE: Standard VQ-VAE (Control)

Standard VQ-VAE with fixed K, fixed tau, no %-accumulation,
no ⟳, no valve shedding. This is what we measure against.

Architecture identical to ∅-NET's encoder/decoder for fair comparison.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F

from modules.module_a_encoder import Encoder
from modules.module_c_decoder import Decoder


class BaselineVQVAE(nn.Module):
    """
    Standard VQ-VAE. No self-governance.

    - Fixed K (never changes)
    - EMA codebook updates
    - Standard commitment loss
    - No remainder tracking
    - No ⟳ events
    """

    def __init__(self, K: int = 128, latent_dim: int = 64,
                 in_channels: int = 3, hidden_dims: tuple = (128, 256),
                 beta: float = 0.25, ema_decay: float = 0.99):
        super().__init__()

        self.K = K
        self.latent_dim = latent_dim
        self.beta = beta
        self.ema_decay = ema_decay

        # Encoder and Decoder (same architecture as ∅-NET)
        self.encoder = Encoder(in_channels, latent_dim, hidden_dims)
        self.decoder = Decoder(in_channels, latent_dim,
                               tuple(reversed(hidden_dims)))

        # Codebook (fixed size)
        self.register_buffer('codebook', torch.randn(K, latent_dim))
        self.register_buffer('ema_count', torch.zeros(K))
        self.register_buffer('ema_sum', torch.zeros(K, latent_dim))
        self._initialized = False

    def initialize_codebook(self, z_e_flat: torch.Tensor):
        """K-means initialization from encoder outputs."""
        from modules.module_h_initializer import kmeans_init
        codes = kmeans_init(z_e_flat, self.K)
        self.codebook.copy_(codes)
        self.ema_sum.copy_(codes)
        self.ema_count.fill_(1.0)
        self._initialized = True

    def quantize(self, z_e: torch.Tensor):
        """Standard VQ: nearest neighbor + STE."""
        B, d, h, w = z_e.shape
        z_flat = z_e.permute(0, 2, 3, 1).reshape(-1, d)

        # Distances
        distances = (
            z_flat.pow(2).sum(1, keepdim=True)
            - 2 * z_flat @ self.codebook.t()
            + self.codebook.pow(2).sum(1, keepdim=True).t()
        )

        indices = distances.argmin(dim=1)
        e_k = self.codebook[indices].reshape(B, h, w, d).permute(0, 3, 1, 2)

        # EMA update (training only)
        if self.training:
            with torch.no_grad():
                onehot = F.one_hot(indices, self.K).float()
                self.ema_count.mul_(self.ema_decay).add_(
                    onehot.sum(0), alpha=1 - self.ema_decay)
                self.ema_sum.mul_(self.ema_decay).add_(
                    onehot.t() @ z_flat, alpha=1 - self.ema_decay)
                n = self.ema_count.sum()
                count_s = (self.ema_count + 1e-5) / (n + self.K * 1e-5) * n
                self.codebook.copy_(self.ema_sum / count_s.unsqueeze(1))

        # STE
        e_k_ste = z_e + (e_k - z_e).detach()
        indices = indices.reshape(B, h, w)

        return e_k_ste, indices

    def forward(self, x: torch.Tensor):
        """
        Full forward: x → z_e → e_k → x̂

        Returns:
            x_hat: reconstruction
            L_recon: reconstruction loss
            L_commit: commitment loss
            L_total: L_recon + L_commit
            indices: code assignments
        """
        z_e = self.encoder(x)
        e_k, indices = self.quantize(z_e)
        x_hat = self.decoder(e_k)

        # Losses
        L_recon = F.mse_loss(x_hat, x)
        L_commit_1 = (z_e - e_k.detach()).pow(2).mean()
        L_commit_2 = (z_e.detach() - e_k).pow(2).mean()
        L_commit = L_commit_1 + self.beta * L_commit_2
        L_total = L_recon + L_commit

        return {
            'x_hat': x_hat,
            'L_recon': L_recon,
            'L_commit': L_commit,
            'L_total': L_total,
            'indices': indices,
            'z_e': z_e,
        }
