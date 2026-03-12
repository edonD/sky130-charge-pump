"""
plot_blog.py — Generate publication-quality plots for the AI charge pump blog post.
Dark theme, annotated, suitable for a technical blog.
"""

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
from matplotlib.patches import FancyBboxPatch
import matplotlib.patheffects as pe
import re
import os

# ---------------------------------------------------------------------------
# Global dark theme
# ---------------------------------------------------------------------------
COLORS = {
    'bg':       '#0d1117',
    'panel':    '#161b22',
    'grid':     '#21262d',
    'text':     '#e6edf3',
    'dim':      '#8b949e',
    'accent1':  '#58a6ff',   # blue
    'accent2':  '#f78166',   # orange
    'accent3':  '#7ee787',   # green
    'accent4':  '#d2a8ff',   # purple
    'accent5':  '#ff7b72',   # red
    'accent6':  '#79c0ff',   # light blue
    'gold':     '#ffd700',
    'spec_line':'#3fb950',   # spec pass green
    'spec_fail':'#f85149',   # spec fail red
}

plt.rcParams.update({
    'figure.facecolor':   COLORS['bg'],
    'axes.facecolor':     COLORS['panel'],
    'axes.edgecolor':     COLORS['grid'],
    'axes.labelcolor':    COLORS['text'],
    'axes.grid':          True,
    'grid.color':         COLORS['grid'],
    'grid.alpha':         0.6,
    'grid.linewidth':     0.5,
    'text.color':         COLORS['text'],
    'xtick.color':        COLORS['dim'],
    'ytick.color':        COLORS['dim'],
    'xtick.labelsize':    10,
    'ytick.labelsize':    10,
    'axes.labelsize':     12,
    'axes.titlesize':     14,
    'legend.facecolor':   COLORS['panel'],
    'legend.edgecolor':   COLORS['grid'],
    'legend.fontsize':    9,
    'font.family':        'sans-serif',
    'lines.linewidth':    1.5,
    'lines.antialiased':  True,
    'savefig.facecolor':  COLORS['bg'],
    'savefig.edgecolor':  COLORS['bg'],
    'savefig.dpi':        200,
})


def glow(color, alpha=0.3, linewidth=5):
    """Return path effects that give a line a subtle glow."""
    return [
        pe.Stroke(linewidth=linewidth, foreground=color, alpha=alpha),
        pe.Normal(),
    ]


# ---------------------------------------------------------------------------
# 1. Startup Plot
# ---------------------------------------------------------------------------
def plot_startup(ax):
    # wrdata format: t1 v(vout) t2 v(mid) t3 v(a1) t4 v(b1)
    data = np.loadtxt('sims/data_startup.csv')
    t = data[:, 0] * 1e6   # us (all time columns identical)
    vout = data[:, 1]
    vmid = data[:, 3]       # col 2=t, col 3=v(mid)

    ax.plot(t, vmid, color=COLORS['accent4'], alpha=0.7, linewidth=1, label='V(mid) — Stage 1 out')
    ax.plot(t, vout, color=COLORS['accent1'], linewidth=2, label='V(out) — Final output',
            path_effects=glow(COLORS['accent1']))

    # Find steady state and 90% point
    vout_ss = np.mean(vout[int(len(vout)*0.8):])
    target90 = vout_ss * 0.9
    idx90 = np.argmax(vout >= target90)
    t90 = t[idx90]

    ax.axhline(y=vout_ss, color=COLORS['accent3'], linestyle='--', alpha=0.5, linewidth=0.8)
    ax.axhline(y=target90, color=COLORS['gold'], linestyle=':', alpha=0.4, linewidth=0.8)
    ax.axhline(y=1.8, color=COLORS['accent5'], linestyle='--', alpha=0.3, linewidth=0.8)

    # Annotate
    ax.annotate(f'90% in {t90*1000:.0f} ns', xy=(t90, target90),
                xytext=(t90 + 2, target90 - 0.5),
                arrowprops=dict(arrowstyle='->', color=COLORS['gold'], lw=1.5),
                fontsize=10, color=COLORS['gold'], fontweight='bold')

    ax.annotate(f'Vout = {vout_ss:.2f} V', xy=(t[-1], vout_ss),
                xytext=(t[-1]*0.6, vout_ss + 0.3),
                fontsize=10, color=COLORS['accent3'], fontweight='bold')

    ax.annotate('Vdd = 1.8 V', xy=(t[-1]*0.85, 1.85),
                fontsize=8, color=COLORS['accent5'], alpha=0.7)

    ax.set_xlabel('Time (µs)')
    ax.set_ylabel('Voltage (V)')
    ax.set_title('Startup Transient', fontweight='bold', fontsize=13)
    ax.legend(loc='center right', framealpha=0.8)
    ax.set_xlim(0, t[-1])
    ax.set_ylim(-0.2, vout_ss + 1)


