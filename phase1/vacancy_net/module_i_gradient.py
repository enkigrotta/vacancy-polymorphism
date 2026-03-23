"""
Module I: GRADIENT ENGINE (Standard)

Structural role: Standard backpropagation. Nothing novel.

Loss:
  L_total = L_recon + L_commit

Updates:
  - Encoder weights (Module A): via gradient of L_total through STE
  - Decoder weights (Module C): via gradient of L_recon
  - Codebook vectors (Module B): via EMA (NOT gradient)

Type: Standard (PyTorch optimizer).
"""

import torch
import torch.optim as optim


class GradientEngine:
    """
    Standard optimization. The only standard module.
    """

    def __init__(self, encoder_params, decoder_params,
                 lr: float = 3e-4, weight_decay: float = 0.0):
        # Combine encoder and decoder parameters
        self.optimizer = optim.Adam(
            [
                {'params': encoder_params, 'lr': lr},
                {'params': decoder_params, 'lr': lr},
            ],
            weight_decay=weight_decay,
        )

    def step(self, L_total: torch.Tensor):
        """
        Standard backward + step.

        Args:
            L_total: L_recon + L_commit (scalar)
        """
        self.optimizer.zero_grad()
        L_total.backward()
        self.optimizer.step()

    def reduce_lr(self, factor: float = 0.5):
        """Emergency: reduce learning rate (called at COLLAPSE)."""
        for param_group in self.optimizer.param_groups:
            param_group['lr'] *= factor
