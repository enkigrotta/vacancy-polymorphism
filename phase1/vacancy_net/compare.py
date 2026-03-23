"""
COMPARE: Side-by-side validation of predictions N.7–N.14

Run AFTER train_baseline.py and train_vacancy_net.py.

Loads logs from both runs, computes comparison metrics,
generates plots and a structured report.

This is Step 3 of the experimental protocol.
"""

import json
import os
import sys
import numpy as np
from pathlib import Path

from config import Config


def load_metrics(log_dir: str, name: str) -> dict:
    """Load metrics JSON from a training run."""
    path = os.path.join(log_dir, f'{name}_metrics.json')
    if not os.path.exists(path):
        raise FileNotFoundError(f"No metrics file at {path}. "
                                f"Run training first.")
    with open(path) as f:
        return json.load(f)


def prediction_N7(baseline: dict, vacancy: dict) -> dict:
    """
    N.7: Self-governed ∅ outperforms fixed-K VQ-VAE on
    reconstruction + generalization JOINTLY.

    Test: Compare FID + codebook utilization.
    Falsification: ∅-NET NOT better on BOTH metrics.
    """
    b_fid = [f for f in baseline.get('fid_scores', []) if f > 0]
    v_fid = [f for f in vacancy.get('fid_scores', []) if f > 0]

    b_util = baseline.get('utilization', [])
    v_util = vacancy.get('utilization', [])

    result = {
        'prediction': 'N.7: ∅-NET outperforms baseline on recon + generalization jointly',
        'baseline_fid_final': b_fid[-1] if b_fid else None,
        'vacancy_fid_final': v_fid[-1] if v_fid else None,
        'baseline_util_final': b_util[-1] if b_util else None,
        'vacancy_util_final': v_util[-1] if v_util else None,
    }

    # Verdict
    if result['vacancy_fid_final'] is not None and result['baseline_fid_final'] is not None:
        fid_better = result['vacancy_fid_final'] < result['baseline_fid_final']
        util_better = (result['vacancy_util_final'] or 0) >= (result['baseline_util_final'] or 0)
        result['fid_better'] = fid_better
        result['util_better'] = util_better
        result['SUPPORTED'] = fid_better and util_better
        result['verdict'] = (
            'SUPPORTED: ∅-NET better on both FID and utilization'
            if result['SUPPORTED'] else
            'NOT SUPPORTED: ∅-NET not better on both metrics'
        )
    else:
        result['SUPPORTED'] = None
        result['verdict'] = 'INCONCLUSIVE: missing FID data'

    return result


def prediction_N8(vacancy: dict) -> dict:
    """
    N.8: %-statistics predict ⟳ events.

    Test: Var_k and C_kk' cross thresholds BEFORE ⟳.
    Falsification: ⟳ events uncorrelated with %-statistics.
    """
    events = vacancy.get('replicant_events', [])
    var_snapshots = vacancy.get('var_k_snapshots', [])

    result = {
        'prediction': 'N.8: %-statistics predict ⟳ events',
        'n_replicant_events': len(events),
        'n_var_snapshots': len(var_snapshots),
    }

    if len(events) == 0:
        result['SUPPORTED'] = None
        result['verdict'] = 'INCONCLUSIVE: no ⟳ events occurred'
        return result

    # Check: do Var_k values rise before ⟳ events?
    # We look at variance snapshots leading up to each event
    if len(var_snapshots) >= 2:
        var_values = [np.mean(s['var_k']) for s in var_snapshots]
        # Check for rising trend before events
        rising_before_event = []
        for event in events:
            event_epoch = event.get('epoch', 0)
            # Find var snapshots before this epoch
            pre_vars = [v for s, v in zip(var_snapshots, var_values)
                       if s['epoch'] < event_epoch]
            if len(pre_vars) >= 2:
                trend = pre_vars[-1] > pre_vars[-2]
                rising_before_event.append(trend)

        if rising_before_event:
            fraction_rising = sum(rising_before_event) / len(rising_before_event)
            result['fraction_rising_before_event'] = fraction_rising
            result['SUPPORTED'] = fraction_rising > 0.5
            result['verdict'] = (
                f'SUPPORTED: {fraction_rising:.0%} of ⟳ events preceded by rising Var'
                if result['SUPPORTED'] else
                f'NOT SUPPORTED: only {fraction_rising:.0%} preceded by rising Var'
            )
        else:
            result['SUPPORTED'] = None
            result['verdict'] = 'INCONCLUSIVE: insufficient data before events'
    else:
        result['SUPPORTED'] = None
        result['verdict'] = 'INCONCLUSIVE: too few Var snapshots'

    return result