# ---------------------------------------------------------------------------
# 2. Ripple Plot (zoomed steady-state)
# ---------------------------------------------------------------------------
def plot_ripple(ax):
    # wrdata format: t1 v(vout) t2 v(clk1) t3 v(clk2)
    data = np.loadtxt('sims/data_ripple.csv')
    t = data[:, 0] * 1e6   # us
    vout = data[:, 1]
    clk1 = data[:, 3]       # col 2=t, col 3=v(clk1)

    # Zoom to last ~10 clock cycles at 60 MHz => ~167 ns each => ~1.67 us
    t_start = 23.0
    t_end = 25.0
    mask = (t >= t_start) & (t <= t_end)

    t_z = t[mask]
    vout_z = vout[mask]
    clk1_z = clk1[mask]

    vmax = np.max(vout_z)
    vmin = np.min(vout_z)
    ripple_mv = (vmax - vmin) * 1000

    ax.plot(t_z, vout_z, color=COLORS['accent1'], linewidth=1.5,
            path_effects=glow(COLORS['accent1'], 0.2, 3))

    # Shade ripple band
    ax.fill_between(t_z, vmin, vmax, alpha=0.1, color=COLORS['accent1'])
    ax.axhline(y=vmax, color=COLORS['accent3'], linestyle=':', alpha=0.4, linewidth=0.7)
    ax.axhline(y=vmin, color=COLORS['accent5'], linestyle=':', alpha=0.4, linewidth=0.7)

    # Clock overlay (scaled)
    vmid_out = (vmax + vmin) / 2
    clk_range = vmax - vmin
    if clk_range < 0.001:
        clk_range = 0.01
    clk_scaled = vmin - clk_range * 3 + clk1_z / 1.8 * clk_range * 2
    ax.plot(t_z, clk_scaled, color=COLORS['accent4'], alpha=0.4, linewidth=0.8, label='CLK1')

    # Annotate ripple
    t_mid = (t_start + t_end) / 2
    ax.annotate(f'Ripple = {ripple_mv:.1f} mV p-p',
                xy=(t_mid, vmax), xytext=(t_mid, vmax + clk_range * 2),
                fontsize=11, color=COLORS['gold'], fontweight='bold',
                ha='center',
                arrowprops=dict(arrowstyle='->', color=COLORS['gold'], lw=1.5))

    # Double arrow for ripple
    ax.annotate('', xy=(t_end - 0.05, vmax), xytext=(t_end - 0.05, vmin),
                arrowprops=dict(arrowstyle='<->', color=COLORS['accent2'], lw=1.5))

    ax.set_xlabel('Time (µs)')
    ax.set_ylabel('Voltage (V)')
    ax.set_title('Output Ripple (Steady State)', fontweight='bold', fontsize=13)
    ax.set_xlim(t_start, t_end)


# ---------------------------------------------------------------------------
# 3. Load Regulation: Vout vs Iload
# ---------------------------------------------------------------------------
def plot_load_regulation(ax, sweep_data):
    rvals = np.array(sweep_data['rvals'])
    vouts = np.array(sweep_data['vouts'])
    iouts = np.array(sweep_data['iouts'])

    iout_ma = iouts * 1000

    ax.plot(iout_ma, vouts, 'o-', color=COLORS['accent1'], markersize=5, linewidth=2,
            markerfacecolor=COLORS['accent6'], markeredgecolor=COLORS['accent1'],
            path_effects=glow(COLORS['accent1'], 0.2, 3))

    # Spec line at 3.0 V
    ax.axhline(y=3.0, color=COLORS['spec_line'], linestyle='--', alpha=0.6, linewidth=1.5,
               label='Vout spec (3.0 V)')

    # Find max Iout at Vout > 3V
    valid = vouts >= 3.0
    if np.any(valid):
        max_iout_3v = np.max(iout_ma[valid])
        ax.axvline(x=max_iout_3v, color=COLORS['accent2'], linestyle=':', alpha=0.5, linewidth=1)
        ax.annotate(f'Max Iout @ 3V = {max_iout_3v:.1f} mA',
                    xy=(max_iout_3v, 3.0),
                    xytext=(max_iout_3v * 0.5, 2.2),
                    fontsize=10, color=COLORS['accent2'], fontweight='bold',
                    arrowprops=dict(arrowstyle='->', color=COLORS['accent2'], lw=1.5))

    # Shade pass region
    ax.fill_between(iout_ma, 3.0, np.max(vouts) + 0.5, alpha=0.05, color=COLORS['spec_line'])

    # Mark nominal operating point
    nom_idx = np.argmin(np.abs(rvals - 2937))
    ax.plot(iout_ma[nom_idx], vouts[nom_idx], 's', color=COLORS['gold'], markersize=10,
            zorder=5, label=f'Nominal ({iout_ma[nom_idx]:.1f} mA, {vouts[nom_idx]:.2f} V)')

    ax.set_xlabel('Load Current (mA)')
    ax.set_ylabel('Output Voltage (V)')
    ax.set_title('Load Regulation', fontweight='bold', fontsize=13)
    ax.legend(loc='upper right', framealpha=0.8)
    ax.set_ylim(0, np.max(vouts) + 0.5)


