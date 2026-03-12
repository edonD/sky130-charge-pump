"""
Local optimization around known-good parameters.
Seeds population with previous best and explores nearby.
"""
import os
import sys
import csv
import json
import tempfile
import subprocess
import re
import time
import numpy as np
from concurrent.futures import ProcessPoolExecutor, as_completed

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
NGSPICE = "ngspice"

def load_best_params(path="best_parameters.csv"):
    params = {}
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            params[row["name"]] = float(row["value"])
    return params

def load_param_ranges(path="parameters.csv"):
    ranges = {}
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            ranges[row["name"].strip()] = {
                "min": float(row["min"]),
                "max": float(row["max"]),
                "scale": row.get("scale", "lin").strip(),
            }
    return ranges

def load_design(path="design.cir"):
    with open(path) as f:
        return f.read()

def load_specs(path="specs.json"):
    with open(path) as f:
        return json.load(f)

def format_netlist(template, param_values):
    def _replace(match):
        key = match.group(1)
        if key in param_values:
            return str(param_values[key])
        return match.group(0)
    return re.sub(r'\{(\w+)\}', _replace, template)

def run_sim(args):
    template, param_values, idx, tmp_dir = args
    netlist = format_netlist(template, param_values)
    path = os.path.join(tmp_dir, f"sim_{idx}.cir")
    with open(path, "w") as f:
        f.write(netlist)
    try:
        result = subprocess.run(
            [NGSPICE, "-b", path],
            capture_output=True, text=True, timeout=60,
            cwd=PROJECT_DIR
        )
        output = result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return idx, None
    except Exception:
        return idx, None
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass

    if "RESULT_DONE" not in output:
        return idx, None

    measurements = {}
    for line in output.split("\n"):
        if "RESULT_" in line and "RESULT_DONE" not in line:
            match = re.search(r'(RESULT_\w+)\s+([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)', line)
            if match:
                measurements[match.group(1)] = float(match.group(2))
    return idx, measurements

def score(measurements, specs):
    if not measurements:
        return -1e6  # maximize score

    total_w = 0
    weighted = 0
    details = {}
    for name, spec in specs["measurements"].items():
        target = spec["target"].strip()
        weight = spec["weight"]
        total_w += weight
        key = f"RESULT_{name.upper()}"
        val = measurements.get(key)
        if val is None:
            details[name] = {"val": None, "met": False}
            continue

        if target.startswith(">"):
            threshold = float(target[1:])
            met = val >= threshold
            s = 1.0 if met else max(0, val / threshold)
        elif target.startswith("<"):
            threshold = float(target[1:])
            met = val <= threshold
            s = 1.0 if met else max(0, threshold / val) if val > 0 else 0
        else:
            met = False
            s = 0

        weighted += weight * s
        details[name] = {"val": val, "met": met, "score": s}

    overall = weighted / total_w if total_w > 0 else 0
    return overall, details

def perturb(base_params, ranges, scale=0.15, n=30):
    """Generate n perturbed versions of base_params."""
    candidates = [dict(base_params)]  # always include the base
    for _ in range(n - 1):
        p = {}
        for name, val in base_params.items():
            r = ranges[name]
            lo, hi = r["min"], r["max"]
            if r["scale"] == "log":
                log_val = np.log10(val)
                log_lo, log_hi = np.log10(lo), np.log10(hi)
                log_range = log_hi - log_lo
                new_log = log_val + np.random.normal(0, scale * log_range)
                new_log = np.clip(new_log, log_lo, log_hi)
                p[name] = 10 ** new_log
            else:
                lin_range = hi - lo
                new_val = val + np.random.normal(0, scale * lin_range)
                p[name] = np.clip(new_val, lo, hi)
        candidates.append(p)
    return candidates

def main():
    best_params = load_best_params()
    ranges = load_param_ranges()
    template = load_design()
    specs = load_specs()

    print("Starting local optimization around known-good parameters")
    print(f"Base params: {best_params}")

    tmp_dir = tempfile.mkdtemp(prefix="local_opt_")
    n_workers = 8
    n_iters = 15
    pop_size = 40
    current_best = dict(best_params)
    best_score = -1
    best_details = None

    for iteration in range(n_iters):
        scale = 0.2 * (0.85 ** iteration)  # shrink perturbation over time
        candidates = perturb(current_best, ranges, scale=scale, n=pop_size)

        # Evaluate in parallel
        args_list = [(template, c, i, tmp_dir) for i, c in enumerate(candidates)]
        results = [None] * len(candidates)

        with ProcessPoolExecutor(max_workers=n_workers) as pool:
            futures = {pool.submit(run_sim, a): a[2] for a in args_list}
            for future in as_completed(futures):
                idx, meas = future.result()
                results[idx] = meas

        # Score all
        scores = []
        for i, meas in enumerate(results):
            if meas is None:
                scores.append((-1e6, None))
            else:
                s, d = score(meas, specs)
                scores.append((s, d))

        # Find best
        best_idx = max(range(len(scores)), key=lambda i: scores[i][0])
        iter_score, iter_details = scores[best_idx]

        if iter_score > best_score:
            best_score = iter_score
            best_details = iter_details
            current_best = dict(candidates[best_idx])
            improved = " *IMPROVED*"
        else:
            improved = ""

        n_valid = sum(1 for s, _ in scores if s > -1e6)
        print(f"Iter {iteration+1:2d} | scale={scale:.3f} | valid={n_valid}/{pop_size} | "
              f"best_this={iter_score:.4f} | best_overall={best_score:.4f}{improved}")

    # Print final results
    print(f"\n{'='*60}")
    print(f"Final score: {best_score:.4f}")
    print(f"\nBest parameters:")
    for name, val in sorted(current_best.items()):
        print(f"  {name:<15} = {val:.4f}")

    if best_details:
        print(f"\nSpec details:")
        for name, d in best_details.items():
            status = "PASS" if d.get("met") else "FAIL"
            val = d.get("val", "N/A")
            print(f"  {name:<20} = {val}  [{status}]")

    # Save best parameters
    with open("best_parameters.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["name", "value"])
        for name, val in sorted(current_best.items()):
            w.writerow([name, val])

    # Save measurements
    # Run one final sim to get exact measurements
    final_meas = run_sim((template, current_best, 0, tmp_dir))[1]
    if final_meas:
        s, d = score(final_meas, specs)
        with open("measurements.json", "w") as f:
            json.dump({
                "measurements": final_meas,
                "score": s,
                "details": {k: {"measured": v.get("val"), "met": v.get("met"),
                                "score": v.get("score", 0)} for k, v in d.items()},
                "parameters": current_best,
            }, f, indent=2)

    try:
        os.rmdir(tmp_dir)
    except OSError:
        pass

    return best_score

if __name__ == "__main__":
    main()
