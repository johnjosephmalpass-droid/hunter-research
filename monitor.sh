#!/bin/bash
# HUNTER v3 Golden — Live Monitor
# Usage: bash monitor.sh

CHECKPOINT="theory_run_v3_golden_output/checkpoint.json"
DB="hunter_v3_golden.db"
LOG="theory_run_v3_golden_output/run.log"
TOTAL_CYCLES=240

while true; do
    clear
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║         HUNTER v3 GOLDEN — LIVE MONITOR                    ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo ""

    if [ ! -f "$CHECKPOINT" ]; then
        echo "  Waiting for first checkpoint..."
        sleep 10
        continue
    fi

    # Parse checkpoint
    CYCLES=$(python3 -c "import json; d=json.load(open('$CHECKPOINT')); print(d['completed_cycles'])" 2>/dev/null)
    COST=$(python3 -c "import json; d=json.load(open('$CHECKPOINT')); print(f\"\${d['total_cost']:.2f}\")" 2>/dev/null)
    PHASE=$(python3 -c "import json; d=json.load(open('$CHECKPOINT')); print(d['phase'])" 2>/dev/null)
    TIMESTAMP=$(python3 -c "import json; d=json.load(open('$CHECKPOINT')); print(d['timestamp'][:19])" 2>/dev/null)
    ERRORS=$(python3 -c "import json; d=json.load(open('$CHECKPOINT')); print(d['errors'])" 2>/dev/null)

    # Calculate progress
    PCT=$(python3 -c "print(f'{$CYCLES/$TOTAL_CYCLES*100:.1f}')" 2>/dev/null)
    BAR_LEN=40
    FILLED=$(python3 -c "print(int($CYCLES/$TOTAL_CYCLES*$BAR_LEN))" 2>/dev/null)
    EMPTY=$(python3 -c "print($BAR_LEN - int($CYCLES/$TOTAL_CYCLES*$BAR_LEN))" 2>/dev/null)
    BAR=$(printf '█%.0s' $(seq 1 $FILLED 2>/dev/null) 2>/dev/null)
    SPACE=$(printf '░%.0s' $(seq 1 $EMPTY 2>/dev/null) 2>/dev/null)

    echo "  Phase: $PHASE/5    Last update: $TIMESTAMP"
    echo ""
    echo "  [$BAR$SPACE] $PCT%"
    echo "  Cycles: $CYCLES / $TOTAL_CYCLES"
    echo "  Cost:   $COST / \$600"
    echo "  Errors: $ERRORS"
    echo ""

    # DB stats
    if [ -f "$DB" ]; then
        STATS=$(python3 -c "
import sqlite3
conn = sqlite3.connect('$DB')
scored = conn.execute('SELECT COUNT(*) FROM hypotheses WHERE stratum IS NOT NULL AND diamond_score IS NOT NULL').fetchone()[0]
collisions = conn.execute('SELECT COUNT(*) FROM collisions WHERE created_at > datetime(\"now\", \"-1 day\")').fetchone()[0]
avg = conn.execute('SELECT AVG(diamond_score) FROM hypotheses WHERE stratum IS NOT NULL AND diamond_score IS NOT NULL').fetchone()[0]
top = conn.execute('SELECT MAX(diamond_score) FROM hypotheses WHERE stratum IS NOT NULL AND diamond_score IS NOT NULL').fetchone()[0]
by_stratum = {}
for s in ['A','B','C','D']:
    c = conn.execute('SELECT COUNT(*) FROM hypotheses WHERE stratum=? AND diamond_score IS NOT NULL', (s,)).fetchone()[0]
    by_stratum[s] = c
conn.close()
print(f'{scored}|{collisions}|{avg or 0:.1f}|{top or 0}|{by_stratum[\"A\"]}|{by_stratum[\"B\"]}|{by_stratum[\"C\"]}|{by_stratum[\"D\"]}')
" 2>/dev/null)

        IFS='|' read -r SCORED COLLISIONS AVG TOP SA SB SC SD <<< "$STATS"
        echo "  ┌─────────────────────────────────────┐"
        echo "  │  Hypotheses scored:  $SCORED"
        echo "  │  Collisions today:   $COLLISIONS"
        echo "  │  Avg score:          $AVG / 100"
        echo "  │  Top score:          $TOP / 100"
        echo "  │                                     │"
        echo "  │  By stratum:                        │"
        echo "  │    A (single):  $SA"
        echo "  │    B (cross-2): $SB"
        echo "  │    C (cross-3): $SC"
        echo "  │    D (open):    $SD"
        echo "  └─────────────────────────────────────┘"
    fi

    echo ""
    echo "  Latest activity:"
    tail -3 "$LOG" 2>/dev/null | sed 's/\x1b\[[0-9;]*m//g' | sed 's/^/    /'
    echo ""
    echo "  [Ctrl+C to exit monitor]"
    sleep 15
done