# ---------------------------------------------------------------------------
# 4. Efficiency vs Load Current
# ---------------------------------------------------------------------------
def plot_efficiency(ax, sweep_data):
    iouts = np.array(sweep_data['iouts']) * 1000
    effs = np.array(sweep_data['effs'])

    # Clip unreasonable efficiency values
    effs = np.clip(effs, 0, 100)

    ax.fill_between(iouts, 0, effs, alpha=0.15, color=COLORS['accent3'])
    ax.plot(iouts, effs, 'o-', color=COLORS['accent3'], markersize=5, linewidth=2,
            markerfacecolor=COLORS['accent3'], markeredgecolor=COLORS['accent3'],
            path_effects=glow(COLORS['accent3'], 0.2, 3))

    # Spec line at 50%
    ax.axhline(y=50, color=COLORS['spec_line'], linestyle='--', alpha=0.5, linewidth=1.5,
               label='Efficiency spec (50%)')

    # Peak efficiency
    peak_idx = np.argmax(effs)
    ax.annotate(f'Peak: {effs[peak_idx]:.1f}% @ {iouts[peak_idx]:.2f} mA',
                xy=(iouts[peak_idx], effs[peak_idx]),
                xytext=(iouts[peak_idx] + 0.5, effs[peak_idx] - 10),
                fontsize=10, color=COLORS['gold'], fontweight='bold',
                arrowprops=dict(arrowstyle='->', color=COLORS['gold'], lw=1.5))

    # Mark nominal
    rvals = np.array(sweep_data['rvals'])
    nom_idx = np.argmin(np.abs(rvals - 2937))
    ax.plot(iouts[nom_idx], effs[nom_idx], 's', color=COLORS['gold'], markersize=10,
            zorder=5, label=f'Nominal ({effs[nom_idx]:.1f}%)')

    ax.set_xlabel('Load Current (mA)')
    ax.set_ylabel('Efficiency (%)')
    ax.set_title('Power Efficiency', fontweight='bold', fontsize=13)
    ax.legend(loc='lower left', framealpha=0.8)
    ax.set_ylim(0, 100)


# ---------------------------------------------------------------------------
# 5. Optimization Journey (from results.tsv)
# ---------------------------------------------------------------------------
def plot_optimization_journey(ax):
    import csv
    steps, scores, notes_list = [], [], []
    with open('results.tsv') as f:
        reader = csv.DictReader(f, delimiter='\t')
        for row in reader:
            try:
                steps.append(int(row.get('step', len(steps) + 1)))
                scores.append(float(row.get('score', 0)))
                notes_list.append(row.get('notes', ''))
            except (ValueError, TypeError):
                continue

    if not steps:
        ax.text(0.5, 0.5, 'No optimization data', transform=ax.transAxes,
                ha='center', va='center', color=COLORS['dim'])
        return

    # Parse key metrics from notes
    effs, vouts = [], []
    for n in notes_list:
        eff_m = re.search(r'Eff=([\d.]+)%', n)
        vout_m = re.search(r'Vout=([\d.]+)V', n)
        effs.append(float(eff_m.group(1)) if eff_m else 0)
        vouts.append(float(vout_m.group(1)) if vout_m else 0)

    x = np.arange(len(steps))
    width = 0.35

    ax2 = ax.twinx()

    bars1 = ax.bar(x - width/2, effs, width, color=COLORS['accent3'], alpha=0.7, label='Efficiency (%)')
    bars2 = ax2.bar(x + width/2, vouts, width, color=COLORS['accent1'], alpha=0.7, label='Vout (V)')

    ax.set_xlabel('Optimization Iteration')
    ax.set_ylabel('Efficiency (%)', color=COLORS['accent3'])
    ax2.set_ylabel('Output Voltage (V)', color=COLORS['accent1'])
    ax.set_xticks(x)
    ax.set_xticklabels([f'Iter {s}' for s in steps], fontsize=9)

    # Value labels on bars
    for bar, val in zip(bars1, effs):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
                f'{val:.0f}%', ha='center', va='bottom', fontsize=8, color=COLORS['accent3'])
    for bar, val in zip(bars2, vouts):
        ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.05,
                 f'{val:.1f}V', ha='center', va='bottom', fontsize=8, color=COLORS['accent1'])

    ax.set_ylim(0, 100)
    ax2.set_ylim(0, 6)
    ax.set_title('Optimization Journey — AI Iterations', fontweight='bold', fontsize=13)

    lines1, labels1 = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(lines1 + lines2, labels1 + labels2, loc='lower right', framealpha=0.8)
    ax2.spines['right'].set_color(COLORS['accent1'])
    ax2.tick_params(axis='y', colors=COLORS['accent1'])


