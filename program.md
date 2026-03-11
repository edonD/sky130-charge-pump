# Autonomous Circuit Design — Charge Pump

You are an autonomous analog circuit designer. Your goal: design a charge pump voltage doubler that meets every specification in `specs.json` using the SKY130 foundry PDK.

You have Differential Evolution (DE) as your optimizer. You define topology and parameter ranges — DE finds optimal values. You NEVER set component values manually.

## Files

| File | Editable? | Purpose |
|------|-----------|---------|
| `design.cir` | YES | Parametric SPICE netlist |
| `parameters.csv` | YES | Parameter names, min, max for DE |
| `evaluate.py` | YES | Runs DE, measures, scores, plots |
| `specs.json` | **NO** | Target specifications |
| `program.md` | **NO** | These instructions |
| `de/engine.py` | **NO** | DE optimizer engine |
| `results.tsv` | YES | Experiment log — append after every run |

## Technology

- **PDK:** SkyWater SKY130 (130nm). Models: `.lib "sky130_models/sky130.lib.spice" tt`
- **Devices:** `sky130_fd_pr__nfet_01v8`, `sky130_fd_pr__pfet_01v8` (and LVT/HVT variants)
- **High-voltage devices:** `sky130_fd_pr__nfet_g5v0d10v5`, `sky130_fd_pr__pfet_g5v0d10v5` (5V tolerant — use these for nodes above 1.8V)
- **Instantiation:** `XM1 drain gate source bulk sky130_fd_pr__nfet_01v8 W=10u L=0.5u nf=1`
- **Supply:** 1.8V single supply. Nodes: `vdd` = 1.8V, `vss` = 0V
- **Units:** Always specify W and L with `u` suffix (micrometers). Capacitors with `p` or `f`.
- **ngspice settings:** `.spiceinit` must contain `set ngbehavior=hsa` and `set skywaterpdk`

## Design Freedom

You are free to explore any charge pump topology. Dickson charge pump, Cockcroft-Walton, cross-coupled voltage doubler, Pelliconi cascade, Makowski charge pump, bootstrap switches — whatever you think will work. Experiment boldly.

You choose the number of stages, switching frequency, clock scheme (single-phase, two-phase, four-phase), and output regulation strategy. The clock generator can be part of the design or an external PULSE source — your call.

**Important:** The output node will exceed 1.8V. Use 5V-tolerant devices (`nfet_g5v0d10v5`, `pfet_g5v0d10v5`) for any transistor whose terminals see voltages above 1.8V. Using 1.8V devices above their rated voltage is not physically real.

The only constraints are physical reality:

1. **All values parametric.** Every W, L, resistor, capacitor, and bias current uses `{name}` in design.cir with a matching row in parameters.csv.
2. **Ranges must be physically real.** W: 0.5u–500u. L: 0.15u–10u. Caps: 10fF–100pF (flying caps can be larger if external). Resistors: 50Ω–500kΩ. Ranges must span at least 10× (one decade).
3. **No hardcoding to game the optimizer.** A range of [5.0, 5.001] is cheating. Every parameter must have real design freedom.
4. **No editing specs.json or model files.** You optimize the circuit to meet the specs, not the other way around.

## The Loop

### 1. Read current state
- `results.tsv` — what you've tried and how it scored
- `design.cir` + `parameters.csv` — current topology
- `specs.json` — what you're targeting

### 2. Design or modify the topology
Change whatever you think will improve performance. You can make small tweaks or try a completely different architecture. Your call.

### 3. Implement
- Edit `design.cir` with the new/modified circuit
- Update `parameters.csv` with ranges for all parameters
- Update `evaluate.py` if measurements need changes
- Verify every `{placeholder}` in design.cir has a parameters.csv entry

### 4. Commit topology
```bash
git add -A
git commit -m "topology: <what changed>"
git push
```
Commit ALL files so any commit can be cloned and understood standalone.

### 5. Run DE
```bash
python evaluate.py 2>&1 | tee run.log          # full run
python evaluate.py --quick 2>&1 | tee run.log   # quick sanity check
```

### 6. Validate — THIS IS MANDATORY

DE found numbers. Now prove they're real. **Do not skip any of these checks.**

#### a) Steady-state verification
Run transient simulation long enough for the output to reach steady state (typically 100+ clock cycles). The output voltage must be stable (not still rising). Measure Vout only after it has settled.

#### b) Load regulation check
Measure Vout at the specified load current. Then vary load from 0 to 2× rated current. Vout should degrade gracefully, not collapse. If Vout drops below 3.0V at the rated 1mA, the spec isn't met.

#### c) Efficiency calculation
Efficiency = (Vout × Iout) / (Vdd × Idd). Measure average input current over full clock cycles in steady state. If efficiency > 90% for an on-chip charge pump, something is wrong — check for modeling errors.

#### d) Ripple measurement
Measure peak-to-peak ripple on Vout in steady state. Use the last 10 clock cycles. Ripple is typically set by output capacitance and load current.

**Only after all four checks pass do you log the result.**

### 7. Generate plots and log results

#### a) Functional plots — `plots/`
Generate these plots every iteration (overwrite previous):
- **`startup.png`** — Vout vs time from power-on. Annotate startup time to 90% of final value.
- **`ripple.png`** — Zoomed Vout in steady state showing ripple. Annotate peak-to-peak ripple.
- **`vout_vs_iload.png`** — Vout vs load current (sweep load). Annotate max current at Vout > 3.0V.
- **`efficiency.png`** — Efficiency vs load current.

Use a dark theme. Label axes with units. Annotate key measurements directly on each plot.

#### b) Progress plot — `plots/progress.png`
Regenerate from `results.tsv` after every run:
- X axis: iteration number
- Y axis: best score so far
- Mark topology changes with vertical dashed lines
- Mark the point where all specs were first met

#### c) Log to results.tsv
Append one line:
```
<commit_hash>	<score>	<topology>	<specs_met>/<total>	<notes>
```

#### d) Commit and push everything
```bash
git add -A
git commit -m "results: <score> — <summary>"
git push
```
Every commit must include ALL files — source, parameters, plots, logs, measurements.

### 8. Decide next step
- Specs not met → analyze what's failing, change topology or ranges
- DE didn't converge → widen ranges or try different architecture
- Specs met → keep improving margins, then check stopping condition

## Stopping Condition

Track a counter: `steps_without_improvement`. After each run:
- If the best score improved → reset counter to 0
- If it did not improve → increment counter

**Stop when BOTH conditions are true:**
1. All specifications in `specs.json` are met (verified by steady-state transient)
2. `steps_without_improvement >= 50`

Until both conditions are met, keep iterating.

## Known Pitfalls

**Voltage stress on 1.8V devices.** Any node that goes above 1.8V MUST use 5V-tolerant devices. Using `nfet_01v8` with Vds > 1.98V (1.1× rated) will cause breakdown in real silicon. The simulator won't warn you — you must check this yourself.

**Transient simulation length.** Charge pumps need many clock cycles to reach steady state. If the simulation is too short, Vout is still rising and measurements are meaningless. Check that dVout/dt ≈ 0 before measuring.

**Clock feedthrough.** Parasitic capacitance from clock lines to the output causes ripple. This is real and often the dominant ripple source. Differential clock schemes (two-phase) help cancel this.

**Efficiency accounting.** Don't forget to include power consumed by the clock driver/buffers. The clock generator is part of the circuit.
