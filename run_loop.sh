#!/bin/bash
cd "$(dirname "$0")"
ITERATION=0
LOG="run_loop.log"
echo "=== Charge Pump Autoresearch Loop Started: $(date) ===" | tee -a "$LOG"
while true; do
    ITERATION=$((ITERATION + 1))
    echo "" | tee -a "$LOG"
    echo "=== ITERATION $ITERATION — $(date) ===" | tee -a "$LOG"
    PROMPT="You are an autonomous analog circuit designer. Read program.md for full instructions.

Current iteration: $ITERATION

Do ONE complete experiment loop iteration:
1. Read results.tsv, design.cir, parameters.csv — understand current state
2. Analyze what is limiting performance (read measurements.json if it exists)
3. Plan and implement a topology change in design.cir and parameters.csv
4. Commit the topology change: git add -A && git commit -m 'topology: <description>'
5. Run: python3 evaluate.py 2>&1 | tee run.log
6. Read the evaluation output and analyze results
7. Append results to results.tsv
8. Generate schematic from design.cir:
   python3 ~/cir2sch/cir2sch.py design.cir plots/schematic.sch
   timeout 15 xvfb-run -a xschem --command \"after 1000 {xschem print svg \$(pwd)/plots/schematic.svg; after 500 {exit 0}}\" plots/schematic.sch
9. Generate progress plot from results.tsv using matplotlib:
   python3 -c \"
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
lines = open('results.tsv').readlines()
if len(lines) > 1:
    scores = []
    for l in lines[1:]:
        parts = l.strip().split('\t')
        if len(parts) >= 2:
            try: scores.append(float(parts[1]))
            except: pass
    if scores:
        plt.figure(figsize=(10,6))
        plt.plot(range(1,len(scores)+1), scores, 'b-o')
        plt.xlabel('Iteration')
        plt.ylabel('Score')
        plt.title('Design Progress')
        plt.grid(True)
        plt.savefig('plots/progress.png', dpi=150)
        plt.close()
\"
10. Commit and push everything: git add -A && git commit -m 'results: <score> — <summary>' && git push

IMPORTANT: You MUST commit and push results before finishing. Do not skip any step."
    echo "$PROMPT" | claude --dangerously-skip-permissions 2>&1 | tee -a "$LOG"
    EXIT_CODE=$?
    echo "Claude exited with code $EXIT_CODE at $(date)" | tee -a "$LOG"
    sleep 5
done