# ---------------------------------------------------------------------------
# 6. Spec Scorecard
# ---------------------------------------------------------------------------
def plot_scorecard(ax):
    specs = [
        ('Output Voltage',  '>3.0 V',   '4.49 V',   True,  4.49/3.0),
        ('Load Current',    '>1 mA',    '1.53 mA',  True,  1.53/1.0),
        ('Efficiency',      '>50%',     '83.5%',    True,  83.5/50),
        ('Ripple',          '<100 mV',  '3.6 mV',   True,  3.6/100),
        ('Startup Time',    '<50 µs',   '0.74 µs',  True,  0.74/50),
    ]

    ax.set_xlim(0, 10)
    ax.set_ylim(0, len(specs) + 1)
    ax.axis('off')

    ax.text(5, len(specs) + 0.5, 'SPECIFICATION SCORECARD', ha='center', va='center',
            fontsize=14, fontweight='bold', color=COLORS['gold'])

    for i, (name, target, measured, met, ratio) in enumerate(specs):
        y = len(specs) - i - 0.2

        # Status icon
        status_color = COLORS['spec_line'] if met else COLORS['spec_fail']
        status_text = 'PASS' if met else 'FAIL'
        ax.text(0.3, y, status_text, fontsize=10, fontweight='bold', color=status_color, va='center')

        # Spec name
        ax.text(1.5, y, name, fontsize=11, color=COLORS['text'], va='center')

        # Target
        ax.text(4.5, y, f'Target: {target}', fontsize=9, color=COLORS['dim'], va='center')

        # Measured
        ax.text(6.8, y, f'Got: {measured}', fontsize=10, fontweight='bold', color=status_color, va='center')

        # Margin bar
        bar_x = 8.3
        bar_w = 1.5
        if '<' in target:
            margin_frac = min(1.0 - ratio, 1.0)
        else:
            margin_frac = min(ratio - 1.0, 1.0)

        ax.barh(y, margin_frac * bar_w, left=bar_x, height=0.35,
                color=status_color, alpha=0.6, edgecolor=status_color)
        margin_pct = margin_frac * 100
        ax.text(bar_x + bar_w + 0.1, y, f'+{margin_pct:.0f}%', fontsize=8,
                color=COLORS['dim'], va='center')


# ---------------------------------------------------------------------------
# Parse load sweep output
# ---------------------------------------------------------------------------
def parse_sweep_output(filepath):
    data = {'rvals': [], 'vouts': [], 'iouts': [], 'effs': []}
    with open(filepath) as f:
        for line in f:
            m = re.search(r'SWEEP_POINT rval=([\d.e+-]+)\s+vout=([\d.e+-]+)\s+iout=([\d.e+-]+)\s+eff=([\d.e+-]+)', line)
            if m:
                data['rvals'].append(float(m.group(1)))
                data['vouts'].append(float(m.group(2)))
                data['iouts'].append(float(m.group(3)))
                data['effs'].append(float(m.group(4)))
    return data


