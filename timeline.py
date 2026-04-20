"""HUNTER operational timeline.

Defines the phases of the operation from launch through summer study to
the autumn paper release. Other modules (orchestrator, hunter, dashboard,
prediction_board) query this to know where we are and adjust behaviour.

Query the current phase:
    from timeline import current_phase, is_active
    p = current_phase()
    print(p.name)                      # "Summer Empirical Run"
    if p.prefer_short_windows: ...     # bias prompt toward 30-90d windows
    if p.throttle_api: ...             # skip expensive cycles in broke-mode

Or check a specific phase:
    if is_active('beta'): ...          # summer run active

Change the dates once at top; every consumer gets the update.

Usage:
    python timeline.py                 # print full timeline + current phase
    python timeline.py phase           # current phase only
    python timeline.py next            # countdown to next phase
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import List, Optional


@dataclass
class Phase:
    """A named operational phase with behaviour flags."""

    id: str
    name: str
    start: date
    end: date
    description: str

    # Behaviour flags (consumers read these)
    run_continuously: bool = False     # orchestrator should run 24/7
    throttle_api: bool = False          # reduce/skip expensive API calls
    prefer_short_windows: bool = False  # hypothesis formation biases to 30-90d
    public_board_active: bool = True    # prediction board accepts new entries
    paper_push_active: bool = False     # SSRN/Zenodo/press outreach in progress
    outreach_active: bool = False       # cold emails, podcast pitches

    # Meta
    key_milestones: List[str] = field(default_factory=list)

    def days_remaining(self) -> int:
        return (self.end - datetime.now().date()).days

    def days_elapsed(self) -> int:
        return (datetime.now().date() - self.start).days

    def is_current(self) -> bool:
        today = datetime.now().date()
        return self.start <= today <= self.end

    def __str__(self):
        return f"[{self.id}] {self.name} ({self.start} → {self.end})"


# ═══════════════════════════════════════════════════════════════════════
# THE TIMELINE — edit dates here, everything else updates
# ═══════════════════════════════════════════════════════════════════════

PHASES: List[Phase] = [
    Phase(
        id="alpha",
        name="Infrastructure Launch",
        start=date(2026, 4, 21),
        end=date(2026, 5, 31),
        description=(
            "Ship public artifacts. GitHub repo, Zenodo corpus, Substack, X, "
            "methodology brief, empty prediction board. Priority-of-discovery locked. "
            "Zero API spend. Exam season — minimal operator time."
        ),
        run_continuously=False,
        throttle_api=True,
        prefer_short_windows=False,
        public_board_active=True,
        paper_push_active=False,
        outreach_active=False,
        key_milestones=[
            "2026-04-28: Public launch (GitHub + X + Substack + Zenodo)",
            "2026-05-05: Paper 0 (methods) to SSRN",
            "2026-05-31: Exams complete, Phase β begins",
        ],
    ),
    Phase(
        id="beta",
        name="Summer Empirical Run",
        start=date(2026, 6, 1),
        end=date(2026, 8, 31),
        description=(
            "HUNTER runs continuously with API budget. Pre-registered 12-week "
            "study active. Hypothesis formation biased to short (30-90d) windows "
            "so first resolutions land mid-July. Weekly analyser suite. Monthly "
            "residual estimator. Diary entries auto-compile into preprint sections."
        ),
        run_continuously=True,
        throttle_api=False,
        prefer_short_windows=True,
        public_board_active=True,
        paper_push_active=False,
        outreach_active=True,
        key_milestones=[
            "2026-06-01: Summer study starts, code+corpus hashes verified",
            "2026-07-15: First 30-day predictions begin resolving on public board",
            "2026-08-10: ≈30 resolved predictions, mid-summer data review",
            "2026-08-31: Study complete, data frozen for paper writing",
        ],
    ),
    Phase(
        id="gamma",
        name="Autumn Paper Launch",
        start=date(2026, 9, 1),
        end=date(2026, 12, 15),
        description=(
            "Summer data in hand. Papers 5 and 6 rewritten with real empirical "
            "content. SSRN submissions. Press outreach (Matt Levine, Tyler Cowen, "
            "Alphaville). First reinsurance / fund licensing conversations. "
            "Book proposal to agents. Podcast circuit active."
        ),
        run_continuously=True,
        throttle_api=False,
        prefer_short_windows=True,
        public_board_active=True,
        paper_push_active=True,
        outreach_active=True,
        key_milestones=[
            "2026-09-10: Paper 5 (Mechanism Monopoly) to SSRN with summer data",
            "2026-09-30: Paper 6 (Computational Collapse) to SSRN",
            "2026-10-15: Book proposal to 5 agents",
            "2026-12-15: First licensing pilot signed (target)",
        ],
    ),
    Phase(
        id="delta",
        name="Year 2 Compound",
        start=date(2026, 12, 16),
        end=date(2027, 12, 31),
        description=(
            "Continuous operation. Expanded corpus (target 50k+ facts). "
            "Fund-seed conversations. Paper 1 empirical under review. "
            "Multi-lingual silos fully active. Revenue scaling from £5k/mo → £50k/mo. "
            "Possibly first hire / contractor."
        ),
        run_continuously=True,
        throttle_api=False,
        prefer_short_windows=False,  # longer-window findings now acceptable given track record
        public_board_active=True,
        paper_push_active=True,
        outreach_active=True,
        key_milestones=[
            "2027-03-31: 100+ resolved predictions, first fund-seed term-sheet",
            "2027-06-30: Paper 1 published, second summer study begins",
            "2027-12-31: Year 1 of public operation complete",
        ],
    ),
]


# ═══════════════════════════════════════════════════════════════════════
# QUERY HELPERS
# ═══════════════════════════════════════════════════════════════════════

def current_phase() -> Optional[Phase]:
    """Return the currently-active phase, or None if between phases."""
    today = datetime.now().date()
    for p in PHASES:
        if p.start <= today <= p.end:
            return p
    return None


def phase_by_id(pid: str) -> Optional[Phase]:
    for p in PHASES:
        if p.id == pid:
            return p
    return None


def is_active(pid: str) -> bool:
    p = current_phase()
    return p is not None and p.id == pid


def next_phase() -> Optional[Phase]:
    today = datetime.now().date()
    for p in PHASES:
        if p.start > today:
            return p
    return None


def days_until_next_phase() -> Optional[int]:
    p = next_phase()
    if p is None:
        return None
    return (p.start - datetime.now().date()).days


def flag(name: str, default=False) -> bool:
    """Read a behaviour flag from the current phase (with safe default)."""
    p = current_phase()
    if p is None:
        return default
    return getattr(p, name, default)


# ═══════════════════════════════════════════════════════════════════════
# INTEGRATION HELPERS (other modules call these)
# ═══════════════════════════════════════════════════════════════════════

def should_throttle_api() -> bool:
    """Check whether orchestrator / ingest should throttle API calls."""
    return flag("throttle_api", default=False)


def should_prefer_short_windows() -> bool:
    """Check whether hypothesis formation should bias toward 30-90d resolution windows."""
    return flag("prefer_short_windows", default=False)


def board_accepting_entries() -> bool:
    """Check whether the public prediction board is in an accepting state."""
    return flag("public_board_active", default=True)


def short_window_prompt_suffix() -> str:
    """Return a prompt suffix to append to HYPOTHESIS_FORM_PROMPT when
    short windows are preferred. Empty string if not."""
    if not should_prefer_short_windows():
        return ""
    return (
        "\n\nWINDOW PREFERENCE: Where the underlying catalyst supports it, prefer "
        "shorter resolution windows (30-90 days) over longer ones (180+ days). "
        "A 60-day thesis that resolves quickly is more valuable than a 365-day "
        "thesis that resolves eventually — faster feedback compounds faster track record. "
        "Only use long windows (180+ days) when the catalyst is genuinely long-dated "
        "(e.g., a 2028 regulatory effective date or a multi-year patent cliff)."
    )


# ═══════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════

def _print_full_timeline():
    today = datetime.now().date()
    print(f"\n{'═' * 72}")
    print(f"  HUNTER TIMELINE — today is {today}")
    print(f"{'═' * 72}\n")

    for p in PHASES:
        status = ""
        if p.start <= today <= p.end:
            elapsed = (today - p.start).days
            remaining = (p.end - today).days
            status = f"  ← CURRENT ({elapsed}d in, {remaining}d left)"
        elif p.end < today:
            status = "  ✓ complete"
        else:
            until = (p.start - today).days
            status = f"  → starts in {until}d"

        print(f"  [{p.id}] {p.name}")
        print(f"       {p.start} → {p.end}   {status}")
        print(f"       {p.description}")
        if p.key_milestones:
            print(f"       Key milestones:")
            for m in p.key_milestones:
                print(f"         - {m}")
        flags_on = [f for f in [
            "run_continuously", "throttle_api", "prefer_short_windows",
            "public_board_active", "paper_push_active", "outreach_active",
        ] if getattr(p, f, False)]
        if flags_on:
            print(f"       Active flags: {', '.join(flags_on)}")
        print()


def _print_current():
    p = current_phase()
    if p is None:
        print("NO ACTIVE PHASE (between phases)")
        nxt = next_phase()
        if nxt:
            print(f"Next: {nxt.name} starts {nxt.start} ({days_until_next_phase()}d)")
        return
    print(f"\n  [{p.id}] {p.name}")
    print(f"  {p.start} → {p.end}  ({p.days_elapsed()}d in, {p.days_remaining()}d left)")
    print(f"  {p.description}")
    print(f"\n  Flags:")
    for f in ["run_continuously", "throttle_api", "prefer_short_windows",
              "public_board_active", "paper_push_active", "outreach_active"]:
        on = "✓" if getattr(p, f, False) else " "
        print(f"    [{on}] {f}")


def _print_next():
    p = current_phase()
    nxt = next_phase()
    if p:
        print(f"Current: {p.name} — {p.days_remaining()}d left")
    if nxt:
        d = days_until_next_phase()
        print(f"Next:    {nxt.name} starts {nxt.start} (in {d}d)")


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "full"
    if cmd == "phase":
        _print_current()
    elif cmd == "next":
        _print_next()
    else:
        _print_full_timeline()
