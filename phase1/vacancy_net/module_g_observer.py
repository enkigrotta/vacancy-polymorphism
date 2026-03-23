"""
Module G: Δ OBSERVER (Object Δ Metrics)

Structural role: Observes the decoder's excess capacity.
Phase 1: log only. Phase 2: feeds into ⟳-protocol.

Three metrics of decoder excess:
  1. Per-code reconstruction quality (over/under-serving)
  2. Interpolation coherence (meaningful output between codes)
  3. Decoder weight utilization (fraction of capacity used)

Type: Diagnostic (no trainable parameters, periodic computation).
"""

import torch
import numpy as np


class DeltaObserver:
    """
    Observes Object Δ = decoder's generative excess.

    Phase 1: All metrics are logged, none feed back.
    """

    def __init__(self, N_observe: int = 500,
                 interpolation_samples: int = 100,
                 device: str = 'cpu'):
        self.N_observe = N_observe
        self.interpolation_samples = interpolation_samples
        self.device = device

        self.observations = []
        self._batch_counter = 0

    def step(self):
        """Called every batch."""
        self._batch_counter += 1

    def should_observe(self) -> bool:
        """Whether it's time for a Δ observation."""
        return self._batch_counter >= self.N_observe

    @torch.no_grad()
    def observe(self, encoder, decoder, vacancy, dataloader_sample) -> dict:
        """
        Compute Object Δ metrics.

        Args:
            encoder: Module A
            decoder: Module C
            vacancy: Module B
            dataloader_sample: small batch iterator (1-2 batches)

        Returns:
            metrics dict
        """
        self._batch_counter = 0
        metrics = {}

        encoder.eval()
        decoder.eval()

        # === 1. Per-code reconstruction quality ===
        L_recon_per_code = {}
        code_counts = {}

        for batch_data in dataloader_sample:
            if isinstance(batch_data, (list, tuple)):
                x = batch_data[0].to(self.device)
            else:
                x = batch_data.to(self.device)

            z_e = encoder(x)
            e_k_ste, indices, _ = vacancy(z_e)
            x_hat = decoder(e_k_ste)

            # Per-code L_recon
            indices_flat = indices.reshape(-1)
            B, C, H, W = x.shape
            _, _, h, w = indices.shape if indices.dim() == 3 else (B, 1, indices.shape[1], indices.shape[2] if indices.dim() > 2 else 1)

            recon_error = (x - x_hat).pow(2).mean(dim=1)  # (B, H, W)

            for k in range(vacancy.K_eff):
                mask_spatial = (indices == k)  # (B, h, w)
                if mask_spatial.sum() == 0:
                    continue
                # Average reconstruction error for patches assigned to code k
                # Upsample mask to match image size
                if mask_spatial.shape != recon_error.shape:
                    scale = H // mask_spatial.shape[1]
                    mask_up = mask_spatial.unsqueeze(1).float()
                    mask_up = torch.nn.functional.interpolate(
                        mask_up, size=(H, W), mode='nearest'
                    ).squeeze(1).bool()
                else:
                    mask_up = mask_spatial

                if mask_up.sum() > 0:
                    err_k = recon_error[mask_up].mean().item()
                    if k not in L_recon_per_code:
                        L_recon_per_code[k] = []
                    L_recon_per_code[k].append(err_k)

        # Average per-code errors
        metrics['L_recon_per_code'] = {
            k: np.mean(v) for k, v in L_recon_per_code.items()
        }

        # === 2. Interpolation coherence ===
        codebook = vacancy.codebook
        K_eff = vacancy.K_eff
        coherence_scores = []

        if K_eff >= 2:
            n_samples = min(self.interpolation_samples, K_eff * (K_eff - 1) // 2)
            for _ in range(n_samples):
                k1, k2 = np.random.choice(K_eff, 2, replace=False)
                interpolated = 0.5 * codebook[k1] + 0.5 * codebook[k2]
                # Reshape for decoder: (1, d, 1, 1) → broadcast to spatial
                h_dec = w_dec = int(np.sqrt(z_e.shape[2] * z_e.shape[3]))
                if h_dec == 0:
                    h_dec = w_dec = z_e.shape[2]
                interp_input = interpolated.reshape(1, -1, 1, 1).expand(
                    1, -1, z_e.shape[2], z_e.shape[3])
                output = decoder(interp_input)

                # Coherence = inverse of high-frequency energy
                # Approximate: Laplacian filter magnitude
                if output.shape[-1] > 2:
                    lap_x = output[:, :, :, 2:] - 2*output[:, :, :, 1:-1] + output[:, :, :, :-2]
                    lap_y = output[:, :, 2:, :] - 2*output[:, :, 1:-1, :] + output[:, :, :-2, :]
                    hf_energy = (lap_x.pow(2).mean() + lap_y.pow(2).mean()).item()
                    coherence = 1.0 / (hf_energy + 1e-8)
                    coherence_scores.append(coherence)

        metrics['interpolation_coherence'] = (
            np.mean(coherence_scores) if coherence_scores else 0.0
        )

        # === 3. Decoder weight utilization ===
        # SVD of first layer weights
        first_conv = None
        for module in decoder.modules():
            if isinstance(module, (torch.nn.Conv2d, torch.nn.ConvTranspose2d)):
                first_conv = module
                break

        if first_conv is not None:
            W = first_conv.weight.reshape(first_conv.weight.shape[0], -1)
            try:
                S = torch.linalg.svdvals(W)
                significant = (S > 0.01 * S[0]).sum().item()
                total = len(S)
                metrics['weight_utilization'] = significant / total
            except Exception:
                metrics['weight_utilization'] = -1.0
        else:
            metrics['weight_utilization'] = -1.0

        encoder.train()
        decoder.train()

        self.observations.append(metrics)
        return metrics
