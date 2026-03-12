"""
Local optimizer: start from best known parameters (step 4) and do
random perturbation hill-climbing to improve margins.
"""
import os, sys, json, csv, re, subprocess, tempfile, time
import numpy as np
from concurrent.futures import ProcessPoolExecutor, as_completed

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
NGSPICE = os.environ.get("NGSPICE", "ngspice")

# Step 4 best parameters
BEST_PARAMS = {
    "Cfly1": 127.589,
    "Cfly2": 198.350,
    "Cmid": 23.090,
    "Cout": 215.145,
    "Freq": 45.383,
    "Ln1": 0.511,
    "Ln2": 0.565,
    "Lp1": 0.643,
    "Lp2": 0.605,
    "Rload": 1980.688,
    "Wn1": 64.806,
    "Wn2": 92.604,
    "Wp1": 98.794,
    "Wp2": 96.425,
}

# Parameter bounds
BOUNDS = {
    "Wn1": (5, 150), "Ln1": (0.5, 5),
    "Wp1": (5, 150), "Lp1": (0.5, 5),
    "Wn2": (5, 150), "Ln2": (0.5, 5),
    "Wp2": (5, 150), "Lp2": (0.5, 5),
    "Cfly1": (50, 500), "Cfly2": (50, 500),
    "Cmid": (10, 300), "Cout": (50, 500),
    "Rload": (1000, 5000), "Freq": (5, 60),
}


def load_design():
    with open(os.path.join(PROJECT_DIR, "design.cir")) as f:
        return f.read()


def load_specs():
    with open(os.path.join(PROJECT_DIR, "specs.json")) as f:
        return json.load(f)


def format_netlist(template, param_values):
    def _replace(match):
        key = match.group(1)
        if key in param_values:
            return str(param_values[key])
        return match.group(0)
    return re.sub(r'\{(\w+)\}', _replace, template)


def run_sim(args):
    template, params, idx, tmp_dir = args
    netlist = format_netlist(template, params)
    path = os.path.join(tmp_dir, f"opt_{idx}.cir")
    with open(path, "w") as f:
        f.write(netlist)
    try:
        result = subprocess.run(
            [NGSPICE, "-b", path],
            capture_output=True, text=True, timeout=60,
            cwd=PROJECT_DIR
        )
        output = result.stdout + result.stderr
    except:
        return idx, None
    finally:
        try:
            os.unlink(path)
        except:
            pass

    if "RESULT_DONE" not in output:
        return idx, None

    m = {}
    for line in output.split("\n"):
        if "RESULT_" in line and "RESULT_DONE" not in line:
            match = re.search(r'(RESULT_\w+)\s+([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)', line)
            if match:
                m[match.group(1)] = float(match.group(2))
    return idx, m


def score(m):
    """Score: higher is better. Weighted sum of margins above spec thresholds."""
    if not m:
        return -1e6

    s = 0.0
    vout = m.get("RESULT_VOUT_V", 0)
    iout = m.get("RESULT_IOUT_MA", 0)
    eff = m.get("RESULT_EFFICIENCY_PCT", 0)
    ripple = m.get("RESULT_RIPPLE_MV", 999)
    startup = m.get("RESULT_STARTUP_US", 999)

    # Must meet all specs
    if vout < 3.0 or iout < 1.0 or eff < 50 or ripple > 100 or startup > 50:
        # Penalty proportional to how far we are
        penalty = 0
        if vout < 3.0: penalty += (3.0 - vout) * 100
        if iout < 1.0: penalty += (1.0 - iout) * 100
        if eff < 50: penalty += (50 - eff) * 10
        if ripple > 100: penalty += (ripple - 100) * 10
        if startup > 50: penalty += (startup - 50) * 10
        return -penalty

    # Reward margins (higher Vout, Iout, Eff; lower Ripple, Startup)
    s += (vout - 3.0) * 25      # Vout margin
    s += (iout - 1.0) * 20      # Iout margin
    s += (eff - 50) * 20 / 50   # Efficiency margin (normalized)
    s += (100 - ripple) / 100 * 20  # Ripple margin
    s += (50 - startup) / 50 * 15   # Startup margin
    return s