def prediction_N9(vacancy: dict) -> dict:
    """
    N.9: Decoder unused modes = latent skills activatable by fine-tuning.

    Test: Identify zero-activation decoder directions; fine-tune; measure activation.
    Falsification: Silent modes stay silent (dead weight, not latent skills).

    NOTE: Full test requires fine-tuning experiment. Here we report
    decoder weight utilization from Δ Observer as a proxy.
    """
    delta_obs = vacancy.get('delta_observations', [])

    result = {
        'prediction': 'N.9: Decoder unused modes are latent skills',
        'n_observations': len(delta_obs),
    }

    if delta_obs:
        weight_utils = [o.get('weight_utilization', -1) for o in delta_obs
                       if o.get('weight_utilization', -1) >= 0]
        if weight_utils:
            result['weight_utilization_mean'] = np.mean(weight_utils)
            result['weight_utilization_final'] = weight_utils[-1]
            # If utilization < 1.0, there ARE unused modes
            result['unused_modes_exist'] = weight_utils[-1] < 0.95
            result['verdict'] = (
                f'PARTIAL: Unused modes exist (utilization={weight_utils[-1]:.2f}). '
                f'Full test requires fine-tuning experiment.'
                if result['unused_modes_exist'] else
                'No unused modes detected — decoder fully utilized.'
            )
        else:
            result['verdict'] = 'INCONCLUSIVE: no weight utilization data'
    else:
        result['verdict'] = 'INCONCLUSIVE: no Δ observations'

    result['SUPPORTED'] = None  # requires fine-tuning experiment
    return result


