"""Fast local optimization around the best known parameters."""
import os, sys, json, csv, subprocess, tempfile, re, time
import numpy as np

NGSPICE = "ngspice"
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

def load_design():
    with open("design.cir") as f:
        return f.read()

def format_netlist(template, params):
    def _replace(m):
        k = m.group(1)
        return str(params[k]) if k in params else m.group(0)
    return re.sub(r'\{(\w+)\}', _replace, template)

def run_sim(template, params):
    netlist = format_netlist(template, params)
    fd, path = tempfile.mkstemp(suffix='.cir', prefix='opt_')
    with os.fdopen(fd, 'w') as f:
        f.write(netlist)
    try:
        r = subprocess.run([NGSPICE, "-b", path],
                          capture_output=True, text=True, timeout=30,
                          cwd=PROJECT_DIR)
        out = r.stdout + r.stderr
    except:
        return None
    finally:
        os.unlink(path)
    
    if "RESULT_DONE" not in out:
        return None
    
    measurements = {}
    for line in out.split("\n"):
        if "RESULT_" in line and "RESULT_DONE" not in line:
            m = re.search(r'(RESULT_\w+)\s+([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)', line)
            if m:
                measurements[m.group(1)] = float(m.group(2))
    return measurements

def score(m):
    if not m:
        return -1e6
    vout = m.get('RESULT_VOUT_V', 0)
    iout = m.get('RESULT_IOUT_MA', 0)
    eff = m.get('RESULT_EFFICIENCY_PCT', 0)
    ripple = m.get('RESULT_RIPPLE_MV', 1e6)
    startup = m.get('RESULT_STARTUP_US', 1e6)

    # Hard penalty if any spec not met
    all_met = (vout > 3.0 and iout > 1.0 and eff > 50 and ripple < 100 and startup < 50)
    if not all_met:
        return -100

    # All specs met - maximize margins
    s = 0
    s += 25 * min((vout - 3.0) / 3.0, 1.0)
    s += 20 * min((iout - 1.0) / 1.0, 1.0)
    s += 20 * min((eff - 50) / 50, 1.0)
    s += 20 * min((100 - ripple) / 100, 1.0)
    s += 15 * min((50 - startup) / 50, 1.0)
    return s

def specs_met(m):
    if not m: return False
    return (m.get('RESULT_VOUT_V',0) > 3.0 and
            m.get('RESULT_IOUT_MA',0) > 1.0 and
            m.get('RESULT_EFFICIENCY_PCT',0) > 50 and
            m.get('RESULT_RIPPLE_MV',1e6) < 100 and
            m.get('RESULT_STARTUP_US',1e6) < 50)

# Best known parameters
best_params = {
    'Cfly1': 120.96, 'Cfly2': 195.90, 'Cmid': 36.86, 'Cout': 121.68,
    'Freq': 48.91, 'Ln1': 0.542, 'Ln2': 0.508, 'Lp1': 0.920, 'Lp2': 0.511,
    'Rload': 3010.0, 'Wn1': 48.79, 'Wn2': 44.63, 'Wp1': 24.36, 'Wp2': 44.64
}

# Parameter ranges
ranges = {
    'Wn1': (10, 100), 'Ln1': (0.5, 5), 'Wp1': (5, 50), 'Lp1': (0.5, 5),
    'Wn2': (10, 100), 'Ln2': (0.5, 5), 'Wp2': (10, 100), 'Lp2': (0.5, 5),
    'Cfly1': (50, 200), 'Cfly2': (50, 200), 'Cmid': (20, 200), 'Cout': (50, 200),
    'Rload': (1500, 3500), 'Freq': (10, 50)
}

template = load_design()

# Evaluate best known
m = run_sim(template, best_params)
best_score = score(m)
print(f"Initial: score={best_score:.2f}, specs_met={specs_met(m)}")
if m:
    for k, v in sorted(m.items()):
        if 'RESULT_' in k and 'DONE' not in k:
            print(f"  {k}: {v:.4f}")

no_improve = 0
iteration = 0
all_met = specs_met(m)

while no_improve < 50:
    iteration += 1
    
    # Random perturbation in log space
    trial = {}
    for k, v in best_params.items():
        lo, hi = ranges[k]
        # Perturb by 5-20% in log space
        scale = np.random.uniform(0.05, 0.3)
        log_v = np.log10(v)
        log_new = log_v + np.random.normal(0, scale)
        new_v = 10**log_new
        trial[k] = np.clip(new_v, lo, hi)
    
    m = run_sim(template, trial)
    s = score(m)
    
    if s > best_score:
        best_score = s
        best_params = trial.copy()
        no_improve = 0
        met = specs_met(m)
        if met: all_met = True
        print(f"[{iteration:>4d}] IMPROVED score={s:.2f} no_imp=0 met={met}")
        if m:
            for k, v in sorted(m.items()):
                if 'RESULT_' in k and 'DONE' not in k:
                    print(f"  {k}: {v:.4f}")
    else:
        no_improve += 1
        if iteration % 20 == 0:
            print(f"[{iteration:>4d}] score={best_score:.2f} no_imp={no_improve}")

print(f"\nDone after {iteration} iterations, no_improve={no_improve}")
print(f"Best score: {best_score:.2f}, all_met: {all_met}")
print("\nBest parameters:")
for k, v in sorted(best_params.items()):
    print(f"  {k}: {v:.6f}")

# Save
with open("best_parameters.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["name", "value"])
    for k, v in sorted(best_params.items()):
        w.writerow([k, v])