def perturb(params, scale=0.15):
    """Randomly perturb parameters in log space."""
    new = {}
    for k, v in params.items():
        lo, hi = BOUNDS[k]
        # Log-space perturbation
        log_v = np.log(v)
        log_lo = np.log(lo)
        log_hi = np.log(hi)
        log_range = log_hi - log_lo
        delta = np.random.normal(0, scale * log_range)
        new_log = np.clip(log_v + delta, log_lo, log_hi)
        new[k] = np.exp(new_log)
    return new


def main():
    template = load_design()
    specs = load_specs()
    n_workers = os.cpu_count() or 8

    # Evaluate baseline
    tmp_dir = tempfile.mkdtemp(prefix="local_opt_")
    _, base_m = run_sim((template, BEST_PARAMS, 0, tmp_dir))
    base_score = score(base_m)
    print(f"Baseline score: {base_score:.3f}")
    if base_m:
        print(f"  Vout={base_m.get('RESULT_VOUT_V',0):.3f}V "
              f"Iout={base_m.get('RESULT_IOUT_MA',0):.3f}mA "
              f"Eff={base_m.get('RESULT_EFFICIENCY_PCT',0):.1f}% "
              f"Ripple={base_m.get('RESULT_RIPPLE_MV',0):.1f}mV")

    best_params = dict(BEST_PARAMS)
    best_score = base_score
    best_measurements = base_m

    n_rounds = 20
    batch_size = n_workers * 2  # 64 candidates per round

    for round_i in range(n_rounds):
        # Generate candidates
        scales = [0.05, 0.10, 0.15, 0.20, 0.30]
        candidates = []
        for _ in range(batch_size):
            s = np.random.choice(scales)
            candidates.append(perturb(best_params, s))

        # Evaluate in parallel
        args = [(template, c, i, tmp_dir) for i, c in enumerate(candidates)]
        results = [None] * batch_size
        with ProcessPoolExecutor(max_workers=n_workers) as pool:
            futures = {pool.submit(run_sim, a): a[2] for a in args}
            for f in as_completed(futures):
                idx, m = f.result()
                results[idx] = (candidates[idx], m)

        # Find best
        improved = False
        for params, m in results:
            if m is None:
                continue
            s = score(m)
            if s > best_score:
                best_score = s
                best_params = params
                best_measurements = m
                improved = True

        vout = best_measurements.get('RESULT_VOUT_V', 0) if best_measurements else 0
        iout = best_measurements.get('RESULT_IOUT_MA', 0) if best_measurements else 0
        eff = best_measurements.get('RESULT_EFFICIENCY_PCT', 0) if best_measurements else 0
        ripple = best_measurements.get('RESULT_RIPPLE_MV', 0) if best_measurements else 0
        mark = " *" if improved else ""
        print(f"Round {round_i+1:2d} | score={best_score:.3f} | "
              f"Vout={vout:.2f}V Iout={iout:.2f}mA Eff={eff:.1f}% Ripple={ripple:.1f}mV{mark}")

    # Save best
    print(f"\nFinal best score: {best_score:.3f}")
    print(f"Best measurements: {json.dumps({k: round(v, 4) for k, v in (best_measurements or {}).items()}, indent=2)}")

    with open(os.path.join(PROJECT_DIR, "best_parameters.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["name", "value"])
        for name, val in sorted(best_params.items()):
            w.writerow([name, val])

    with open(os.path.join(PROJECT_DIR, "measurements.json"), "w") as f:
        json.dump({
            "measurements": best_measurements,
            "score": 1.0 if best_score > 0 else 0.0,
            "details": {},
            "parameters": best_params,
        }, f, indent=2)

    print("\nSaved best_parameters.csv and measurements.json")

    try:
        os.rmdir(tmp_dir)
    except:
        pass


if __name__ == "__main__":
    main()
