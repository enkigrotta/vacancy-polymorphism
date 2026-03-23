"""
Module H: Δ₀ INITIALIZER (Inheritance)

Structural role: Converts ⟳ plan + %-statistics into a new codebook.
This is the inheritance function: Δ₀' = f(plan, %-stats, old_codebook).

Two modes:
  1. Initial: k-means on first encoder outputs (Δ₀_initial)
  2. At ⟳: execute restructuring plan (Δ₀' = inherited)

Type: Structural (one-shot computation at ⟳ events).
"""

import torch
import numpy as np


def kmeans_init(data: torch.Tensor, K: int, n_iter: int = 20) -> torch.Tensor:
    """
    K-means initialization of codebook vectors.

    Args:
        data: (N, d) — flattened encoder outputs
        K: number of codes
        n_iter: k-means iterations

    Returns:
        centroids: (K, d)
    """
    N, d = data.shape
    assert N >= K, f"Need at least K={K} data points, got {N}"

    # K-means++ initialization
    indices = [np.random.randint(N)]
    for _ in range(1, K):
        dists = torch.cdist(data, data[indices]).min(dim=1)[0]
        probs = dists.pow(2)
        probs = probs / probs.sum()
        idx = torch.multinomial(probs, 1).item()
        indices.append(idx)

    centroids = data[indices].clone()

    # K-means iterations
    for _ in range(n_iter):
        # Assign
        dists = torch.cdist(data, centroids)
        assignments = dists.argmin(dim=1)

        # Update
        new_centroids = torch.zeros_like(centroids)
        for k in range(K):
            mask = (assignments == k)
            if mask.sum() > 0:
                new_centroids[k] = data[mask].mean(dim=0)
            else:
                # Dead centroid: reinitialize near random point
                new_centroids[k] = data[np.random.randint(N)] + \
                    torch.randn(d, device=data.device) * 0.01
        centroids = new_centroids

    return centroids


def execute_restructuring_plan(plan: dict, old_codebook: torch.Tensor,
                                old_tau: torch.Tensor,
                                device: str = 'cpu') -> tuple:
    """
    Execute the ⟳ restructuring plan from Module F.

    This is the inheritance function: old structure + plan → new structure.
    Δ₀' carries the trace of the old cycle's failures.

    Args:
        plan: dict with 'splits', 'merges', 'shifts', 'resurrections'
        old_codebook: (K_old, d)
        old_tau: (K_old,)

    Returns:
        new_codebook: (K_new, d)
        new_tau: (K_new,)
        K_new: int
    """
    new_codes = [old_codebook[i].clone() for i in range(old_codebook.shape[0])]
    new_tau = [old_tau[i].clone() for i in range(old_tau.shape[0])]

    # Track indices to remove (from merges)
    codes_to_remove = set()

    # 1. Execute splits: overloaded code → two codes
    split_additions = []
    for split in plan['splits']:
        k = split['code']
        direction = split['direction'].to(device)
        magnitude = split['magnitude']

        code_plus = new_codes[k] + magnitude * direction
        code_minus = new_codes[k] - magnitude * direction

        new_codes[k] = code_plus
        split_additions.append((code_minus, new_tau[k].clone()))

    # Add split products at the end
    for code, tau in split_additions:
        new_codes.append(code)
        new_tau.append(tau)

    # 2. Execute merges: redundant pair → one code
    for merge in plan['merges']:
        k1, k2 = merge['code1'], merge['code2']
        new_position = merge['new_position'].to(device)
        new_codes[k1] = new_position
        codes_to_remove.add(k2)
        new_tau[k1] = (new_tau[k1] + new_tau[k2]) / 2

    # 3. Execute shifts: drifted code → shift by accumulated residual
    for shift in plan['shifts']:
        k = shift['code']
        shift_vec = shift['shift'].to(device)
        new_codes[k] = new_codes[k] + shift_vec

    # 4. Execute resurrections: dead code → place near high-Var code
    for res in plan['resurrections']:
        k = res['dead_code']
        new_position = res['new_position'].to(device)
        new_codes[k] = new_position
        # Reset tau to average
        mean_tau = sum(t.item() if isinstance(t, torch.Tensor) else t
                       for t in new_tau) / len(new_tau)
        new_tau[k] = torch.tensor(mean_tau, device=device)

    # 5. Remove merged codes
    final_codes = []
    final_tau = []
    for i in range(len(new_codes)):
        if i not in codes_to_remove:
            c = new_codes[i]
            t = new_tau[i]
            if not isinstance(c, torch.Tensor):
                c = torch.tensor(c, device=device)
            if not isinstance(t, torch.Tensor):
                t = torch.tensor(t, device=device)
            final_codes.append(c)
            final_tau.append(t)

    # Safety: K_eff ≥ 2 always
    K_new = len(final_codes)
    assert K_new >= 2, f"⟳ would reduce K to {K_new} < 2. Aborting."

    new_codebook = torch.stack(final_codes)
    new_tau_tensor = torch.stack(final_tau) if all(
        isinstance(t, torch.Tensor) for t in final_tau
    ) else torch.tensor([t.item() if isinstance(t, torch.Tensor) else t
                         for t in final_tau], device=device)

    return new_codebook, new_tau_tensor, K_new
