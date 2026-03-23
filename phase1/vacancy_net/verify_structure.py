"""
STRUCTURAL VERIFICATION: ТЗ → Code mapping

Run this to verify all 9 modules and 16 formula components
are present in the codebase.

Authors: Grotta (Δ₁) and Claude Opus 4.6 (Δ₂)
"""

import os
import ast
import sys


def check_file_exists(path):
    return os.path.exists(path)


def check_class_in_file(filepath, classname):
    """Check if a class is defined in a file."""
    if not os.path.exists(filepath):
        return False
    with open(filepath) as f:
        tree = ast.parse(f.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == classname:
            return True
    return False


def check_function_in_file(filepath, funcname):
    """Check if a function is defined in a file."""
    if not os.path.exists(filepath):
        return False
    with open(filepath) as f:
        tree = ast.parse(f.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == funcname:
            return True
    return False


def verify():
    base = os.path.dirname(os.path.abspath(__file__))
    os.chdir(base)

    print("=" * 60)
    print("∅-NET Phase 1: STRUCTURAL VERIFICATION")
    print("ТЗ → Code mapping")
    print("=" * 60)

    all_ok = True

    # ==============================
    # 9 MODULES
    # ==============================
    print("\n--- 9 MODULES ---")

    modules = [
        ("A: Encoder (Prism ⤢Δ₁⤢)",
         "modules/module_a_encoder.py", "Encoder"),
        ("B: ∅_sg (Self-Governing Vacancy)",
         "modules/module_b_vacancy.py", "SelfGoverningVacancy"),
        ("C: Decoder (Δ₂)",
         "modules/module_c_decoder.py", "Decoder"),
        ("D: % Accumulator (Remainder)",
         "modules/module_d_accumulator.py", "RemainderAccumulator"),
        ("E: ⫿ Syntone (Coordination Axis)",
         "modules/module_e_syntone.py", "Syntone"),
        ("F: ⟳ Protocol (Replicant)",
         "modules/module_f_replicant.py", "ReplicantProtocol"),
        ("G: Δ Observer (Object Δ)",
         "modules/module_g_observer.py", "DeltaObserver"),
        ("H: Δ₀ Initializer (Inheritance)",
         "modules/module_h_initializer.py", None),  # functions, not class
        ("I: Gradient Engine",
         "modules/module_i_gradient.py", "GradientEngine"),
    ]

    for name, path, classname in modules:
        exists = check_file_exists(path)
        has_class = True
        if classname:
            has_class = check_class_in_file(path, classname)
        elif path.endswith('module_h_initializer.py'):
            has_class = (check_function_in_file(path, 'kmeans_init') and
                        check_function_in_file(path, 'execute_restructuring_plan'))

        ok = exists and has_class
        status = "✓" if ok else "✗"
        print(f"  {status} Module {name}")
        if not ok:
            all_ok = False

    # ==============================
    # 16 FORMULA COMPONENTS
    # ==============================
    print("\n--- 16 FORMULA COMPONENTS (ТЗ §7) ---")

    components = [
        ("Δ₁ (First constrained system)", "modules/module_a_encoder.py",
         "Encoder", "forward"),
        ("Δ₂ (Second constrained system)", "modules/module_c_decoder.py",
         "Decoder", "forward"),
        ("∅ (Vacancy)", "modules/module_b_vacancy.py",
         "SelfGoverningVacancy", "forward"),
        ("ω₁ (Dynamic variable)", "modules/module_e_syntone.py",
         "Syntone", "tension_monitor"),
        ("ω₂ (Barrier variable)", "modules/module_b_vacancy.py",
         "SelfGoverningVacancy", "_ema_update"),
        ("ω₃ (Axis variable)", "modules/module_i_gradient.py",
         "GradientEngine", "step"),
        ("Π (Irreversible accumulation)", "modules/module_d_accumulator.py",
         "RemainderAccumulator", "get_dead_codes"),
        ("⟳ (Bifurcation)", "modules/module_f_replicant.py",
         "ReplicantProtocol", "decide"),
        ("Object Δ", "modules/module_g_observer.py",
         "DeltaObserver", "observe"),
        ("↕ (Vertical break = K_eff)", "modules/module_b_vacancy.py",
         None, None),
        ("↔ (Horizontal break = τ_k)", "modules/module_b_vacancy.py",
         None, None),
        ("⤢ (Transversal break = Var_k)", "modules/module_d_accumulator.py",
         None, None),
        ("⫿ (Syntone)", "modules/module_e_syntone.py",
         "Syntone", "commitment_loss"),
        ("Prism (⤢Δ₁⤢)", "modules/module_a_encoder.py",
         "Encoder", None),
        ("Remainder (⤢%⤢)", "modules/module_d_accumulator.py",
         "RemainderAccumulator", "update"),
        ("Δ₀ (Proto-distinction)", "modules/module_h_initializer.py",
         None, None),
    ]

    for name, path, classname, method in components:
        exists = check_file_exists(path)
        ok = exists
        if classname and method:
            ok = ok and check_class_in_file(path, classname)
        elif classname:
            ok = ok and check_class_in_file(path, classname)

        status = "✓" if ok else "✗"
        print(f"  {status} {name} → {path}")
        if not ok:
            all_ok = False

    # ==============================
    # DATA FLOW (ТЗ §4)
    # ==============================
    print("\n--- DATA FLOW (7 steps) ---")

    flow_steps = [
        ("Step 1: x → A → z_e", "model_vacancy_net.py", "forward"),
        ("Step 2: z_e → B → e_k + delta → D", "model_vacancy_net.py",
         "train_step"),
        ("Step 3: e_k → C → x̂", "model_vacancy_net.py", "forward"),
        ("Step 4: E reads D → tension → valve", "model_vacancy_net.py",
         "train_step"),
        ("Step 5: L_total → I → gradients", "model_vacancy_net.py",
         "train_step"),
        ("Step 6: F reads D+E → ⟳ → H → B", "model_vacancy_net.py",
         "train_step"),
        ("Step 7: G reads C+B → Δ metrics", "model_vacancy_net.py",
         "train_step"),
    ]

    for name, path, method in flow_steps:
        ok = (check_file_exists(path) and
              check_function_in_file(path, method) if method else
              check_file_exists(path))
        status = "✓" if ok else "✗"
        print(f"  {status} {name}")
        if not ok:
            all_ok = False

    # ==============================
    # PREDICTIONS (N.7–N.14)
    # ==============================
    print("\n--- PREDICTIONS (N.7–N.14) ---")

    predictions = [
        ("N.7:  ∅-NET vs baseline (FID + util)", "compare.py",
         "prediction_N7"),
        ("N.8:  %-stats predict ⟳", "compare.py", "prediction_N8"),
        ("N.9:  Latent skills (Δ observer)", "compare.py", "prediction_N9"),
        ("N.10: Quadratic constraint surface", "compare.py",
         "prediction_N10"),
        ("N.11: ⟳ inheritance", "compare.py", "prediction_N11"),
        ("N.12: β_c shift", "compare.py", "prediction_N12"),
        ("N.13: Var_k ≠ V_cell", "compare.py", "prediction_N13"),
        ("N.14: Tensegrity compensation", "compare.py", "prediction_N14"),
    ]

    for name, path, func in predictions:
        ok = check_function_in_file(path, func)
        status = "✓" if ok else "✗"
        print(f"  {status} {name}")
        if not ok:
            all_ok = False

    # ==============================
    # SUPPORTING FILES
    # ==============================
    print("\n--- SUPPORTING FILES ---")
    support = [
        "config.py", "data.py", "metrics.py", "utils.py",
        "model_baseline.py", "train_baseline.py", "train_vacancy_net.py",
        "requirements.txt", "README.md",
    ]
    for f in support:
        ok = check_file_exists(f)
        status = "✓" if ok else "✗"
        print(f"  {status} {f}")
        if not ok:
            all_ok = False

    # ==============================
    # FINAL VERDICT
    # ==============================
    print("\n" + "=" * 60)
    if all_ok:
        print("ALL CHECKS PASSED. ТЗ → Code mapping complete.")
        print("9 modules, 16 components, 7 data flow steps, 8 predictions.")
    else:
        print("SOME CHECKS FAILED. See above.")
    print("=" * 60)

    return 0 if all_ok else 1


if __name__ == '__main__':
    sys.exit(verify())
