"""
Module C: DECODER (Δ₂)

Structural role: Second constrained system. Reconstructs through ∅.
Constitutes Object Δ (generative excess) as a side effect.

What the decoder does NOT know: It does not know about %-statistics,
codebook restructuring, or its own excess. It reconstructs.
Everything else is observed externally.

Type: Neural network (trainable).
"""

import torch
import torch.nn as nn


class Decoder(nn.Module):
    """
    e_k ∈ ℝ^(d×h×w) → x̂ ∈ ℝ^(C×H×W)

    Stack of ConvTranspose2D + BatchNorm + ReLU, upsampling ×4.
    For CIFAR-10 with d=64: input (64×8×8) → output (3×32×32).
    """

    def __init__(self, out_channels: int = 3, latent_dim: int = 64,
                 hidden_dims: tuple = (256, 128)):
        super().__init__()

        layers = []
        ch_in = latent_dim

        # Initial projection (no upsampling)
        layers.extend([
            nn.Conv2d(ch_in, hidden_dims[0], kernel_size=3, stride=1, padding=1),
            nn.BatchNorm2d(hidden_dims[0]),
            nn.ReLU(inplace=True),
        ])
        ch_in = hidden_dims[0]

        # Upsampling layers
        for ch_out in hidden_dims[1:]:
            layers.extend([
                nn.ConvTranspose2d(ch_in, ch_out, kernel_size=4, stride=2,
                                   padding=1),
                nn.BatchNorm2d(ch_out),
                nn.ReLU(inplace=True),
            ])
            ch_in = ch_out

        # Final layer → image channels (with Tanh for [-1, 1] range)
        layers.extend([
            nn.ConvTranspose2d(ch_in, out_channels, kernel_size=4, stride=2,
                               padding=1),
            nn.Tanh(),
        ])

        self.net = nn.Sequential(*layers)

    def forward(self, e_k: torch.Tensor) -> torch.Tensor:
        """
        Args:
            e_k: (B, d, h, w) — quantized codes from Module B
        Returns:
            x_hat: (B, C, H, W) — reconstruction
        """
        return self.net(e_k)
