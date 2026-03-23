"""
∅-NET Phase 1: Self-Governing Vacancy Network

All nine modules assembled into a single coherent system.

DATA FLOW (one batch):
  1. x → Module A (encoder) → z_e
  2. z_e → Module B (∅_sg) → e_k + delta
     delta → Module D (% accumulator) — stats updated
  3. e_k → Module C (decoder) → x̂
     L_recon = ||x - x̂||²
  4. z_e, e_k → Module E (⫿ syntone) → L_commit
     E reads Var_k from D → tension state
     IF STRAINED → valve shedding → Module B
  5. L_total → Module I (gradient engine) → weights updated
     Codebook in B updated via EMA
  6. Module F reads D + E → IF ⟳ triggered:
     F computes plan → H executes → new codebook → B
     D resets. New epoch begins.
  7. Module G (periodic) reads decoder + codebook → logs Δ metrics.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np

from modules.module_a_encoder import Encoder
from modules.module_b_vacancy import SelfGoverningVacancy
from modules.module_c_decoder import Decoder
from modules.module_d_accumulator import RemainderAccumulator
from modules.module_e_syntone import Syntone, TensionState
from modules.module_f_replicant import ReplicantProtocol
from modules.module_g_observer import DeltaObserver
from modules.module_h_initializer import execute_restructuring_plan
from modules.module_i_gradient import GradientEngine

from config import Config


class VacancyNet(nn.Module):
    """
    ∅-NET Phase 1.

    Self-governing VQ-VAE with remainder-driven restructuring.
    """

    def __init__(self, cfg: Config):
        super().__init__()
        self.cfg = cfg
        device = cfg.resolve_device()

        # === NEURAL MODULES (trainable) ===
        self.encoder = Encoder(
            cfg.image_channels, cfg.latent_dim, cfg.hidden_dims)
        self.decoder = Decoder(
            cfg.image_channels, cfg.latent_dim,
            tuple(reversed(cfg.hidden_dims)))

        # === STRUCTURAL MODULE: ∅_sg ===
        self.vacancy = SelfGoverningVacancy(
            cfg.K_initial, cfg.latent_dim, cfg.tau_initial,
            cfg.ema_decay_codebook)

        # === STRUCTURAL MODULES (non-trainable) ===
        self.accumulator = RemainderAccumulator(
            cfg.K_initial, cfg.latent_dim, cfg.ema_decay_stats,
            cfg.cross_corr_update_interval, device)

        self.syntone = Syntone(
            cfg.beta, cfg.utilization_resonance,
            cfg.utilization_strained, cfg.utilization_overloaded,
            cfg.commit_history_window, cfg.valve_nudge_rate,
            cfg.valve_tau_softening, device)

        self.replicant = ReplicantProtocol(
            cfg.T_cool, cfg.pressure_threshold,
            cfg.alpha_shift, cfg.var_critical_percentile,
            cfg.c_critical, cfg.drift_threshold_factor, device)

        self.observer = DeltaObserver(
            cfg.N_observe, cfg.interpolation_samples, device)

        # Gradient engine created externally (needs optimizer reference)
        self.gradient_engine = None

        # State
        self._total_batches = 0
        self._replicant_count = 0

    def setup_gradient_engine(self):
        """Create gradient engine after model is on device."""
        self.gradient_engine = GradientEngine(
            self.encoder.parameters(),
            self.decoder.parameters(),
            self.cfg.learning_rate,
            self.cfg.weight_decay,
        )

    def forward(self, x: torch.Tensor):
        """
        Full forward pass through all modules.

        Returns dict with all intermediate results for logging.
        """
        # STEP 1: Encoder (Prism)
        z_e = self.encoder(x)

        # STEP 2: Vacancy (∅_sg)
        e_k_ste, indices, delta = self.vacancy(z_e)

        # STEP 3: Decoder (Δ₂)
        x_hat = self.decoder(e_k_ste)

        # Losses
        L_recon = F.mse_loss(x_hat, x)
        L_commit = self.syntone.commitment_loss(z_e, e_k_ste)
        L_total = L_recon + L_commit

        return {
            'x_hat': x_hat,
            'z_e': z_e,
            'e_k': e_k_ste,
            'indices': indices,
            'delta': delta,
            'L_recon': L_recon,
            'L_commit': L_commit,
            'L_total': L_total,
        }

    def train_step(self, x: torch.Tensor, epoch: int, batch: int) -> dict:
        """
        Complete training step: forward + structural updates + gradient.

        This is the FULL data flow from the ТЗ §4.

        Returns:
            dict with all metrics for logging
        """
        self._total_batches += 1

        # === STEPS 1-3: Forward pass ===
        result = self.forward(x)

        # === STEP 2 (continued): Update % accumulator ===
        self.accumulator.update(result['delta'].detach(), result['indices'])

        # === STEP 4: Syntone tension monitor ===
        tension = self.syntone.tension_monitor(
            self.vacancy.K_eff,
            self.accumulator.usage_count,
            self.accumulator.delta_mean,
        )

        # Valve shedding if STRAINED/OVERLOADED
        did_shed = False
        if tension in (TensionState.STRAINED, TensionState.OVERLOADED):
            cb, tau, did_shed = self.syntone.valve_shedding(
                self.vacancy.codebook,
                self.vacancy.tau_k,
                self.accumulator.usage_count,
                self.accumulator.delta_var,
                self.vacancy.K_eff,
            )
            if did_shed:
                self.vacancy.codebook.copy_(cb)
                self.vacancy.tau_k.copy_(tau)

        # Emergency LR reduction at COLLAPSE
        if tension == TensionState.COLLAPSE and self.gradient_engine:
            self.gradient_engine.reduce_lr(0.5)

        # === STEP 5: Gradient step ===
        if self.gradient_engine:
            self.gradient_engine.step(result['L_total'])

        # === STEP 6: ⟳ Protocol check ===
        self.replicant.step()
        replicant_event = None

        if self._replicant_count < self.cfg.max_replicant_events:
            should_trigger, plan = self.replicant.decide(
                self.accumulator, tension, self.vacancy.codebook)

            if should_trigger and plan is not None:
                # Capture pre-⟳ state
                pre_stats = self.accumulator.get_stats_snapshot()
                pre_codebook = self.vacancy.codebook.clone()

                # Execute restructuring (Module H)
                new_cb, new_tau, K_new = execute_restructuring_plan(
                    plan, self.vacancy.codebook, self.vacancy.tau_k,
                    device=str(x.device),
                )

                # Apply new codebook to vacancy
                self.vacancy.replace_codebook(new_cb, new_tau)

                # Reset accumulator for new epoch
                self.accumulator.reset(K_new)

                # Log event
                self.replicant.record_event(plan, pre_stats, epoch, batch)
                self._replicant_count += 1

                replicant_event = {
                    'epoch': epoch,
                    'batch': batch,
                    'K_old': pre_codebook.shape[0],
                    'K_new': K_new,
                    'n_splits': len(plan['splits']),
                    'n_merges': len(plan['merges']),
                    'n_shifts': len(plan['shifts']),
                    'n_resurrections': len(plan['resurrections']),
                }

        # === STEP 7: Δ Observer (periodic) ===
        self.observer.step()

        # Collect result
        return {
            'L_recon': result['L_recon'].item(),
            'L_commit': result['L_commit'].item(),
            'L_total': result['L_total'].item(),
            'K_eff': self.vacancy.K_eff,
            'tension': tension.value,
            'valve_shed': did_shed,
            'replicant_event': replicant_event,
        }

    def collect_init_data(self, dataloader, n_batches: int = 5,
                          device: str = 'cpu'):
        """
        Collect encoder outputs for k-means initialization (Δ₀_initial).
        """
        self.eval()
        all_z = []
        with torch.no_grad():
            for i, (x, _) in enumerate(dataloader):
                if i >= n_batches:
                    break
                x = x.to(device)
                z_e = self.encoder(x)
                z_flat = z_e.permute(0, 2, 3, 1).reshape(-1, self.cfg.latent_dim)
                all_z.append(z_flat)
        self.train()
        return torch.cat(all_z, dim=0)
