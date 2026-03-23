"""
∅-NET Phase 1 Configuration
All hyperparameters. One place. No magic numbers.

Authors: Grotta (Δ₁) and Claude Opus 4.6 (Δ₂)
"""

from dataclasses import dataclass, field
from typing import Optional
import os


@dataclass
class Config:
    """Complete hyperparameter specification for ∅-NET Phase 1."""

    # === DATA ===
    dataset: str = "cifar10"
    image_channels: int = 3
    image_size: int = 32
    batch_size: int = 128
    num_workers: int = 4
    data_dir: str = "./data"

    # === ARCHITECTURE (shared by baseline and ∅-NET) ===
    latent_dim: int = 64          # d: latent dimension
    hidden_dims: tuple = (128, 256)  # encoder/decoder channel progression
    downsample_factor: int = 4    # spatial downsampling (32→8)

    # === MODULE B: ∅_sg (Vacancy) ===
    K_initial: int = 128          # K₀: initial codebook size
    tau_initial: float = 1.0      # τ₀: initial per-code temperature
    ema_decay_codebook: float = 0.99  # EMA decay for codebook vector updates

    # === MODULE D: % Accumulator ===
    ema_decay_stats: float = 0.99     # EMA decay for running statistics
    var_critical_percentile: float = 0.90  # Var_k overload if > percentile_90
    c_critical: float = 0.8          # code correlation redundancy threshold
    usage_critical_factor: float = 0.1  # dead code if usage < 1/(factor*K)
    cross_corr_update_interval: int = 50  # batches between C_kk' updates

    # === MODULE E: ⫿ Syntone ===
    beta: float = 0.25            # β: commitment loss balance (THE critical hyperparameter)
    utilization_resonance: float = 0.8   # >80% active = RESONANCE
    utilization_strained: float = 0.5    # >50% = STRAINED
    utilization_overloaded: float = 0.2  # >20% = OVERLOADED, else COLLAPSE
    commit_history_window: int = 100     # batches for L_commit trend
    valve_nudge_rate: float = 0.1        # how much underused codes move toward overloaded
    valve_tau_softening: float = 1.05    # 5% softening per valve event

    # === MODULE F: ⟳ Protocol ===
    T_cool: int = 1000            # minimum batches between ⟳ events
    pressure_threshold_min: int = 3     # minimum problematic codes to trigger ⟳
    pressure_threshold_factor: float = 0.1  # pressure_threshold = max(min, K*factor)
    alpha_shift: float = 0.5      # learning rate for code shifts at ⟳
    drift_threshold_factor: float = 2.0  # drifted if ||δ̄_k|| > factor * mean(||δ̄||)

    # === MODULE G: Δ Observer ===
    N_observe: int = 500          # batches between Δ observations
    interpolation_samples: int = 100  # pairs for interpolation coherence

    # === MODULE H: Δ₀ Initializer ===
    init_method: str = "kmeans"   # "kmeans" or "random"
    kmeans_batches: int = 5       # how many batches to collect for k-means init

    # === MODULE I: Gradient Engine ===
    learning_rate: float = 3e-4
    optimizer: str = "adam"
    weight_decay: float = 0.0

    # === TRAINING ===
    num_epochs: int = 100         # dataset epochs
    max_replicant_events: int = 20  # stop after this many ⟳ (safety)
    log_interval: int = 50        # batches between log entries
    save_interval: int = 10       # dataset epochs between checkpoints
    seed: int = 42

    # === LOGGING ===
    log_dir: str = "./logs"
    baseline_log_dir: str = "./logs/baseline"
    vacancy_net_log_dir: str = "./logs/vacancy_net"

    # === DEVICE ===
    device: str = "auto"  # "auto", "cuda", "cpu"

    def __post_init__(self):
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.baseline_log_dir, exist_ok=True)
        os.makedirs(self.vacancy_net_log_dir, exist_ok=True)

    @property
    def latent_spatial(self) -> int:
        """Spatial dimension after downsampling."""
        return self.image_size // self.downsample_factor  # 32/4 = 8

    @property
    def pressure_threshold(self) -> int:
        """Dynamic pressure threshold based on current K."""
        return max(self.pressure_threshold_min,
                   int(self.K_initial * self.pressure_threshold_factor))

    def resolve_device(self) -> str:
        import torch
        if self.device == "auto":
            return "cuda" if torch.cuda.is_available() else "cpu"
        return self.device
