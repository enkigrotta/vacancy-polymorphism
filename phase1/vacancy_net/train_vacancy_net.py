"""
Train ∅-NET Phase 1: Self-Governing Vacancy Network

VQ-VAE with all nine modules active:
  A (Encoder), B (∅_sg), C (Decoder), D (% Accumulator),
  E (⫿ Syntone), F (⟳ Protocol), G (Δ Observer),
  H (Δ₀ Initializer), I (Gradient Engine)

This is Step 2 of the experimental protocol.
"""

import torch
import numpy as np
import os
import sys

from config import Config
from model_vacancy_net import VacancyNet
from data import get_cifar10_loaders
from metrics import (codebook_utilization, compute_reconstruction_fid,
                     pca_spectrum, estimate_voronoi_volumes)
from utils import TrainingLogger, save_checkpoint


def train_vacancy_net(cfg: Config = None):
    if cfg is None:
        cfg = Config()

    device = cfg.resolve_device()
    print(f"Training ∅-NET Phase 1 on {device}")
    print(f"K₀={cfg.K_initial}, d={cfg.latent_dim}, β={cfg.beta}, "
          f"T_cool={cfg.T_cool}, epochs={cfg.num_epochs}")

    # Seed
    torch.manual_seed(cfg.seed)
    np.random.seed(cfg.seed)

    # Data
    train_loader, test_loader = get_cifar10_loaders(
        cfg.data_dir, cfg.batch_size, cfg.num_workers)

    # Model
    model = VacancyNet(cfg).to(device)
    model.setup_gradient_engine()

    # Logger
    logger = TrainingLogger(cfg.vacancy_net_log_dir, 'vacancy_net')

    # === Codebook initialization (Δ₀_initial via k-means) ===
    print("Initializing codebook via k-means (Δ₀_initial)...")
    init_z = model.collect_init_data(train_loader, cfg.kmeans_batches, device)
    model.vacancy.initialize_from_data(init_z)
    print(f"Codebook initialized: K={model.vacancy.K_eff}, "
          f"d={cfg.latent_dim}, from {init_z.shape[0]} vectors.")

    # === Training loop ===
    for epoch in range(cfg.num_epochs):
        epoch_indices = []
        epoch_replicant_events = []

        for batch_idx, (x, _) in enumerate(train_loader):
            x = x.to(device)

            # Complete training step (all 9 modules)
            step_result = model.train_step(x, epoch, batch_idx)

            # Collect indices for utilization
            # (need to re-run forward briefly for indices, or cache from train_step)
            with torch.no_grad():
                z_e = model.encoder(x)
                _, indices, _ = model.vacancy(z_e)
                epoch_indices.append(indices.cpu())

            # Log replicant events
            if step_result['replicant_event'] is not None:
                event = step_result['replicant_event']
                logger.log_replicant_event(event)
                epoch_replicant_events.append(event)
                print(f"  ⟳ EVENT at epoch {epoch} batch {batch_idx}: "
                      f"K {event['K_old']}→{event['K_new']} "
                      f"(splits={event['n_splits']}, merges={event['n_merges']}, "
                      f"shifts={event['n_shifts']}, res={event['n_resurrections']})")

            # Log batch
            if batch_idx % cfg.log_interval == 0:
                logger.log_batch(
                    epoch, batch_idx,
                    {
                        'L_recon': step_result['L_recon'],
                        'L_commit': step_result['L_commit'],
                        'L_total': step_result['L_total'],
                    },
                    K_eff=step_result['K_eff'],
                    tension=step_result['tension'],
                    valve_shed=step_result['valve_shed'],
                )

            # Δ Observer (periodic)
            if model.observer.should_observe():
                # Get a small sample for observation
                sample_batches = []
                for i, (sx, _) in enumerate(test_loader):
                    if i >= 2:
                        break
                    sample_batches.append((sx.to(device),))

                obs = model.observer.observe(
                    model.encoder, model.decoder, model.vacancy,
                    sample_batches,
                )
                logger.log_delta_observation(obs)

        # === End-of-epoch metrics ===
        K_eff = model.vacancy.K_eff
        all_indices = torch.cat([idx.reshape(-1) for idx in epoch_indices])
        util_metrics = codebook_utilization(all_indices, K_eff)

        # Var_k snapshot (for N.13)
        logger.log_var_snapshot(
            model.accumulator.delta_var.cpu().numpy(), epoch)

        # PCA spectrum (every 10 epochs, for N.6)
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

        # Voronoi volumes (every 20 epochs, for N.13: Var_k ≠ V_cell)
        if epoch % 20 == 0 and epoch > 0:
            model.eval()
            z_samples = []
            with torch.no_grad():
                for i, (x, _) in enumerate(test_loader):
                    if i >= 10:
                        break
                    z_e = model.encoder(x.to(device))
                    z_samples.append(z_e.permute(0, 2, 3, 1).reshape(
                        -1, cfg.latent_dim))
            z_samples = torch.cat(z_samples, dim=0)
            v_cell = estimate_voronoi_volumes(
                model.vacancy.codebook, z_samples)
            var_k = model.accumulator.delta_var.cpu().numpy()

            # Log for N.13 scatter plot
            logger._metrics.setdefault('voronoi_vs_var', []).append({
                'epoch': epoch,
                'V_cell': v_cell.tolist(),
                'Var_k': var_k[:len(v_cell)].tolist(),
            })
            model.train()

        # FID (every 20 epochs)
        fid = -1.0
        if epoch % 20 == 0 and epoch > 0:
            try:
                fid = compute_reconstruction_fid(
                    model.encoder, model.decoder, model.vacancy,
                    test_loader, device, max_batches=20,
                )
            except Exception as e:
                print(f"FID computation failed: {e}")

        logger.log_epoch_metrics(epoch, {
            'utilization': util_metrics['utilization'],
            'perplexity': util_metrics['perplexity'],
            'active_codes': util_metrics['active_codes'],
            'K_eff': K_eff,
            'n_replicant_events_total': model._replicant_count,
            'fid': fid,
            'tension': model.syntone.current_state.value,
        })
        logger.print_summary(epoch, len(train_loader))

        # Checkpoint
        if epoch % cfg.save_interval == 0:
            save_checkpoint(
                os.path.join(cfg.vacancy_net_log_dir,
                             f'checkpoint_e{epoch}.pt'),
                epoch,
                {
                    'encoder': model.encoder.state_dict(),
                    'decoder': model.decoder.state_dict(),
                    'codebook': model.vacancy.codebook,
                    'tau_k': model.vacancy.tau_k,
                    'K_eff': model.vacancy.K_eff,
                },
                extra={
                    'replicant_events': model.replicant.replicant_events,
                    'syntone_history': model.syntone.tension_history,
                },
            )

    # === Final save ===
    logger.save()
    save_checkpoint(
        os.path.join(cfg.vacancy_net_log_dir, 'checkpoint_final.pt'),
        cfg.num_epochs,
        {
            'encoder': model.encoder.state_dict(),
            'decoder': model.decoder.state_dict(),
            'codebook': model.vacancy.codebook,
            'tau_k': model.vacancy.tau_k,
            'K_eff': model.vacancy.K_eff,
        },
        extra={
            'replicant_events': model.replicant.replicant_events,
            'delta_observations': model.observer.observations,
            'syntone_history': model.syntone.tension_history,
        },
    )

    print(f"\n∅-NET training complete.")
    print(f"  Total ⟳ events: {model._replicant_count}")
    print(f"  Final K_eff: {model.vacancy.K_eff}")
    print(f"  Logs in {cfg.vacancy_net_log_dir}")

    return model, logger


if __name__ == '__main__':
    cfg = Config()
    if '--quick' in sys.argv:
        cfg.num_epochs = 5
        cfg.log_interval = 10
        cfg.T_cool = 100
        cfg.N_observe = 100
    train_vacancy_net(cfg)