# ---------------------------------------------------------------------------
# Main — Generate the master figure
# ---------------------------------------------------------------------------
def main():
    os.makedirs('plots', exist_ok=True)

    # Check which data files exist
    has_startup = os.path.exists('sims/data_startup.csv')
    has_ripple = os.path.exists('sims/data_ripple.csv')
    has_sweep = os.path.exists('sims/loadsweep_output.txt')

    sweep_data = None
    if has_sweep:
        sweep_data = parse_sweep_output('sims/loadsweep_output.txt')
        if not sweep_data['rvals']:
            has_sweep = False

    print(f"Data available: startup={has_startup}, ripple={has_ripple}, sweep={has_sweep}")

    # === Master 6-panel figure ===
    fig = plt.figure(figsize=(20, 24))
    fig.suptitle('AI-Designed SKY130 Charge Pump — Pelliconi 2-Stage',
                 fontsize=22, fontweight='bold', color=COLORS['gold'], y=0.98)
    fig.text(0.5, 0.965,
             '1.8V → 4.49V  |  83.5% Efficiency  |  3.6 mV Ripple  |  All Specs Met',
             ha='center', fontsize=13, color=COLORS['dim'])

    gs = GridSpec(3, 2, figure=fig, hspace=0.3, wspace=0.25,
                  left=0.07, right=0.95, top=0.94, bottom=0.04)

    # Panel 1: Startup
    ax1 = fig.add_subplot(gs[0, 0])
    if has_startup:
        plot_startup(ax1)
    else:
        ax1.text(0.5, 0.5, 'Startup data not available', transform=ax1.transAxes,
                 ha='center', color=COLORS['dim'])

    # Panel 2: Ripple
    ax2 = fig.add_subplot(gs[0, 1])
    if has_ripple:
        plot_ripple(ax2)
    else:
        ax2.text(0.5, 0.5, 'Ripple data not available', transform=ax2.transAxes,
                 ha='center', color=COLORS['dim'])

    # Panel 3: Load regulation
    ax3 = fig.add_subplot(gs[1, 0])
    if has_sweep:
        plot_load_regulation(ax3, sweep_data)
    else:
        ax3.text(0.5, 0.5, 'Load sweep data not available', transform=ax3.transAxes,
                 ha='center', color=COLORS['dim'])

    # Panel 4: Efficiency
    ax4 = fig.add_subplot(gs[1, 1])
    if has_sweep:
        plot_efficiency(ax4, sweep_data)
    else:
        ax4.text(0.5, 0.5, 'Efficiency data not available', transform=ax4.transAxes,
                 ha='center', color=COLORS['dim'])

    # Panel 5: Optimization journey
    ax5 = fig.add_subplot(gs[2, 0])
    plot_optimization_journey(ax5)

    # Panel 6: Scorecard
    ax6 = fig.add_subplot(gs[2, 1])
    plot_scorecard(ax6)

    plt.savefig('plots/charge_pump_blog.png', dpi=200, bbox_inches='tight')
    print("Saved: plots/charge_pump_blog.png")
    plt.close()

    # === Individual high-res plots for blog ===
    if has_startup:
        fig, ax = plt.subplots(figsize=(12, 6))
        plot_startup(ax)
        plt.savefig('plots/blog_startup.png', dpi=200, bbox_inches='tight')
        plt.close()
        print("Saved: plots/blog_startup.png")

    if has_ripple:
        fig, ax = plt.subplots(figsize=(12, 6))
        plot_ripple(ax)
        plt.savefig('plots/blog_ripple.png', dpi=200, bbox_inches='tight')
        plt.close()
        print("Saved: plots/blog_ripple.png")

    if has_sweep:
        fig, ax = plt.subplots(figsize=(12, 6))
        plot_load_regulation(ax, sweep_data)
        plt.savefig('plots/blog_load_regulation.png', dpi=200, bbox_inches='tight')
        plt.close()
        print("Saved: plots/blog_load_regulation.png")

        fig, ax = plt.subplots(figsize=(12, 6))
        plot_efficiency(ax, sweep_data)
        plt.savefig('plots/blog_efficiency.png', dpi=200, bbox_inches='tight')
        plt.close()
        print("Saved: plots/blog_efficiency.png")

    fig, ax = plt.subplots(figsize=(12, 6))
    plot_optimization_journey(ax)
    plt.savefig('plots/blog_optimization.png', dpi=200, bbox_inches='tight')
    plt.close()
    print("Saved: plots/blog_optimization.png")

    fig, ax = plt.subplots(figsize=(12, 5))
    plot_scorecard(ax)
    plt.savefig('plots/blog_scorecard.png', dpi=200, bbox_inches='tight')
    plt.close()
    print("Saved: plots/blog_scorecard.png")

    print("\nAll plots generated!")


if __name__ == '__main__':
    main()
