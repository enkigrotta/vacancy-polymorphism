"""
Metrics for ∅-NET Phase 1.

Includes:
  - FID (Fréchet Inception Distance) — simplified version
  - Codebook utilization
  - Var_k distribution analysis
  - Voronoi cell volume estimation (for N.13: Var_k ≠ V_cell)
  - PCA spectrum (for N.6: gap between λ₃ and λ₄)
  - Tensegrity compensation (for N.14)
"""

import torch
import numpy as np
from scipy import linalg


# ============================================================
# FID (simplified: using raw features, not Inception)
# For proof-of-concept, we compare latent statistics.
# Full FID with InceptionV3 can be added for paper.
# ============================================================

def compute_fid_from_features(real_features: np.ndarray,
                               fake_features: np.ndarray) -> float:
    """
    Compute FID between two sets of features.

    FID = ||μ_r - μ_f||² + Tr(Σ_r + Σ_f - 2(Σ_r·Σ_f)^{1/2})

    Args:
        real_features: (N, d) — features from real data
        fake_features: (N, d) — features from reconstructions
    Returns:
        fid: scalar
    """
    mu_r = real_features.mean(axis=0)
    mu_f = fake_features.mean(axis=0)
    sigma_r = np.cov(real_features, rowvar=False)
    sigma_f = np.cov(fake_features, rowvar=False)

    diff = mu_r - mu_f
    covmean, _ = linalg.sqrtm(sigma_r @ sigma_f, disp=False)
    if np.iscomplexobj(covmean):
        covmean = covmean.real

    fid = diff @ diff + np.trace(sigma_r + sigma_f - 2 * covmean)
    return float(fid)


def compute_reconstruction_fid(encoder, decoder, vacancy, dataloader,
                                device: str = 'cpu',
                                max_batches: int = 50) -> float:
    """
    Compute FID between original and reconstructed images.
    Uses encoder features as the feature space (not Inception).
    """
    real_feats = []
    recon_feats = []

    encoder.eval()
    decoder.eval()

    with torch.no_grad():
        for i, (x, _) in enumerate(dataloader):
            if i >= max_batches:
                break
            x = x.to(device)
            z_e = encoder(x)
            e_k, _, _ = vacancy(z_e)
            x_hat = decoder(e_k)

            # Use flattened encoder features
            z_real = z_e.reshape(x.shape[0], -1).cpu().numpy()
            z_recon = encoder(x_hat).reshape(x.shape[0], -1).cpu().numpy()

            real_feats.append(z_real)
            recon_feats.append(z_recon)

    real_feats = np.concatenate(real_feats, axis=0)
    recon_feats = np.concatenate(recon_feats, axis=0)

    encoder.train()
    decoder.train()

    return compute_fid_from_features(real_feats, recon_feats)


# ============================================================
# Codebook utilization
# ============================================================

def codebook_utilization(indices: torch.Tensor, K_eff: int) -> dict:
    """
    Compute codebook utilization statistics.

    Args:
        indices: concatenated code assignments from multiple batches
        K_eff: total number of codes

    Returns:
        dict with utilization, active_codes, usage_per_code, perplexity
    """
    counts = torch.zeros(K_eff)
    for k in range(K_eff):
        counts[k] = (indices == k).sum().float()

    total = counts.sum()
    if total == 0:
        return {
            'utilization': 0.0,
            'active_codes': 0,
            'K_eff': K_eff,
            'perplexity': 0.0,
            'usage_per_code': counts.numpy(),
        }

    probs = counts / total
    active = (counts > 0).sum().item()
    utilization = active / K_eff

    # Perplexity = exp(entropy)
    log_probs = torch.log(probs + 1e-10)
    entropy = -(probs * log_probs).sum().item()
    perplexity = np.exp(entropy)

    return {
        'utilization': utilization,
        'active_codes': active,
        'K_eff': K_eff,
        'perplexity': perplexity,
        'usage_per_code': counts.numpy(),
    }


# ============================================================
# Voronoi cell volume estimation (for N.13)
# ============================================================

def estimate_voronoi_volumes(codebook: torch.Tensor,
                              z_samples: torch.Tensor) -> np.ndarray:
    """
    Estimate Voronoi cell volumes by counting assignments from
    uniformly sampled points (Monte Carlo approximation).

    Args:
        codebook: (K, d)
        z_samples: (N, d) — encoder outputs (proxy for data distribution)

    Returns:
        volumes: (K,) — estimated volume per code (as fraction)
    """
    K = codebook.shape[0]
    dists = torch.cdist(z_samples, codebook)
    assignments = dists.argmin(dim=1)
    volumes = torch.zeros(K)
    for k in range(K):
        volumes[k] = (assignments == k).sum().float()
    volumes = volumes / max(volumes.sum(), 1)
    return volumes.numpy()


# ============================================================
# PCA spectrum (for N.6: gap between λ₃ and λ₄)
# ============================================================

def pca_spectrum(z_e_flat: np.ndarray, n_components: int = 10) -> np.ndarray:
    """
    Compute top eigenvalues of the covariance of encoder outputs.

    Args:
        z_e_flat: (N, d) — flattened encoder outputs
        n_components: how many eigenvalues to return

    Returns:
        eigenvalues: (n_components,) sorted descending
    """
    cov = np.cov(z_e_flat, rowvar=False)
    eigenvalues = np.linalg.eigvalsh(cov)[::-1]
    return eigenvalues[:n_components]


# ============================================================
# Inheritance correlation (for N.11)
# ============================================================

def inheritance_correlation(pre_stats: dict, post_codebook: torch.Tensor,
                             pre_codebook: torch.Tensor) -> float:
    """
    Measure correlation between pre-⟳ %-pattern and post-⟳ topology.

    Simple version: cosine similarity between pre-⟳ delta_mean
    pattern and post-⟳ code displacements.
    """
    delta_mean = pre_stats.get('delta_mean')
    if delta_mean is None or pre_codebook is None:
        return 0.0

    # Match codes (nearest neighbor mapping)
    K_old = pre_codebook.shape[0]
    K_new = post_codebook.shape[0]

    dists = torch.cdist(pre_codebook.float(), post_codebook.float())
    mapping = dists.argmin(dim=1)  # each old code → nearest new code

    # Displacements
    displacements = post_codebook[mapping] - pre_codebook
    # Pattern: delta_mean[:K_old]
    pattern = delta_mean[:K_old].float()

    # Flatten and compute cosine similarity
    d1 = displacements.reshape(-1)
    d2 = pattern.reshape(-1)

    if d1.norm() == 0 or d2.norm() == 0:
        return 0.0

    cos_sim = (d1 @ d2) / (d1.norm() * d2.norm())
    return cos_sim.item()


# ============================================================
# Tensegrity compensation (for N.14)
# ============================================================

def measure_tensegrity_response(vacancy_net_model, test_loader,
                                 device: str = 'cpu') -> dict:
    """
    Freeze one ∅-parameter, measure redistribution in others.
    This is an interventional test run after training.

    Returns dict with compensation measurements.
    """
    # This is a protocol description — actual implementation requires
    # training interventions (freeze K, measure τ and Var response).
    # Placeholder for the comparison script.
    return {
        'note': 'Tensegrity compensation requires interventional experiments. '
                'See compare.py for the protocol.',
    }
