"""
Validation and plot generation for charge pump design.
Runs steady-state check, load regulation, efficiency sweep, and generates all plots.
"""
import os
import csv
import json
import subprocess
import re
import tempfile
import numpy as np

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
PLOTS_DIR = os.path.join(PROJECT_DIR, "plots")
os.makedirs(PLOTS_DIR, exist_ok=True)

# Dark theme
plt.rcParams.update({
    'figure.facecolor': '#1a1a2e', 'axes.facecolor': '#16213e',
    'axes.edgecolor': '#e94560', 'axes.labelcolor': '#eee',
    'text.color': '#eee', 'xtick.color': '#aaa', 'ytick.color': '#aaa',
    'grid.color': '#333', 'grid.alpha': 0.5, 'lines.linewidth': 2,
    'font.size': 11,
})

def load_best_params():
    params = {}
    with open(os.path.join(PROJECT_DIR, "best_parameters.csv")) as f:
        reader = csv.DictReader(f)
        for row in reader:
            params[row["name"]] = float(row["value"])
    return params

def load_design():
    with open(os.path.join(PROJECT_DIR, "design.cir")) as f:
        return f.read()

def format_netlist(template, param_values):
    def _replace(match):
        key = match.group(1)
        if key in param_values:
            return str(param_values[key])
        return match.group(0)
    return re.sub(r'\{(\w+)\}', _replace, template)

def run_ngspice(netlist_str):
    """Run ngspice and return stdout+stderr."""
    tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.cir', delete=False, dir='/tmp')
    tmp.write(netlist_str)
    tmp.close()
    try:
        result = subprocess.run(
            ['ngspice', '-b', tmp.name],
            capture_output=True, text=True, timeout=120,
            cwd=PROJECT_DIR
        )
        return result.stdout + result.stderr
    finally:
        os.unlink(tmp.name)

def extract_results(output):
    """Extract RESULT_ values from ngspice output."""
    results = {}
    for line in output.split('\n'):
        if 'RESULT_' in line and 'RESULT_DONE' not in line:
            match = re.search(r'(RESULT_\w+)\s+([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)', line)
            if match:
                results[match.group(1)] = float(match.group(2))
    return results

def run_rawfile_sim(netlist_str, rawfile_path):
    """Run ngspice with rawfile output for waveform extraction."""
    tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.cir', delete=False, dir='/tmp')
    tmp.write(netlist_str)
    tmp.close()
    try:
        result = subprocess.run(
            ['ngspice', '-b', '-r', rawfile_path, tmp.name],
            capture_output=True, text=True, timeout=120,
            cwd=PROJECT_DIR
        )
        return result.stdout + result.stderr
    finally:
        os.unlink(tmp.name)

def make_waveform_netlist(template, params):
    """Create a netlist that saves raw waveform data."""
    # Replace the .control section with one that writes raw data
    netlist = format_netlist(template, params)
    # Remove existing .control section
    lines = netlist.split('\n')
    new_lines = []
    in_control = False
    for line in lines:
        if line.strip().lower().startswith('.control'):
            in_control = True
            continue
        if line.strip().lower().startswith('.endc'):
            in_control = False
            continue
        if not in_control:
            new_lines.append(line)

    # Remove .end and add tran + save
    final_lines = [l for l in new_lines if l.strip().lower() != '.end']
    final_lines.append('.tran 2n 50u uic')
    final_lines.append('.end')
    return '\n'.join(final_lines)

def read_rawfile(path):
    """Read ngspice binary rawfile."""
    import struct

    with open(path, 'rb') as f:
        content = f.read()

    # Parse header (text until 'Binary:' line)
    header_end = content.find(b'Binary:\n')
    if header_end < 0:
        header_end = content.find(b'Binary:\r\n')
    header = content[:header_end].decode('ascii', errors='replace')
    binary_start = header_end + len(b'Binary:\n')
    if b'Binary:\r\n' in content[:header_end+20]:
        binary_start = header_end + len(b'Binary:\r\n')

    # Parse header for variable names and number of points
    var_names = []
    n_vars = 0
    n_points = 0
    in_vars = False
    for line in header.split('\n'):
        line = line.strip()
        if line.startswith('No. Variables:'):
            n_vars = int(line.split(':')[1].strip())
        elif line.startswith('No. Points:'):
            n_points = int(line.split(':')[1].strip())
        elif line.startswith('Variables:'):
            in_vars = True
        elif in_vars and line and line[0].isdigit():
            parts = line.split()
            if len(parts) >= 2:
                var_names.append(parts[1])
        elif in_vars and not line:
            in_vars = False

    # Read binary data (double precision)
    binary_data = content[binary_start:]
    expected = n_vars * n_points
    values = struct.unpack(f'<{expected}d', binary_data[:expected*8])

    data = {}
    for i, name in enumerate(var_names):
        data[name] = np.array([values[j*n_vars + i] for j in range(n_points)])

    return data

