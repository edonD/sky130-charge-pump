"""
Validation script: generates all required plots from best parameters.
Runs steady-state, ripple, load sweep, and efficiency measurements.
"""
import os, re, subprocess, json, csv, tempfile
import numpy as np

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
NGSPICE = os.environ.get("NGSPICE", "ngspice")

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

def run_ngspice(netlist_str, label="sim"):
    tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.cir', delete=False, dir=PROJECT_DIR)
    tmp.write(netlist_str)
    tmp.close()
    try:
        result = subprocess.run(
            [NGSPICE, "-b", tmp.name],
            capture_output=True, text=True, timeout=120,
            cwd=PROJECT_DIR
        )
        return result.stdout + result.stderr
    finally:
        os.unlink(tmp.name)

def main():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    params = load_best_params()
    template = load_design()
    os.makedirs("plots", exist_ok=True)

    # Dark theme
    plt.rcParams.update({
        'figure.facecolor': '#1a1a2e', 'axes.facecolor': '#16213e',
        'axes.edgecolor': '#e94560', 'axes.labelcolor': '#eee',
        'text.color': '#eee', 'xtick.color': '#aaa', 'ytick.color': '#aaa',
        'grid.color': '#333', 'grid.alpha': 0.5, 'lines.linewidth': 2,
    })

    # ========================
    # 1. Startup plot - run long transient, save raw data
    # ========================
    print("Running startup simulation...")
    startup_cir = format_netlist(template, params)
    # Replace .control section with data export
    startup_cir = re.sub(
        r'\.control.*?\.endc',
        """.control
tran 2n 25u uic
wrdata plots/startup_data.txt v(vout)
meas tran vout_avg avg v(vout) from=20u to=25u
meas tran vout_max max v(vout) from=20u to=25u
meas tran vout_min min v(vout) from=20u to=25u
let ripple = (vout_max - vout_min) * 1000
echo "RESULT_VOUT_V" $&vout_avg
echo "RESULT_RIPPLE_MV" $&ripple
let target90 = vout_avg * 0.9
meas tran startup_t when v(vout)=target90 rise=1
let startup_us = startup_t * 1e6
echo "RESULT_STARTUP_US" $&startup_us
echo "RESULT_DONE"
.endc""",
        startup_cir, flags=re.DOTALL
    )
    output = run_ngspice(startup_cir, "startup")

    # Parse startup data
    data_file = os.path.join(PROJECT_DIR, "plots/startup_data.txt")
    if os.path.exists(data_file):
        t_data, v_data = [], []
        with open(data_file) as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) >= 2:
                    try:
                        t_data.append(float(parts[0]))
                        v_data.append(float(parts[1]))
                    except:
                        pass
        t_data = np.array(t_data)
        v_data = np.array(v_data)

        if len(t_data) > 0:
            # Startup plot
            fig, ax = plt.subplots(figsize=(12, 5))
            ax.plot(t_data * 1e6, v_data, color='#e94560', linewidth=1.5)
            vout_final = np.mean(v_data[-100:]) if len(v_data) > 100 else v_data[-1]
            target90 = vout_final * 0.9
            ax.axhline(y=target90, color='#0f3460', linestyle='--', alpha=0.7, label=f'90% = {target90:.2f}V')
            ax.axhline(y=vout_final, color='#533483', linestyle='--', alpha=0.7, label=f'Final = {vout_final:.2f}V')
            # Find startup time
            idx90 = np.argmax(v_data >= target90) if np.any(v_data >= target90) else -1
            if idx90 > 0:
                t_startup = t_data[idx90] * 1e6
                ax.axvline(x=t_startup, color='yellow', linestyle=':', alpha=0.5)
                ax.annotate(f'Startup: {t_startup:.2f}us', xy=(t_startup, target90),
                           fontsize=12, color='yellow', ha='left')
            ax.set_xlabel('Time (us)')
            ax.set_ylabel('Vout (V)')
            ax.set_title('Charge Pump Startup')
            ax.legend()
            ax.grid(True)
            plt.tight_layout()
            plt.savefig('plots/startup.png', dpi=150)
            plt.close()
            print(f"  Startup plot saved. Vout_final={vout_final:.3f}V")

            # Ripple plot - zoom on last 2us
            mask = t_data >= 23e-6
            if np.any(mask):
                fig, ax = plt.subplots(figsize=(12, 5))
                ax.plot(t_data[mask] * 1e6, v_data[mask] * 1000, color='#e94560', linewidth=1)
                vmax = np.max(v_data[mask]) * 1000
                vmin = np.min(v_data[mask]) * 1000
                ripple_mv = vmax - vmin
                ax.axhline(y=vmax, color='#0f3460', linestyle='--', alpha=0.7)
                ax.axhline(y=vmin, color='#0f3460', linestyle='--', alpha=0.7)
                ax.annotate(f'Ripple: {ripple_mv:.1f}mV', xy=(23.5, (vmax+vmin)/2),
                           fontsize=14, color='yellow', ha='left',
                           bbox=dict(boxstyle='round', facecolor='#1a1a2e', alpha=0.8))
                ax.set_xlabel('Time (us)')
                ax.set_ylabel('Vout (mV)')
                ax.set_title('Output Ripple (Steady State)')
                ax.grid(True)
                plt.tight_layout()
                plt.savefig('plots/ripple.png', dpi=150)
                plt.close()
                print(f"  Ripple plot saved. Ripple={ripple_mv:.1f}mV")

        os.unlink(data_file)

    # ========================
    # 2. Load sweep - vary Rload, measure Vout and efficiency
    # ========================
    print("Running load sweep...")
    rloads = np.logspace(np.log10(500), np.log10(10000), 20)
    vouts, iouts, effs = [], [], []

    for rl in rloads:
        p = dict(params)
        p["Rload"] = rl
        cir = format_netlist(template, p)
        out = run_ngspice(cir, f"load_{rl:.0f}")

        vout = eff = None
        for line in out.split("\n"):
            if "RESULT_VOUT_V" in line:
                m = re.search(r'RESULT_VOUT_V\s+([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)', line)
                if m: vout = float(m.group(1))
            if "RESULT_EFFICIENCY_PCT" in line:
                m = re.search(r'RESULT_EFFICIENCY_PCT\s+([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)', line)
                if m: eff = float(m.group(1))

        if vout and vout > 0:
            iout = vout / rl * 1000  # mA
            vouts.append(vout)
            iouts.append(iout)
            effs.append(eff if eff else 0)
            print(f"  Rload={rl:.0f} -> Vout={vout:.3f}V Iout={iout:.2f}mA Eff={eff:.1f}%")

    if vouts:
        iouts = np.array(iouts)
        vouts = np.array(vouts)
        effs = np.array(effs)

        # Find max Iout at Vout > 3.0V
        valid = vouts > 3.0
        max_iout_at_3v = np.max(iouts[valid]) if np.any(valid) else 0

        # Vout vs Iload
        fig, ax = plt.subplots(figsize=(12, 5))
        ax.plot(iouts, vouts, 'o-', color='#e94560', markersize=5)
        ax.axhline(y=3.0, color='#0f3460', linestyle='--', alpha=0.7, label='3.0V spec')
        ax.annotate(f'Max Iout @ Vout>3V: {max_iout_at_3v:.2f}mA',
                   xy=(max_iout_at_3v, 3.0), fontsize=12, color='yellow',
                   bbox=dict(boxstyle='round', facecolor='#1a1a2e', alpha=0.8))
        ax.set_xlabel('Load Current (mA)')
        ax.set_ylabel('Output Voltage (V)')
        ax.set_title('Load Regulation')
        ax.legend()
        ax.grid(True)
        plt.tight_layout()
        plt.savefig('plots/vout_vs_iload.png', dpi=150)
        plt.close()
        print(f"  Vout vs Iload plot saved. MaxIout@3V={max_iout_at_3v:.2f}mA")

        # Efficiency vs Iload
        fig, ax = plt.subplots(figsize=(12, 5))
        ax.plot(iouts, effs, 'o-', color='#e94560', markersize=5)
        ax.axhline(y=50, color='#0f3460', linestyle='--', alpha=0.7, label='50% spec')
        ax.set_xlabel('Load Current (mA)')
        ax.set_ylabel('Efficiency (%)')
        ax.set_title('Efficiency vs Load Current')
        ax.legend()
        ax.grid(True)
        plt.tight_layout()
        plt.savefig('plots/efficiency.png', dpi=150)
        plt.close()
        print(f"  Efficiency plot saved.")

        return max_iout_at_3v

    return 0


if __name__ == "__main__":
    max_iout = main()
    print(f"\nValidation complete. MaxIout@3V={max_iout:.2f}mA")
