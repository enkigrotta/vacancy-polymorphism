"""
Train Baseline VQ-VAE (Control)

Standard VQ-VAE on CIFAR-10. No self-governance.
This is Step 1 of the experimental protocol.
"""

import torch
import numpy as np
import os
import sys

from config import Config
from model_baseline import BaselineVQVAE
from data import get_cifar10_loaders
from metrics import codebook_utilization, compute_reconstruction_fid, pca_spectrum
from utils import TrainingLogger, save_checkpoint


def train_baseline(cfg: Config = None):
    if cfg is None:
        cfg = Config()

    device = cfg.resolve_device()
    print(f"Training Baseline VQ-VAE on {device}")
    print(f"K={cfg.K_initial}, d={cfg.latent_dim}, β={cfg.beta}, "
          f"epochs={cfg.num_epochs}")

    # Data
    train_loader, test_loader = get_cifar10_loaders(
        cfg.data_dir, cfg.batch_size, cfg.num_workers)

    # Model
    model = BaselineVQVAE(
        K=cfg.K_initial, latent_dim=cfg.latent_dim,
        in_channels=cfg.image_channels, hidden_dims=cfg.hidden_dims,
        beta=cfg.beta, ema_decay=cfg.ema_decay_codebook,
    ).to(device)

    # Optimizer
    optimizer = torch.optim.Adam(
        list(model.encoder.parameters()) + list(model.decoder.parameters()),
        lr=cfg.learning_rate,
    )

    # Logger
    logger = TrainingLogger(cfg.baseline_log_dir, 'baseline')

    # === Codebook initialization (Δ₀_initial) ===
    print("Initializing codebook via k-means...")
    init_z = []
    model.eval()
    with torch.no_grad():
        for i, (x, _) in enumerate(train_loader):
            if i >= cfg.kmeans_batches:
                break
            z_e = model.encoder(x.to(device))
            z_flat = z_e.permute(0, 2, 3, 1).reshape(-1, cfg.latent_dim)
            init_z.append(z_flat)
    init_z = torch.cat(init_z, dim=0)
    model.initialize_codebook(init_z)
    model.train()
    print(f"Codebook initialized from {init_z.shape[0]} vectors.")

    # === Training loop ===
    for epoch in range(cfg.num_epochs):
        epoch_indices = []

        for batch_idx, (x, _) in enumerate(train_loader):
            x = x.to(device)

            result = model(x)
            L_total = result['L_total']

            optimizer.zero_grad()
            L_total.backward()
            optimizer.step()

            epoch_indices.append(result['indices'].detach().cpu())

            # Log
            if batch_idx % cfg.log_interval == 0:
                logger.log_batch(
                    epoch, batch_idx,
                    {
                        'L_recon': result['L_recon'].item(),
                        'L_commit': result['L_commit'].item(),
                        'L_total': result['L_total'].item(),
                    },
                    K_eff=cfg.K_initial,
                )

        # End-of-epoch metrics
        all_indices = torch.cat([idx.reshape(-1) for idx in epoch_indices])
        util_metrics = codebook_utilization(all_indices, cfg.K_initial)

        # PCA spectrum (every 10 epochs)
        if epoch % 10 == 0:
            model.eval()
            z_all = []
            with torch.no_grad():
                for i, (x, _) in enumerate(test_loader):
                    if i >= 10:
                        break
                    z_e = model.encoder(x.to(device))
                    z_all.append(z_e.permute(0, 2, 3, 1).reshape(
                        -1, cfg.latent_dim).cpu().numpy())
            z_all = np.concatenate(z_all, axis=0)
            pca_eigs = pca_spectrum(z_all, n_components=10)
            logger.log_pca_spectrum(pca_eigs, epoch)
            model.train()

        # FID (every 20 epochs)
        fid = -1.0
        if epoch % 20 == 0 and epoch > 0:
            try:
                fid = compute_reconstruction_fid(
                    model.encoder, model.decoder,
                    # Wrap model to expose vacancy-like interface
                    _BaselineVacancyWrapper(model),
                    test_loader, device, max_batches=20,
                )
            except Exception as e:
                print(f"FID computation failed: {e}")

        logger.log_epoch_metrics(epoch, {
            'utilization': util_metrics['utilization'],
            'perplexity': util_metrics['perplexity'],
            'active_codes': util_metrics['active_codes'],
            'fid': fid,
        })
        logger.print_summary(epoch, len(train_loader))

        # Checkpoint
        if epoch % cfg.save_interval == 0:
            save_checkpoint(
                os.path.join(cfg.baseline_log_dir, f'checkpoint_e{epoch}.pt'),
                epoch, model.state_dict(),
                optimizer.state_dict(),
            )

    # Final save
    logger.save()
    save_checkpoint(
        os.path.join(cfg.baseline_log_dir, 'checkpoint_final.pt'),
        cfg.num_epochs, model.state_dict(),
    )
    print(f"\nBaseline training complete. Logs in {cfg.baseline_log_dir}")
    return model, logger


class _BaselineVacancyWrapper:
    """Wrapper to give baseline model a vacancy-like interface for FID computation."""
    def __init__(self, model):
        self.model = model
        self.K_eff = model.K
        self.codebook = model.codebook

    def __call__(self, z_e):
        e_k, indices = self.model.quantize(z_e)
        delta = z_e - e_k.detach()
        return e_k, indices, delta


if __name__ == '__main__':
    cfg = Config()
    # Allow quick test with fewer epochs
    if '--quick' in sys.argv:
        cfg.num_epochs = 5
        cfg.log_interval = 10
    train_baseline(cfg)