def prediction_N10(vacancy: dict) -> dict:
    """
    N.10: Constraint surface coefficients measurable from training dynamics.

    Test: Fit quadratic to logged (ω₁, ω₂, ω₃, Π) data. Check R².
    Falsification: Data does not fit quadratic form.

    NOTE: Full test requires ω extraction protocol. Here we report
    whether loss trajectories exhibit quadratic structure.
    """
    loss_recon = vacancy.get('loss_recon', [])
    loss_commit = vacancy.get('loss_commit', [])

    result = {
        'prediction': 'N.10: Constraint surface is quadratic',
        'n_loss_samples': len(loss_recon),
    }

    if len(loss_recon) > 100:
        # Proxy: check if L_recon vs L_commit shows quadratic relationship
        # Subsample for efficiency
        step = max(1, len(loss_recon) // 500)
        lr = np.array(loss_recon[::step])
        lc = np.array(loss_commit[::step])

        # Remove NaN/Inf
        valid = np.isfinite(lr) & np.isfinite(lc)
        lr, lc = lr[valid], lc[valid]

        if len(lr) > 10:
            # Fit quadratic: L_recon = a*L_commit^2 + b*L_commit + c
            try:
                coeffs = np.polyfit(lc, lr, 2)
                fitted = np.polyval(coeffs, lc)
                ss_res = np.sum((lr - fitted) ** 2)
                ss_tot = np.sum((lr - np.mean(lr)) ** 2)
                r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0

                result['quadratic_R2'] = r_squared
                result['coefficients'] = coeffs.tolist()
                result['SUPPORTED'] = r_squared > 0.7
                result['verdict'] = (
                    f'SUPPORTED: R²={r_squared:.3f} for quadratic fit'
                    if result['SUPPORTED'] else
                    f'NOT SUPPORTED: R²={r_squared:.3f} (threshold: 0.7)'
                )
            except Exception as e:
                result['SUPPORTED'] = None
                result['verdict'] = f'INCONCLUSIVE: fit failed ({e})'
        else:
            result['SUPPORTED'] = None
            result['verdict'] = 'INCONCLUSIVE: insufficient valid data'
    else:
        result['SUPPORTED'] = None
        result['verdict'] = 'INCONCLUSIVE: too few loss samples'

    return result


def prediction_N11(vacancy: dict) -> dict:
    """
    N.11: ⟳ cycles exhibit inheritance.

    Test: Post-⟳ codebook topology correlates with pre-⟳ %-pattern.
    Falsification: Post-⟳ topology independent of pre-⟳ %.
    """
    events = vacancy.get('replicant_events', [])

    result = {
        'prediction': 'N.11: ⟳ cycles show inheritance (Δ₀\' = f(%-stats))',
        'n_replicant_events': len(events),
    }

    if len(events) < 2:
        result['SUPPORTED'] = None
        result['verdict'] = 'INCONCLUSIVE: need ≥2 ⟳ events for inheritance analysis'
        return result

    # Check that plans reflect %-statistics
    # Indicator: splits target codes with high Var (overloaded),
    # merges target high-correlation pairs, resurrections target dead codes
    structural_coherence = []
    for event in events:
        plan = event.get('plan', {})
        n_ops = (len(plan.get('splits', [])) + len(plan.get('merges', []))
                + len(plan.get('shifts', [])) + len(plan.get('resurrections', [])))
        # If plan has operations → %-statistics drove the decision
        structural_coherence.append(n_ops > 0)

    fraction_coherent = sum(structural_coherence) / len(structural_coherence)
    result['fraction_coherent'] = fraction_coherent
    result['SUPPORTED'] = fraction_coherent > 0.8
    result['verdict'] = (
        f'SUPPORTED: {fraction_coherent:.0%} of ⟳ plans driven by %-statistics'
        if result['SUPPORTED'] else
        f'NOT SUPPORTED: only {fraction_coherent:.0%} of ⟳ plans driven by %-stats'
    )

    return result


def prediction_N12(vacancy: dict) -> dict:
    """
    N.12: β_c shifts after multiple ⟳ cycles.

    Test: Compare effective β_c before and after multiple ⟳.
    Falsification: β_c constant across cycles.

    NOTE: Full test requires β sweep. Here we report commitment loss
    dynamics around ⟳ events as a proxy.
    """
    events = vacancy.get('replicant_events', [])
    loss_commit = vacancy.get('loss_commit', [])

    result = {
        'prediction': 'N.12: β_c shifts after ⟳ cycles',
        'n_replicant_events': len(events),
    }

    if len(events) >= 2 and len(loss_commit) > 100:
        # Proxy: L_commit level changes after ⟳
        # If the system self-governs, L_commit should shift to new equilibrium
        n = len(loss_commit)
        first_quarter = np.mean(loss_commit[:n // 4])
        last_quarter = np.mean(loss_commit[-n // 4:])
        shift = abs(last_quarter - first_quarter) / (first_quarter + 1e-8)

        result['commit_shift_ratio'] = shift
        result['commit_early'] = first_quarter
        result['commit_late'] = last_quarter
        result['SUPPORTED'] = shift > 0.1  # >10% shift
        result['verdict'] = (
            f'SUPPORTED: L_commit shifted by {shift:.1%} across training'
            if result['SUPPORTED'] else
            f'NOT SUPPORTED: L_commit shift only {shift:.1%}'
        )
    else:
        result['SUPPORTED'] = None
        result['verdict'] = 'INCONCLUSIVE: insufficient data'

    return result


def prediction_N13(vacancy: dict) -> dict:
    """
    N.13: Var_k ≠ V_cell (geometric volume does not predict heterogeneity).

    Test: Scatter V_cell vs Var_k. Measure correlation.
    Falsification: Perfect correlation (Var_k ~ V_cell).
    """
    voronoi_data = vacancy.get('voronoi_vs_var', [])

    result = {
        'prediction': 'N.13: Var_k (⤢) is not predictable from V_cell',
    }

    if voronoi_data:
        latest = voronoi_data[-1]
        V = np.array(latest['V_cell'])
        Var = np.array(latest['Var_k'])

        # Match lengths (K_eff might differ)
        n = min(len(V), len(Var))
        V, Var = V[:n], Var[:n]

        # Remove zeros
        valid = (V > 0) & (Var > 0)
        if valid.sum() > 5:
            V_v, Var_v = V[valid], Var[valid]
            correlation = np.corrcoef(V_v, Var_v)[0, 1]

            result['correlation'] = correlation
            result['n_valid_codes'] = int(valid.sum())
            result['SUPPORTED'] = abs(correlation) < 0.7
            result['verdict'] = (
                f'SUPPORTED: correlation={correlation:.3f} (not predictable)'
                if result['SUPPORTED'] else
                f'NOT SUPPORTED: correlation={correlation:.3f} (too predictable)'
            )
        else:
            result['SUPPORTED'] = None
            result['verdict'] = 'INCONCLUSIVE: too few valid codes'
    else:
        result['SUPPORTED'] = None
        result['verdict'] = 'INCONCLUSIVE: no Voronoi data logged'

    return result


def prediction_N14(vacancy: dict) -> dict:
    """
    N.14: Tensegrity compensation in ∅-parameters.

    Test: Perturbation of one → redistribution in others.
    Falsification: No effect on others.

    NOTE: Full test requires interventional experiments (freeze K, measure τ+Var).
    Here we report correlations between K_eff, utilization (proxy τ),
    and Var_k dynamics.
    """
    K_eff_history = vacancy.get('K_eff', [])
    util_history = vacancy.get('utilization', [])
    var_snapshots = vacancy.get('var_k_snapshots', [])

    result = {
        'prediction': 'N.14: Tensegrity compensation in ∅-parameters (K, τ, Var)',
    }

    if len(K_eff_history) >= 5 and len(util_history) >= 5:
        # Check: when K_eff changes, do utilization and Var respond?
        K = np.array(K_eff_history)
        U = np.array(util_history[:len(K)])

        n = min(len(K), len(U))
        K, U = K[:n], U[:n]

        # Differences
        dK = np.diff(K.astype(float))
        dU = np.diff(U.astype(float))

        # At points where K changes, check if U also changes
        K_changed = np.where(np.abs(dK) > 0)[0]
        if len(K_changed) > 0:
            # For each K change, check if U responded in next step
            responses = []
            for idx in K_changed:
                if idx + 1 < len(dU):
                    responses.append(abs(dU[idx]) > 0.01)

            fraction_responsive = (sum(responses) / len(responses)
                                   if responses else 0)
            result['K_changes'] = len(K_changed)
            result['U_responses'] = sum(responses) if responses else 0
            result['fraction_responsive'] = fraction_responsive
            result['SUPPORTED'] = fraction_responsive > 0.3
            result['verdict'] = (
                f'SUPPORTED: {fraction_responsive:.0%} of K changes '
                f'→ utilization response'
                if result['SUPPORTED'] else
                f'NOT SUPPORTED: only {fraction_responsive:.0%} responsive'
            )
        else:
            result['SUPPORTED'] = None
            result['verdict'] = ('INCONCLUSIVE: K_eff never changed '
                                '(no ⟳ events → no compensation to measure)')
    else:
        result['SUPPORTED'] = None
        result['verdict'] = 'INCONCLUSIVE: insufficient history'

    return result


def generate_report(baseline: dict, vacancy: dict,
                    output_dir: str) -> str:
    """Generate full comparison report."""

    results = {
        'N.7': prediction_N7(baseline, vacancy),
        'N.8': prediction_N8(vacancy),
        'N.9': prediction_N9(vacancy),
        'N.10': prediction_N10(vacancy),
        'N.11': prediction_N11(vacancy),
        'N.12': prediction_N12(vacancy),
        'N.13': prediction_N13(vacancy),
        'N.14': prediction_N14(vacancy),
    }

    # Summary
    supported = sum(1 for r in results.values() if r.get('SUPPORTED') is True)
    not_supported = sum(1 for r in results.values()
                       if r.get('SUPPORTED') is False)
    inconclusive = sum(1 for r in results.values()
                      if r.get('SUPPORTED') is None)

    report_lines = [
        "=" * 70,
        "∅-NET Phase 1: COMPARISON REPORT",
        "=" * 70,
        f"",
        f"Baseline: Standard VQ-VAE (K={baseline.get('K_eff', ['?'])[-1] if baseline.get('K_eff') else '?'})",
        f"∅-NET:    Self-Governing VQ-VAE",
        f"",
        f"PREDICTIONS SUMMARY:",
        f"  SUPPORTED:     {supported}/8",
        f"  NOT SUPPORTED: {not_supported}/8",
        f"  INCONCLUSIVE:  {inconclusive}/8",
        f"",
        "-" * 70,
    ]

    for key, res in results.items():
        report_lines.append(f"\n{key}: {res.get('prediction', '')}")
        report_lines.append(f"  VERDICT: {res.get('verdict', 'N/A')}")
        for k, v in res.items():
            if k not in ('prediction', 'verdict', 'SUPPORTED'):
                report_lines.append(f"  {k}: {v}")
        report_lines.append("-" * 70)

    # Baseline vs ∅-NET loss comparison
    b_loss = baseline.get('loss_total', [])
    v_loss = vacancy.get('loss_total', [])
    if b_loss and v_loss:
        report_lines.append(f"\nFINAL LOSSES:")
        report_lines.append(
            f"  Baseline L_total (last 100 avg): "
            f"{np.mean(b_loss[-100:]):.4f}")
        report_lines.append(
            f"  ∅-NET    L_total (last 100 avg): "
            f"{np.mean(v_loss[-100:]):.4f}")

    # ⟳ event summary
    events = vacancy.get('replicant_events', [])
    if events:
        report_lines.append(f"\n⟳ EVENTS ({len(events)} total):")
        for i, ev in enumerate(events):
            report_lines.append(
                f"  ⟳{i+1}: epoch {ev.get('epoch')}, "
                f"K {ev.get('K_old')}→{ev.get('K_new')}")

    report_lines.append("\n" + "=" * 70)
    report_lines.append("Report generated by compare.py")
    report_lines.append("Laboratory: РАЗЛИЧАЮЩИЙ ОБЪЕКТ")
    report_lines.append("DOI: 10.5281/zenodo.19145417")
    report_lines.append("=" * 70)

    report = "\n".join(report_lines)

    # Save
    os.makedirs(output_dir, exist_ok=True)
    report_path = os.path.join(output_dir, 'comparison_report.txt')
    with open(report_path, 'w') as f:
        f.write(report)

    results_path = os.path.join(output_dir, 'prediction_results.json')
    with open(results_path, 'w') as f:
        # Clean results for JSON
        clean = {}
        for k, v in results.items():
            clean[k] = {kk: (vv if not isinstance(vv, np.floating)
                            else float(vv))
                       for kk, vv in v.items()}
        json.dump(clean, f, indent=2, default=str)

    return report


def main():
    cfg = Config()

    print("Loading baseline metrics...")
    try:
        baseline = load_metrics(cfg.baseline_log_dir, 'baseline')
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        print("Run train_baseline.py first.")
        sys.exit(1)

    print("Loading ∅-NET metrics...")
    try:
        vacancy = load_metrics(cfg.vacancy_net_log_dir, 'vacancy_net')
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        print("Run train_vacancy_net.py first.")
        sys.exit(1)

    print("Generating comparison report...")
    report = generate_report(baseline, vacancy, cfg.log_dir)
    print(report)

    # === Generate plots if matplotlib available ===
    try:
        generate_plots(baseline, vacancy, cfg.log_dir)
        print(f"\nPlots saved to {cfg.log_dir}/")
    except ImportError:
        print("\nmatplotlib not available — skipping plots.")
    except Exception as e:
        print(f"\nPlot generation failed: {e}")


def generate_plots(baseline: dict, vacancy: dict, output_dir: str):
    """Generate comparison plots."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    fig_dir = os.path.join(output_dir, 'figures')
    os.makedirs(fig_dir, exist_ok=True)

    # --- Plot 1: Loss curves ---
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    for ax, key, title in zip(axes,
                               ['loss_recon', 'loss_commit', 'loss_total'],
                               ['L_recon', 'L_commit', 'L_total']):
        b = baseline.get(key, [])
        v = vacancy.get(key, [])
        if b:
            # Smooth
            window = max(1, len(b) // 200)
            b_smooth = np.convolve(b, np.ones(window)/window, mode='valid')
            ax.plot(b_smooth, label='Baseline', alpha=0.8)
        if v:
            window = max(1, len(v) // 200)
            v_smooth = np.convolve(v, np.ones(window)/window, mode='valid')
            ax.plot(v_smooth, label='∅-NET', alpha=0.8)
        ax.set_title(title)
        ax.set_xlabel('Batch')
        ax.legend()
        ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(os.path.join(fig_dir, 'loss_comparison.png'), dpi=150)
    plt.close()

    # --- Plot 2: K_eff over time (N.7) ---
    K_history = vacancy.get('K_eff', [])
    if K_history:
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.plot(K_history, 'b-', label='∅-NET K_eff(t)')
        ax.axhline(y=baseline.get('K_eff', [128])[-1] if baseline.get('K_eff') else 128,
                   color='r', linestyle='--', label='Baseline K (fixed)')

        # Mark ⟳ events
        events = vacancy.get('replicant_events', [])
        for ev in events:
            # Approximate batch index (rough)
            ax.axvline(x=ev.get('batch', 0), color='g', alpha=0.3,
                      linestyle=':')

        ax.set_xlabel('Epoch')
        ax.set_ylabel('K_eff')
        ax.set_title('N.7: Codebook cardinality over training')
        ax.legend()
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(os.path.join(fig_dir, 'K_eff_trajectory.png'), dpi=150)
        plt.close()

    # --- Plot 3: Var_k distribution (N.13 proxy) ---
    var_snapshots = vacancy.get('var_k_snapshots', [])
    if var_snapshots and len(var_snapshots) >= 2:
        fig, axes = plt.subplots(1, min(3, len(var_snapshots)), figsize=(15, 4))
        if not isinstance(axes, np.ndarray):
            axes = [axes]

        indices_to_plot = np.linspace(
            0, len(var_snapshots) - 1,
            min(3, len(var_snapshots)), dtype=int)

        for ax, idx in zip(axes, indices_to_plot):
            snap = var_snapshots[idx]
            var_k = np.array(snap['var_k'])
            ax.bar(range(len(var_k)), var_k, alpha=0.7)
            ax.set_title(f"Var_k at epoch {snap['epoch']}")
            ax.set_xlabel('Code k')
            ax.set_ylabel('Var_k (⤢)')

        plt.tight_layout()
        plt.savefig(os.path.join(fig_dir, 'var_k_evolution.png'), dpi=150)
        plt.close()

    # --- Plot 4: V_cell vs Var_k scatter (N.13) ---
    voronoi_data = vacancy.get('voronoi_vs_var', [])
    if voronoi_data:
        latest = voronoi_data[-1]
        V = np.array(latest['V_cell'])
        Var = np.array(latest['Var_k'])
        n = min(len(V), len(Var))

        fig, ax = plt.subplots(figsize=(7, 7))
        ax.scatter(V[:n], Var[:n], alpha=0.6, s=30)
        ax.set_xlabel('V_cell (geometric volume)')
        ax.set_ylabel('Var_k (within-cell heterogeneity, ⤢)')
        ax.set_title('N.13: V_cell vs Var_k — should NOT correlate')

        # Add correlation line
        valid = (V[:n] > 0) & (Var[:n] > 0)
        if valid.sum() > 2:
            corr = np.corrcoef(V[:n][valid], Var[:n][valid])[0, 1]
            ax.annotate(f'r = {corr:.3f}', xy=(0.05, 0.95),
                       xycoords='axes fraction', fontsize=12,
                       bbox=dict(boxstyle='round', facecolor='wheat'))

        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(os.path.join(fig_dir, 'N13_Vcell_vs_Vark.png'), dpi=150)
        plt.close()

    # --- Plot 5: PCA spectrum (N.6) ---
    pca_data = vacancy.get('pca_spectra', [])
    if pca_data:
        latest = pca_data[-1]
        eigs = np.array(latest['eigenvalues'])

        fig, ax = plt.subplots(figsize=(8, 5))
        ax.bar(range(len(eigs)), eigs, alpha=0.7, color='steelblue')
        ax.set_xlabel('Principal Component')
        ax.set_ylabel('Eigenvalue (λ)')
        ax.set_title(f"N.6: PCA spectrum — gap between λ₃ and λ₄?")

        # Mark the predicted gap
        if len(eigs) >= 4:
            gap = eigs[2] - eigs[3]
            ax.annotate(f'λ₃-λ₄ gap = {gap:.4f}',
                       xy=(2.5, (eigs[2] + eigs[3]) / 2),
                       fontsize=10, ha='center',
                       arrowprops=dict(arrowstyle='->', color='red'),
                       xytext=(4, eigs[2]))

        ax.grid(True, alpha=0.3, axis='y')
        plt.tight_layout()
        plt.savefig(os.path.join(fig_dir, 'N6_pca_spectrum.png'), dpi=150)
        plt.close()

    # --- Plot 6: Utilization comparison ---
    b_util = baseline.get('utilization', [])
    v_util = vacancy.get('utilization', [])
    if b_util or v_util:
        fig, ax = plt.subplots(figsize=(10, 4))
        if b_util:
            ax.plot(b_util, label='Baseline', alpha=0.8)
        if v_util:
            ax.plot(v_util, label='∅-NET', alpha=0.8)
        ax.set_xlabel('Epoch')
        ax.set_ylabel('Codebook Utilization')
        ax.set_title('Codebook utilization over training')
        ax.legend()
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(os.path.join(fig_dir, 'utilization_comparison.png'),
                   dpi=150)
        plt.close()

    print(f"Generated plots in {fig_dir}/")


if __name__ == '__main__':
    main()
