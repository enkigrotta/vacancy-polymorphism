"""
Module A: ENCODER (Prism ⤢Δ₁⤢)

Structural role: Organ of distinction. Distinguishes features on the Map
(raw data) under pressure of forthcoming vacancy.

Double bind: Must produce detailed representations (minimize recon error)
AND quantization-robust representations (survive ∅). This tension is
constitutive — the Prism's structural condition.

Type: Neural network (trainable).
"""

import torch
import torch.nn as nn


class Encoder(nn.Module):
    """
    x ∈ ℝ^(C×H×W) → z_e ∈ ℝ^(d×h×w)

    Stack of Conv2D + BatchNorm + ReLU, downsampling ×4.
    For CIFAR-10 (3×32×32) with d=64: output is (64×8×8).
    """

    def __init__(self, in_channels: int = 3, latent_dim: int = 64,
                 hidden_dims: tuple = (128, 256)):
        super().__init__()

        layers = []
        ch_in = in_channels
        for ch_out in hidden_dims:
            layers.extend([
                nn.Conv2d(ch_in, ch_out, kernel_size=4, stride=2, padding=1),
                nn.BatchNorm2d(ch_out),
                nn.ReLU(inplace=True),
            ])
            ch_in = ch_out

        # Final projection to latent_dim (no downsampling)
        layers.extend([
            nn.Conv2d(ch_in, latent_dim, kernel_size=3, stride=1, padding=1),
            nn.BatchNorm2d(latent_dim),
            nn.ReLU(inplace=True),
        ])

        self.net = nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: (B, C, H, W) — raw data (the Map)
        Returns:
            z_e: (B, d, h, w) — continuous latent (before vacancy)
        """
        return self.net(x)
