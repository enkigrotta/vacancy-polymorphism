"""
Module F: ⟳ PROTOCOL (Replicant)

Structural role: Bifurcation operator. Reads %-pressure and ⫿-health,
decides whether to restructure, computes restructuring plan.

ONE protocol, not two. ⫿ integrates ALL vectors [⤢↔↕] and makes
ONE coordination. The protocol weighs both %-pressure and ⫿-health,
but acts once.

Type: Structural (decision engine, no trainable parameters).
"""

import torch
import numpy as np
from .module_e_syntone import TensionState


class ReplicantProtocol:
    """
    ⟳: Decides when and how to restructure the codebook.

    Decision: should_trigger + plan (splits, merges, shifts, resurrections)
    """

    def __init__(self, T_cool: int = 1000,
                 pressure_threshold: int = 13,
                 alpha_shift: float = 0.5,
                 var_critical_percentile: float = 0.90,
                 c_critical: float = 0.8,
                 drift_threshold_factor: float = 2.0,
                 device: str = 'cpu'):
        self.T_cool = T_cool
        self.pressure_threshold = pressure_threshold
        self.alpha_shift = alpha_shift
        self.var_critical_percentile = var_critical_percentile
        self.c_critical = c_critical
        self.drift_threshold_factor = drift_threshold_factor
        self.device = device

        self.cooldown_counter = 0
        self.replicant_events = []  # full log of all ⟳

    def step(self):
        """Called every batch. Increments cooldown counter."""
        self.cooldown_counter += 1

    def decide(self, accumulator, syntone_state: TensionState,
               codebook: torch.Tensor) -> tuple:
        """
        Unified ⟳ decision.

        Args:
            accumulator: Module D (RemainderAccumulator)
            syntone_state: current TensionState from Module E
            codebook: current codebook from Module B

        Returns:
            (should_trigger: bool, plan: dict or None)
        """
        # Cooldown check
        if self.cooldown_counter < self.T_cool:
            return False, None

        # ⫿-health: can the system absorb restructuring?
        if syntone_state == TensionState.COLLAPSE:
            return False, None  # too fragile

        # %-pressure assessment
        overloaded = accumulator.get_overloaded_codes(
            self.var_critical_percentile)
        redundant = accumulator.get_redundant_pairs(self.c_critical)
        dead = accumulator.get_dead_codes()
        drifted = accumulator.get_drifted_codes(self.drift_threshold_factor)

        pressure = len(overloaded) + len(redundant) + len(dead)

        if syntone_state == TensionState.RESONANCE and pressure == 0:
            return False, None  # nothing to restructure

        # Trigger condition
        if pressure > self.pressure_threshold and syntone_state in (
                TensionState.RESONANCE, TensionState.STRAINED):
            plan = self._compute_plan(
                overloaded, redundant, dead, drifted,
                accumulator, codebook
            )
            return True, plan

        return False, None

    def _compute_plan(self, overloaded, redundant_pairs, dead, drifted,
                      accumulator, codebook):
        """Compute a single, coherent restructuring plan."""
        plan = {
            'splits': [],
            'merges': [],
            'shifts': [],
            'resurrections': [],
        }

        # Track codes already involved in operations
        involved = set()

        # SPLITS: overloaded codes → two codes at e_k ± direction of max variance
        for k in overloaded.tolist():
            if k in involved:
                continue
            # Don't split a code that's about to be merged
            in_merge = any(k in (p[0], p[1]) for p in redundant_pairs)
            if in_merge:
                continue

            # Direction = principal component of residuals for this code
            # Approximation: use delta_mean direction
            direction = accumulator.delta_mean[k]
            norm = direction.norm()
            if norm > 0:
                direction = direction / norm
            else:
                direction = torch.randn(self.latent_dim_or(codebook),
                                       device=self.device)
                direction = direction / direction.norm()

            magnitude = accumulator.delta_var[k].sqrt().item()
            magnitude = max(magnitude, 0.01)  # minimum split distance

            plan['splits'].append({
                'code': k,
                'direction': direction.cpu(),
                'magnitude': magnitude,
            })
            involved.add(k)

        # MERGES: redundant pairs → one code at centroid
        for (k1, k2) in redundant_pairs:
            if k1 in involved or k2 in involved:
                continue
            plan['merges'].append({
                'code1': k1,
                'code2': k2,
                'new_position': (
                    (codebook[k1] + codebook[k2]) / 2
                ).cpu(),
            })
            involved.add(k1)
            involved.add(k2)

        # SHIFTS: drifted codes → shift by accumulated mean residual
        for k in drifted.tolist():
            if k in involved:
                continue
            plan['shifts'].append({
                'code': k,
                'shift': (self.alpha_shift * accumulator.delta_mean[k]).cpu(),
            })
            involved.add(k)

        # RESURRECTIONS: dead codes → place near highest-Var_k codes
        for k in dead.tolist():
            if k in involved:
                continue
            target_k = accumulator.delta_var.argmax().item()
            perturbation = torch.randn(codebook.shape[1],
                                       device=self.device) * 0.01
            plan['resurrections'].append({
                'dead_code': k,
                'new_position': (codebook[target_k] + perturbation).cpu(),
            })
            involved.add(k)

        return plan

    def latent_dim_or(self, codebook):
        """Get latent dim from codebook shape."""
        return codebook.shape[1]

    def record_event(self, plan: dict, pre_stats: dict, epoch: int,
                     batch: int):
        """Log ⟳ event for analysis."""
        self.replicant_events.append({
            'epoch': epoch,
            'batch': batch,
            'plan': plan,
            'pre_stats': pre_stats,
            'cooldown_was': self.cooldown_counter,
        })
        self.cooldown_counter = 0  # reset cooldown