def main():
    params = load_best_params()
    template = load_design()

    print("=" * 60)
    print("CHARGE PUMP VALIDATION")
    print("=" * 60)

    # 1. Steady-state verification
    print("\n1. Steady-state verification...")
    netlist = format_netlist(template, params)
    output = run_ngspice(netlist)
    results = extract_results(output)
    print(f"   Vout = {results.get('RESULT_VOUT_V', 'N/A'):.3f} V")
    print(f"   Ripple = {results.get('RESULT_RIPPLE_MV', 'N/A'):.2f} mV")
    print(f"   Iout = {results.get('RESULT_IOUT_MA', 'N/A'):.3f} mA")
    print(f"   Efficiency = {results.get('RESULT_EFFICIENCY_PCT', 'N/A'):.1f} %")
    print(f"   Startup = {results.get('RESULT_STARTUP_US', 'N/A'):.3f} us")

    # 2. Generate waveform data for startup and ripple plots
    print("\n2. Generating waveform plots...")
    wave_netlist = make_waveform_netlist(template, params)
    rawfile = '/tmp/cp_waveform.raw'
    run_rawfile_sim(wave_netlist, rawfile)

    try:
        data = read_rawfile(rawfile)
        time_arr = data.get('time', data.get('v-sweep', None))
        vout_arr = data.get('v(vout)', data.get('vout', None))

        if time_arr is not None and vout_arr is not None:
            # Startup plot
            fig, ax = plt.subplots(figsize=(10, 5))
            t_us = time_arr * 1e6
            ax.plot(t_us, vout_arr, color='#e94560', linewidth=1.5)
            ax.set_xlabel('Time (us)')
            ax.set_ylabel('Vout (V)')
            ax.set_title('Charge Pump Startup')

            # Annotate 90% point
            vout_final = results.get('RESULT_VOUT_V', vout_arr[-1])
            v90 = vout_final * 0.9
            startup_us = results.get('RESULT_STARTUP_US', 0)
            ax.axhline(y=v90, color='#0f3460', linestyle='--', alpha=0.7, label=f'90% = {v90:.2f}V')
            ax.axhline(y=vout_final, color='#533483', linestyle='--', alpha=0.7, label=f'Final = {vout_final:.2f}V')
            ax.annotate(f'Startup: {startup_us:.2f} us', xy=(startup_us, v90),
                       fontsize=12, color='#e94560',
                       arrowprops=dict(arrowstyle='->', color='#e94560'),
                       xytext=(startup_us + 5, v90 - 0.5))
            ax.legend()
            ax.grid(True)
            plt.tight_layout()
            plt.savefig(os.path.join(PLOTS_DIR, 'startup.png'), dpi=150)
            plt.close()
            print("   startup.png saved")

            # Ripple plot - zoom into last 5us
            fig, ax = plt.subplots(figsize=(10, 5))
            mask = t_us >= 20
            ax.plot(t_us[mask], vout_arr[mask], color='#e94560', linewidth=1)
            ripple_mv = results.get('RESULT_RIPPLE_MV', 0)
            vmax_ss = np.max(vout_arr[mask])
            vmin_ss = np.min(vout_arr[mask])
            ax.axhline(y=vmax_ss, color='#0f3460', linestyle=':', alpha=0.5)
            ax.axhline(y=vmin_ss, color='#0f3460', linestyle=':', alpha=0.5)
            ax.annotate(f'Ripple: {ripple_mv:.1f} mV p-p',
                       xy=(22, (vmax_ss + vmin_ss)/2), fontsize=13, color='#e94560',
                       bbox=dict(boxstyle='round,pad=0.3', facecolor='#16213e', edgecolor='#e94560'))
            ax.set_xlabel('Time (us)')
            ax.set_ylabel('Vout (V)')
            ax.set_title('Output Ripple (Steady State)')
            ax.grid(True)
            plt.tight_layout()
            plt.savefig(os.path.join(PLOTS_DIR, 'ripple.png'), dpi=150)
            plt.close()
            print("   ripple.png saved")
    except Exception as e:
        print(f"   Waveform plots failed: {e}")
        # Fallback: create simple placeholder plots
        for name in ['startup.png', 'ripple.png']:
            fig, ax = plt.subplots(figsize=(10, 5))
            ax.text(0.5, 0.5, f'Plot generation failed\n{e}', transform=ax.transAxes,
                   ha='center', va='center', fontsize=14)
            plt.savefig(os.path.join(PLOTS_DIR, name), dpi=150)
            plt.close()

    # 3. Load regulation sweep (Vout vs Iload)
    print("\n3. Load regulation sweep...")
    rload_values = [10000, 7000, 5000, 4000, 3500, 3000, 2500, 2000, 1500, 1200, 1000, 800]
    vouts = []
    iouts = []
    effs = []

    for rload in rload_values:
        p = dict(params)
        p['Rload'] = rload
        nl = format_netlist(template, p)
        out = run_ngspice(nl)
        r = extract_results(out)
        vout = r.get('RESULT_VOUT_V', 0)
        iout = vout / rload * 1000  # mA
        eff = r.get('RESULT_EFFICIENCY_PCT', 0)
        vouts.append(vout)
        iouts.append(iout)
        effs.append(eff)
        print(f"   Rload={rload:5d}  Vout={vout:.3f}V  Iout={iout:.3f}mA  Eff={eff:.1f}%")

    # Vout vs Iload plot
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(iouts, vouts, 'o-', color='#e94560', markersize=6)
    ax.axhline(y=3.0, color='#0f3460', linestyle='--', alpha=0.7, label='Spec: Vout > 3.0V')
    ax.axvline(x=1.0, color='#533483', linestyle='--', alpha=0.7, label='Spec: Iout > 1mA')

    # Find max current at Vout > 3V
    max_i_at_3v = 0
    for i, v in zip(iouts, vouts):
        if v > 3.0:
            max_i_at_3v = max(max_i_at_3v, i)

    ax.annotate(f'Max Iout @ Vout>3V: {max_i_at_3v:.2f} mA',
               xy=(max_i_at_3v, 3.0), fontsize=12, color='#e94560',
               bbox=dict(boxstyle='round,pad=0.3', facecolor='#16213e', edgecolor='#e94560'),
               xytext=(max_i_at_3v - 0.5, 2.5),
               arrowprops=dict(arrowstyle='->', color='#e94560'))
    ax.set_xlabel('Load Current (mA)')
    ax.set_ylabel('Output Voltage (V)')
    ax.set_title('Load Regulation: Vout vs Iload')
    ax.legend()
    ax.grid(True)
    plt.tight_layout()
    plt.savefig(os.path.join(PLOTS_DIR, 'vout_vs_iload.png'), dpi=150)
    plt.close()
    print("   vout_vs_iload.png saved")

    # Efficiency vs Iload plot
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(iouts, effs, 'o-', color='#e94560', markersize=6)
    ax.axhline(y=50, color='#0f3460', linestyle='--', alpha=0.7, label='Spec: Eff > 50%')
    ax.set_xlabel('Load Current (mA)')
    ax.set_ylabel('Efficiency (%)')
    ax.set_title('Efficiency vs Load Current')

    # Annotate peak efficiency
    peak_eff = max(effs)
    peak_idx = effs.index(peak_eff)
    ax.annotate(f'Peak: {peak_eff:.1f}% @ {iouts[peak_idx]:.2f}mA',
               xy=(iouts[peak_idx], peak_eff), fontsize=12, color='#e94560',
               bbox=dict(boxstyle='round,pad=0.3', facecolor='#16213e', edgecolor='#e94560'))
    ax.legend()
    ax.grid(True)
    plt.tight_layout()
    plt.savefig(os.path.join(PLOTS_DIR, 'efficiency.png'), dpi=150)
    plt.close()
    print("   efficiency.png saved")

    # 4. Progress plot
    print("\n4. Generating progress plot...")
    results_file = os.path.join(PROJECT_DIR, "results.tsv")
    if os.path.exists(results_file):
        steps, scores = [], []
        with open(results_file) as f:
            reader = csv.DictReader(f, delimiter='\t')
            for row in reader:
                try:
                    steps.append(int(row.get("step", len(steps)+1)))
                    scores.append(float(row.get("score", 0)))
                except (ValueError, TypeError):
                    continue

        if scores:
            best_so_far = []
            best = -1
            for s in scores:
                best = max(best, s)
                best_so_far.append(best)

            fig, ax = plt.subplots(figsize=(10, 5))
            ax.plot(steps, scores, 'o', color='#0f3460', markersize=6, alpha=0.7, label='Run score')
            ax.plot(steps, best_so_far, '-', color='#e94560', linewidth=2, label='Best so far')
            ax.set_xlabel('Iteration')
            ax.set_ylabel('Score')
            ax.set_title('Optimization Progress')
            ax.legend()
            ax.grid(True)
            ax.set_ylim(0, 1.1)
            plt.tight_layout()
            plt.savefig(os.path.join(PLOTS_DIR, 'progress.png'), dpi=150)
            plt.close()
            print("   progress.png saved")

    # Summary
    print(f"\n{'='*60}")
    print(f"VALIDATION SUMMARY")
    print(f"{'='*60}")
    vout = results.get('RESULT_VOUT_V', 0)
    iout = results.get('RESULT_IOUT_MA', 0)
    eff = results.get('RESULT_EFFICIENCY_PCT', 0)
    ripple = results.get('RESULT_RIPPLE_MV', 0)
    startup = results.get('RESULT_STARTUP_US', 0)

    specs = [
        ('Vout (V)', vout, '>3.0', vout >= 3.0),
        ('Iout (mA)', iout, '>1.0', iout >= 1.0),
        ('Efficiency (%)', eff, '>50', eff >= 50),
        ('Ripple (mV)', ripple, '<100', ripple <= 100),
        ('Startup (us)', startup, '<50', startup <= 50),
    ]

    all_pass = True
    for name, val, target, met in specs:
        status = "PASS" if met else "FAIL"
        if not met: all_pass = False
        print(f"  {name:<20} {val:>10.3f}  {target:>8}  [{status}]")

    print(f"\n  Max Iout @ Vout>3V: {max_i_at_3v:.2f} mA")
    print(f"  All specs: {'PASS' if all_pass else 'FAIL'}")
    print(f"{'='*60}")

    return all_pass, results

if __name__ == "__main__":
    passed, results = main()
