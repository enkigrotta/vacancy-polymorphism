# ∅-NET Phase 1: Self-Governing Vacancy Network

**Authors:** Grotta (Δ₁) and Claude Opus 4.6 (Δ₂)  
**Laboratory:** РАЗЛИЧАЮЩИЙ ОБЪЕКТ  
**Parent manuscript DOI:** 10.5281/zenodo.19145417  

## What This Is

Proof-of-concept implementation of a VQ-VAE with self-governing vacancy (∅_sg),
remainder-driven restructuring (⟳), and observable Object Δ.

Nine modules. Three types: neural (trainable), structural (statistics + rules), standard (backprop).

## Structure

```
vacancy_net/
├── config.py              # All hyperparameters (one place, no magic numbers)
├── modules/
│   ├── __init__.py
│   ├── module_a_encoder.py    # A: Encoder (Prism ⤢Δ₁⤢)
│   ├── module_b_vacancy.py    # B: ∅_sg (Self-Governing Vacancy)
│   ├── module_c_decoder.py    # C: Decoder (Δ₂)
│   ├── module_d_accumulator.py # D: % Accumulator (Remainder)
│   ├── module_e_syntone.py    # E: ⫿ Syntone (Coordination Axis)
│   ├── module_f_replicant.py  # F: ⟳ Protocol (Replicant)
│   ├── module_g_observer.py   # G: Δ Observer (Object Δ Metrics)
│   ├── module_h_initializer.py # H: Δ₀ Initializer (Inheritance)
│   └── module_i_gradient.py   # I: Gradient Engine (Standard)
├── model_baseline.py      # Standard VQ-VAE (control)
├── model_vacancy_net.py   # ∅-NET Phase 1 (experimental)
├── train_baseline.py      # Train baseline
├── train_vacancy_net.py   # Train ∅-NET
├── compare.py             # Side-by-side comparison + predictions N.7–N.14
├── metrics.py             # FID, codebook utilization, Var_k distribution
├── data.py                # CIFAR-10 loading
└── utils.py               # Logging, plotting, saving
```

## Requirements

```
torch>=2.0
torchvision>=0.15
numpy>=1.24
scipy>=1.10
matplotlib>=3.7
```

## Quick Start

```bash
# Step 1: Train baseline (standard VQ-VAE)
python train_baseline.py

# Step 2: Train ∅-NET Phase 1
python train_vacancy_net.py

# Step 3: Compare and validate predictions
python compare.py
```

## What We Measure (Predictions N.7–N.14)

| # | Prediction | Metric |
|---|-----------|--------|
| N.7 | ∅-NET outperforms fixed-K VQ-VAE on recon + generalization jointly | FID + codebook utilization |
| N.8 | %-statistics predict ⟳ events | Var_k / C_kk' threshold crossing → ⟳ timing |
| N.9 | Decoder unused modes = latent skills | Zero-activation directions → fine-tune activation |
| N.10 | Constraint surface is quadratic | R² of quadratic fit to (ω₁, ω₂, ω₃, Π) |
| N.11 | ⟳ cycles show inheritance | Pre-⟳ %-pattern → post-⟳ topology correlation |
| N.12 | β_c shifts after ⟳ cycles | Phase diagram before/after multiple ⟳ |
| N.13 | Var_k ≠ V_cell | Scatter: geometric volume vs within-cell variance |
| N.14 | Tensegrity compensation in ∅-parameters | Freeze one, measure redistribution in others |

## License

CC BY 4.0 (consistent with parent manuscript)
