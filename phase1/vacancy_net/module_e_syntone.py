"""
Module E: ⫿ SYNTONE (Coordination Axis)

Structural role: Resonating system. Coordinates vectors [⤢↔↕]
through the vacancy. Does not create tension — coordinates it.

Three functions:
  1. Commitment loss (the loss term)
  2. Tension monitor (the diagnostic)
  3. Valve shedding (the preemptive action)

Type: Structural (loss function + diagnostic + valve controller).
"""

import torch
import numpy as np
from enum import Enum


class TensionState(Enum):
    RESONANCE = "resonance"       # >80% utilization, stable
    STRAINED = "strained"         # 50-80%, oscillating
    OVERLOADED = "overloaded"     # 20-50%, rising
    COLLAPSE = "collapse"         # <20%, diverging


class Syntone:
    """
    ⫿: The coordination axis. Integrates all vectors [⤢↔↕] and
    makes ONE coordination decision.
    """

    def __init__(self, beta: float = 0.25,
                 util_resonance: float = 0.8,
                 util_strained: float = 0.5,
                 util_overloaded: float = 0.2,
                 history_window: int = 100,
                 valve_nudge_rate: float = 0.1,
                 valve_tau_softening: float = 1.05,
                 device: str = 'cpu'):
        self.beta = beta
        self.util_resonance = util_resonance
        self.util_strained = util_strained
        self.util_overloaded = util_overloaded
        self.valve_nudge_rate = valve_nudge_rate
        self.valve_tau_softening = valve_tau_softening
        self.device = device

        # Internal state
        self.commit_history = []
        self.tension_history = []
        self.history_window = history_window
        self.current_state = TensionState.RESONANCE

    def commitment_loss(self, z_e: torch.Tensor, e_k: torch.Tensor) -> torch.Tensor:
        """
        L_commit = ||z_e - sg[e_k]||² + β·||sg[z_e] - e_k||²

        First term: encoder adapts to codebook
        Second term: codebook adapts to encoder (via EMA in Module B)
        """
        L1 = (z_e - e_k.detach()).pow(2).mean()
        L2 = (z_e.detach() - e_k).pow(2).mean()
        loss = L1 + self.beta * L2

        self.commit_history.append(loss.item())
        if len(self.commit_history) > self.history_window * 2:
            self.commit_history = self.commit_history[-self.history_window * 2:]

        return loss

    def tension_monitor(self, K_eff: int, usage_count: torch.Tensor,
                        delta_mean: torch.Tensor) -> TensionState:
        """
        Diagnose structural state of ⫿.

        Returns: RESONANCE / STRAINED / OVERLOADED / COLLAPSE
        """
        # Utilization: fraction of active codes
        total = usage_count.sum()
        if total == 0:
            utilization = 0.0
        else:
            active = (usage_count > 0).sum().float()
            utilization = (active / K_eff).item()

        # Commitment trend: is L_commit rising?
        if len(self.commit_history) >= self.history_window:
            recent = self.commit_history[-self.history_window:]
            half = len(recent) // 2
            first_half = np.mean(recent[:half])
            second_half = np.mean(recent[half:])
            commit_rising = second_half > first_half * 1.05
        else:
            commit_rising = False

        # Alignment: how far codes are from encoder mean
        alignment = delta_mean.norm(dim=1).mean().item()

        # Determine state
        if utilization > self.util_resonance and not commit_rising:
            state = TensionState.RESONANCE
        elif utilization > self.util_strained:
            state = TensionState.STRAINED
        elif utilization > self.util_overloaded:
            state = TensionState.OVERLOADED
        else:
            state = TensionState.COLLAPSE

        self.current_state = state
        self.tension_history.append({
            'state': state.value,
            'utilization': utilization,
            'commit_rising': commit_rising,
            'alignment': alignment,
        })

        return state

    @torch.no_grad()
    def valve_shedding(self, codebook: torch.Tensor, tau_k: torch.Tensor,
                       usage_count: torch.Tensor, delta_var: torch.Tensor,
                       K_eff: int) -> tuple:
        """
        When STRAINED: nudge underused codes toward high-pressure regions.
        This is ∅% (purple vacancy) partially opening.

        Returns:
            codebook: possibly modified
            tau_k: possibly modified
            did_shed: bool
        """
        if self.current_state not in (TensionState.STRAINED,
                                      TensionState.OVERLOADED):
            return codebook, tau_k, False

        total = usage_count.sum()
        if total == 0:
            return codebook, tau_k, False

        usage_critical = 1.0 / (10.0 * K_eff)
        relative_usage = usage_count / total

        underused = torch.where(relative_usage < usage_critical)[0]
        if len(underused) == 0:
            return codebook, tau_k, False

        # Find overloaded codes (high Var_k)
        if delta_var.sum() == 0:
            return codebook, tau_k, False
        p75 = torch.quantile(delta_var, 0.75)
        overloaded = torch.where(delta_var > p75)[0]
        if len(overloaded) == 0:
            return codebook, tau_k, False

        # Nudge underused toward overloaded
        for u in underused:
            dists = (codebook[u] - codebook[overloaded]).pow(2).sum(dim=1)
            nearest_idx = dists.argmin()
            target = codebook[overloaded[nearest_idx]]
            codebook[u] = (
                codebook[u] + self.valve_nudge_rate * (target - codebook[u])
            )

        # Slightly soften τ for overloaded codes
        for k in overloaded:
            tau_k[k] *= self.valve_tau_softening

        return codebook, tau_k, True

    def get_state_summary(self) -> dict:
        """For logging."""
        return {
            'state': self.current_state.value,
            'commit_loss_recent': (
                np.mean(self.commit_history[-20:])
                if self.commit_history else 0.0
            ),
            'history_len': len(self.tension_history),
        }
