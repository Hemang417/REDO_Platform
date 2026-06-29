"""
REDO Platform — Streamlit UI

Run with:
    streamlit run app.py
"""

from __future__ import annotations

import glob
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

import streamlit as st
import yaml

# ── Base directory (always the repo root, regardless of CWD) ─────────────────
BASE_DIR = Path(__file__).parent.resolve()
SCRIPTS = BASE_DIR / "scripts"
CONFIG_DIR = BASE_DIR / "config"
OUTPUT_DIR = BASE_DIR / "output"

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="REDO Platform",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Minimal CSS overrides ─────────────────────────────────────────────────────
st.markdown("""
<style>
[data-testid="stSidebar"] { background: #1B3A6B; }
[data-testid="stSidebar"] * { color: rgba(255,255,255,0.85) !important; }
[data-testid="stSidebar"] label { color: rgba(255,255,255,0.6) !important; font-size: 12px !important; }
[data-testid="stSidebar"] .stTextInput input,
[data-testid="stSidebar"] .stSelectbox select,
[data-testid="stSidebar"] .stNumberInput input {
    background: rgba(255,255,255,0.1) !important;
    border: 1px solid rgba(255,255,255,0.2) !important;
    color: white !important;
}
.stage-card {
    background: #fff;
    border: 1px solid #D1D9E6;
    border-radius: 8px;
    padding: 14px 18px;
    margin-bottom: 10px;
    border-left: 4px solid #9CA3AF;
}
.stage-card.running  { border-left-color: #C47C1A; background: #FFFBF2; }
.stage-card.done     { border-left-color: #1A7F5A; background: #F0FAF5; }
.stage-card.error    { border-left-color: #DC2626; background: #FFF5F5; }
.stage-card.skipped  { border-left-color: #6B7280; background: #F9FAFB; }
.stButton button { font-weight: 600; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _latest(pattern: str) -> Optional[Path]:
    matches = sorted(glob.glob(str(BASE_DIR / pattern)), reverse=True)
    return Path(matches[0]) if matches else None


def _has_output(pattern: str) -> bool:
    return bool(glob.glob(str(BASE_DIR / pattern)))


def _run_stage(cmd: list[str], log_container) -> int:
    """Run a subprocess and stream output into a Streamlit container."""
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(BASE_DIR),
        env=env,
    )

    lines: list[str] = []
    log_placeholder = log_container.empty()

    for line in iter(proc.stdout.readline, ""):
        stripped = line.rstrip()
        if stripped:
            lines.append(stripped)
            # Show last 35 lines, wrapped in a scrollable code block
            log_placeholder.code("\n".join(lines[-35:]), language="")

    proc.wait()
    return proc.returncode


def _load_scoring_rules() -> dict:
    path = CONFIG_DIR / "scoring_rules.yaml"
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _save_scoring_rules(data: dict) -> None:
    path = CONFIG_DIR / "scoring_rules.yaml"
    tmp = path.with_suffix(".yaml.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
    os.replace(tmp, path)


def _load_ai_config() -> dict:
    path = CONFIG_DIR / "ai_config.yaml"
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _latest_report_html() -> Optional[Path]:
    return _latest("output/reports/deal_origination_*.html")


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar — Run Configuration
# ─────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("""
    <div style="padding:4px 0 18px">
      <div style="font-size:20px;font-weight:800;letter-spacing:-0.4px">REDO Platform</div>
      <div style="font-size:11px;opacity:0.5;letter-spacing:1px;text-transform:uppercase;margin-top:2px">
        Category II AIF · Maharashtra
      </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("**Run Configuration**")

    # --- Collector settings
    with st.expander("Module 1 — Collector", expanded=True):
        end_page = st.number_input(
            "End page (blank = all ~4,873 pages)",
            min_value=1, max_value=5000,
            value=st.session_state.get("end_page", 5),
            step=1,
            help="2 pages ≈ 20 projects, ~30 sec. Full run ≈ 22 hrs.",
        )
        st.session_state["end_page"] = end_page
        skip_collector = st.checkbox(
            "Skip collector (use existing raw data)",
            value=_has_output("output/raw/maharera_projects_*.json"),
            help="Check this if you already ran the collector and don't want to re-scrape.",
        )

    # --- Analyst settings
    with st.expander("Module 5 — AI Analyst", expanded=True):
        provider = st.selectbox(
            "AI Provider",
            ["groq", "claude"],
            index=0,
            help="Groq is free. Claude requires internal approval.",
        )
        st.session_state["provider"] = provider

        key_label = "GROQ_API_KEY" if provider == "groq" else "ANTHROPIC_API_KEY"
        env_val = os.environ.get(key_label, "")
        api_key_input = st.text_input(
            key_label,
            value=env_val,
            type="password",
            placeholder="Paste your API key here",
        )
        if api_key_input:
            os.environ[key_label] = api_key_input

        min_score = st.slider(
            "Min score for memo",
            min_value=0.0, max_value=80.0, value=0.0, step=5.0,
            help="Skip projects scoring below this. Saves API cost on large datasets.",
        )
        st.session_state["min_score"] = min_score

    # --- Pipeline summary
    st.markdown("---")
    st.markdown("**Output files**")
    for label, pattern in [
        ("Raw", "output/raw/*.json"),
        ("Clean", "output/clean/*.json"),
        ("Scored", "output/scored/*.json"),
        ("Intelligence", "output/intelligence/*.json"),
        ("Memos", "output/memos/investment_memos_*.json"),
        ("Report", "output/reports/*.html"),
    ]:
        exists = _has_output(pattern)
        icon = "🟢" if exists else "⚪"
        st.markdown(f"{icon} {label}", unsafe_allow_html=False)


# ─────────────────────────────────────────────────────────────────────────────
# Main tabs
# ─────────────────────────────────────────────────────────────────────────────

tab_pipeline, tab_scoring, tab_report = st.tabs([
    "▶  Run Pipeline",
    "⚙  Scoring Rules",
    "📄  View Report",
])


# ═════════════════════════════════════════════════════════════════════════════
# TAB 1 — Pipeline Runner
# ═════════════════════════════════════════════════════════════════════════════

with tab_pipeline:
    st.markdown("## Deal Origination Pipeline")
    st.caption(
        "Runs all 6 modules in sequence. Each module writes its output before "
        "the next one starts. You can also run individual stages below."
    )

    # --- CAPTCHA warning if collector is not skipped
    if not skip_collector:
        st.warning(
            "**Module 1 will open a Chrome window for CAPTCHA.** "
            "Stay at your machine to solve it manually — it only happens once. "
            "After that, the saved token is reused for all future runs. "
            "If you already have raw data, tick 'Skip collector' in the sidebar.",
            icon="⚠️",
        )

    # --- API key check
    key_env = "GROQ_API_KEY" if st.session_state.get("provider") == "groq" else "ANTHROPIC_API_KEY"
    if not os.environ.get(key_env):
        st.error(
            f"**{key_env} is not set.** Paste your API key in the sidebar before running.",
            icon="🔑",
        )

    st.markdown("---")

    # --- Stage definitions
    STAGES = [
        {
            "num": 1, "name": "Collector", "script": "run_collector.py",
            "desc": "Scrapes MAHARERA portal — list pages + detail API",
            "output_check": "output/raw/maharera_projects_*.json",
        },
        {
            "num": 2, "name": "Cleaner", "script": "run_cleaner.py",
            "desc": "Parses dates, computes delay days, normalises fields",
            "output_check": "output/clean/maharera_clean_*.json",
        },
        {
            "num": 3, "name": "Scorer", "script": "run_scorer.py",
            "desc": "Scores each project 0–100 using weighted config rules",
            "output_check": "output/scored/maharera_scored_*.json",
        },
        {
            "num": 4, "name": "Developer Intelligence", "script": "run_intelligence.py",
            "desc": "Aggregates developer portfolio metrics + track record score",
            "output_check": "output/intelligence/developer_profiles_*.json",
        },
        {
            "num": 5, "name": "AI Analyst", "script": "run_analyst.py",
            "desc": "Generates structured investment memos via AI",
            "output_check": "output/memos/investment_memos_*.json",
        },
        {
            "num": 6, "name": "Report Generator", "script": "run_reporter.py",
            "desc": "Assembles final HTML deal origination report",
            "output_check": "output/reports/deal_origination_*.html",
        },
    ]

    # --- Initialize stage status in session state
    if "stage_status" not in st.session_state:
        st.session_state["stage_status"] = {s["num"]: "pending" for s in STAGES}
    if "stage_logs" not in st.session_state:
        st.session_state["stage_logs"] = {s["num"]: "" for s in STAGES}

    # --- Run All button
    col_btn, col_info = st.columns([2, 5])
    with col_btn:
        run_all = st.button(
            "▶  Run Full Pipeline",
            type="primary",
            use_container_width=True,
            disabled=not os.environ.get(key_env),
        )

    # --- Stage cards + individual run buttons
    stage_log_containers = {}
    for stage in STAGES:
        n = stage["num"]
        status = st.session_state["stage_status"].get(n, "pending")
        has_output = _has_output(stage["output_check"])

        status_icon = {
            "pending": "⬜", "running": "🟡", "done": "✅",
            "error": "❌", "skipped": "⏭️",
        }.get(status, "⬜")

        col_info, col_run = st.columns([7, 2])
        with col_info:
            st.markdown(
                f"**{status_icon} Module {n} — {stage['name']}**  \n"
                f"<span style='font-size:13px;color:#6B7280'>{stage['desc']}"
                f"{'  · ✓ output exists' if has_output else ''}</span>",
                unsafe_allow_html=True,
            )
        with col_run:
            if st.button(f"Run {n}", key=f"run_{n}", use_container_width=True):
                st.session_state["stage_status"][n] = "running"
                st.rerun()

        log_container = st.expander(
            f"Logs — Module {n}",
            expanded=(status in ("running", "error")),
        )
        stage_log_containers[n] = log_container

        if st.session_state["stage_logs"].get(n):
            with log_container:
                st.code(st.session_state["stage_logs"][n], language="")

    # --- Build command for each stage
    def _build_cmd(stage: dict) -> list[str]:
        cmd = [sys.executable, str(SCRIPTS / stage["script"])]
        n = stage["num"]
        if n == 1:
            cmd += ["--end-page", str(st.session_state.get("end_page", 5))]
        if n == 5:
            cmd += ["--provider", st.session_state.get("provider", "groq")]
            min_s = st.session_state.get("min_score", 0.0)
            if min_s > 0:
                cmd += ["--min-score", str(min_s)]
        return cmd

    # --- Execute pipeline on Run All click
    if run_all:
        st.session_state["stage_status"] = {s["num"]: "pending" for s in STAGES}
        st.session_state["stage_logs"] = {s["num"]: "" for s in STAGES}

        for stage in STAGES:
            n = stage["num"]

            # Skip collector if user opted out
            if n == 1 and skip_collector:
                st.session_state["stage_status"][n] = "skipped"
                continue

            st.session_state["stage_status"][n] = "running"
            log_container = stage_log_containers[n]

            with log_container:
                st.info(f"Running Module {n} — {stage['name']}…")
                log_area = st.container()
                rc = _run_stage(_build_cmd(stage), log_area)

            if rc == 0:
                st.session_state["stage_status"][n] = "done"
            else:
                st.session_state["stage_status"][n] = "error"
                st.error(f"Module {n} failed (exit code {rc}). Check logs above.", icon="❌")
                break

        # Show report link if pipeline completed
        if all(
            st.session_state["stage_status"][n] in ("done", "skipped")
            for n in range(1, 7)
        ):
            report = _latest_report_html()
            if report:
                st.success(
                    f"**Pipeline complete!** Report saved to `{report.relative_to(BASE_DIR)}`",
                    icon="✅",
                )
                st.info(
                    "Switch to the **View Report** tab to read it, "
                    "or open the HTML file in Chrome and print to PDF.",
                    icon="📄",
                )

    # --- Execute individual stage run
    for stage in STAGES:
        n = stage["num"]
        if st.session_state["stage_status"].get(n) == "running" and not run_all:
            with stage_log_containers[n]:
                st.info(f"Running Module {n} — {stage['name']}…")
                log_area = st.container()
                rc = _run_stage(_build_cmd(stage), log_area)

            if rc == 0:
                st.session_state["stage_status"][n] = "done"
                st.rerun()
            else:
                st.session_state["stage_status"][n] = "error"
                st.rerun()


# ═════════════════════════════════════════════════════════════════════════════
# TAB 2 — Scoring Rules Editor
# ═════════════════════════════════════════════════════════════════════════════

with tab_scoring:
    st.markdown("## Scoring Rules")
    st.caption(
        "All investment scoring rules live in `config/scoring_rules.yaml`. "
        "Edit them here and click **Save** — changes take effect on the next scorer run. "
        "No code changes required."
    )

    try:
        rules = _load_scoring_rules()
    except Exception as e:
        st.error(f"Could not load scoring_rules.yaml: {e}")
        st.stop()

    w = rules["scoring"]["weights"]
    cp = rules["scoring"]["construction_progress"]
    ds = rules["scoring"]["delay_severity"]
    eh = rules["scoring"]["extension_history"]
    pv = rules["scoring"]["project_viability"]
    loc = rules["scoring"]["location"]
    devw = rules["developer_scoring"]["weights"]

    st.info(
        "**How scores work:** Each factor produces a 0.0–1.0 score. "
        "The final opportunity_score = weighted combination × 100, clamped to [0, 100]. "
        "**Project viability acts as a multiplier** — a lapsed project scores 0 regardless of all other factors.",
        icon="ℹ️",
    )

    # ── Factor Weights ────────────────────────────────────────────────────────
    with st.expander("**Factor Weights** (must sum to 1.0)", expanded=True):
        st.caption(
            "These weights control how much each factor contributes to the final opportunity score. "
            "A higher weight = that factor matters more to the investment thesis."
        )
        cols = st.columns(5)
        weight_labels = [
            ("Construction Progress", "construction_progress"),
            ("Delay Severity", "delay_severity"),
            ("Extension History", "extension_history"),
            ("Project Viability", "project_viability"),
            ("Location", "location"),
        ]
        new_weights = {}
        for col, (label, key) in zip(cols, weight_labels):
            with col:
                new_weights[key] = st.number_input(
                    label, min_value=0.0, max_value=1.0,
                    value=float(w[key]), step=0.05, format="%.2f",
                    key=f"w_{key}",
                )

        total = sum(new_weights.values())
        if abs(total - 1.0) > 0.001:
            st.warning(f"Weights sum to **{total:.2f}** — they must sum to exactly **1.00**. Adjust before saving.", icon="⚠️")
        else:
            st.success(f"Weights sum to {total:.2f} ✓", icon="✅")

    # ── Construction Progress ─────────────────────────────────────────────────
    with st.expander("**Construction Progress** — sweet spot: 40–85% complete"):
        st.caption(
            "Projects below 40% have too much execution risk. Above 85% may not need AIF capital. "
            "100% complete = no funding gap at all."
        )
        col1, col2 = st.columns(2)
        with col1:
            new_cp_min = st.number_input("Optimal min (%)", value=float(cp["optimal_min"]), step=5.0, key="cp_min")
            new_cp_max = st.number_input("Optimal max (%)", value=float(cp["optimal_max"]), step=5.0, key="cp_max")
        with col2:
            new_cp_below = st.slider("Score below optimal", 0.0, 1.0, float(cp["score_below_optimal"]), 0.05, key="cp_below",
                                      help="Score for projects < optimal_min%")
            new_cp_in = st.slider("Score in optimal range", 0.0, 1.0, float(cp["score_in_optimal"]), 0.05, key="cp_in",
                                   help="Score for projects between optimal_min and optimal_max")
            new_cp_above = st.slider("Score above optimal", 0.0, 1.0, float(cp["score_above_optimal"]), 0.05, key="cp_above",
                                      help="Score for projects > optimal_max but < 100%")
            new_cp_complete = st.slider("Score at 100% complete", 0.0, 1.0, float(cp["score_complete"]), 0.05, key="cp_complete")

    # ── Delay Severity ────────────────────────────────────────────────────────
    with st.expander("**Delay Severity** — moderate delay signals a funding gap"):
        st.caption(
            "No delay means the developer doesn't need help. Extreme delay (>3 yrs) often means the project is stuck. "
            "The sweet spot is 6 months to 2 years overdue — a classic last-mile capital gap."
        )
        col1, col2 = st.columns(2)
        with col1:
            new_ds_mod_min = st.number_input("Moderate delay start (days)", value=int(ds["moderate_delay_min_days"]), step=30, key="ds_modmin")
            new_ds_mod_max = st.number_input("Moderate delay end (days)", value=int(ds["moderate_delay_max_days"]), step=30, key="ds_modmax")
            new_ds_severe_max = st.number_input("Severe delay end (days)", value=int(ds["severe_delay_max_days"]), step=30, key="ds_sevmax")
        with col2:
            new_ds_no = st.slider("No delay score", 0.0, 1.0, float(ds["no_delay_score"]), 0.05, key="ds_no")
            new_ds_mod = st.slider("Moderate delay score", 0.0, 1.0, float(ds["moderate_delay_score"]), 0.05, key="ds_mod")
            new_ds_severe = st.slider("Severe delay score", 0.0, 1.0, float(ds["severe_delay_score"]), 0.05, key="ds_severe")
            new_ds_extreme = st.slider("Extreme delay score (>3 yrs)", 0.0, 1.0, float(ds["extreme_delay_score"]), 0.05, key="ds_extreme")

    # ── Extension History ─────────────────────────────────────────────────────
    with st.expander("**Extension History** — how many deadline extensions the developer has taken"):
        st.caption(
            "0 extensions = no distress signal. 1–2 = classic AIF candidate — used the regulatory safety valve. "
            "3+ = repeatedly troubled, high risk of lapse."
        )
        col1, col2, col3, col4 = st.columns(4)
        new_eh_scores = {}
        for col, n in zip([col1, col2, col3, col4], [0, 1, 2, 3]):
            with col:
                new_eh_scores[n] = st.slider(
                    f"{n} extension{'s' if n != 1 else ''}",
                    0.0, 1.0, float(eh["scores"][n]), 0.05,
                    key=f"eh_{n}",
                )
        new_eh_4plus = st.slider("4+ extensions", 0.0, 1.0, float(eh["four_plus_score"]), 0.05, key="eh_4plus")

    # ── Project Viability ─────────────────────────────────────────────────────
    with st.expander("**Project Viability** — legal status gate (acts as multiplier)"):
        st.caption(
            "⚠️ Viability is a **multiplier**, not an additive factor. "
            "A lapsed project scoring 0.00 here will score 0 overall regardless of construction or location. "
            "Do not set lapsed/deregistered above 0.0 unless you have a specific reason."
        )
        col1, col2 = st.columns(2)
        with col1:
            new_pv_active = st.slider("Active", 0.0, 1.0, float(pv["active_score"]), 0.05, key="pv_active")
            new_pv_completed = st.slider("Completed (no capital need)", 0.0, 1.0, float(pv["completed_score"]), 0.05, key="pv_completed")
            new_pv_abeyance = st.slider("Abeyance", 0.0, 1.0, float(pv["abeyance_score"]), 0.05, key="pv_abeyance")
        with col2:
            new_pv_lapsed = st.slider("Lapsed (hard gate)", 0.0, 0.05, float(pv["lapsed_score"]), 0.01, key="pv_lapsed")
            new_pv_deregistered = st.slider("Deregistered (hard gate)", 0.0, 0.05, float(pv["deregistered_score"]), 0.01, key="pv_dereg")
            new_pv_unknown = st.slider("Unknown status", 0.0, 1.0, float(pv["unknown_score"]), 0.05, key="pv_unknown")

    # ── Location ──────────────────────────────────────────────────────────────
    with st.expander("**Location** — district tier assignment"):
        st.caption(
            "Tier 1 districts have deep buyer demand, liquidity, and established micro-markets. "
            "Tier 2 are growth corridors. Everything else is 'other'."
        )
        col1, col2 = st.columns(2)
        with col1:
            tier1_text = st.text_area(
                "Tier 1 districts (one per line)",
                value="\n".join(loc["tier1_districts"]),
                height=140,
                key="loc_tier1",
            )
            tier2_text = st.text_area(
                "Tier 2 districts (one per line)",
                value="\n".join(loc["tier2_districts"]),
                height=140,
                key="loc_tier2",
            )
        with col2:
            new_loc_t1 = st.slider("Tier 1 score", 0.0, 1.0, float(loc["tier1_score"]), 0.05, key="loc_t1")
            new_loc_t2 = st.slider("Tier 2 score", 0.0, 1.0, float(loc["tier2_score"]), 0.05, key="loc_t2")
            new_loc_other = st.slider("Other districts score", 0.0, 1.0, float(loc["other_score"]), 0.05, key="loc_other")

    # ── Developer Scoring ─────────────────────────────────────────────────────
    with st.expander("**Developer Track Record Weights**"):
        st.caption(
            "These control how the developer's track_record_score (0–100) is computed from portfolio metrics."
        )
        dcols = st.columns(4)
        dw_labels = [
            ("Completion Rate", "completion_rate"),
            ("On-Time Rate", "on_time_rate"),
            ("No-Lapse Rate", "no_lapse_rate"),
            ("Portfolio Size", "portfolio_size"),
        ]
        new_devw = {}
        for col, (label, key) in zip(dcols, dw_labels):
            with col:
                new_devw[key] = st.number_input(
                    label, min_value=0.0, max_value=1.0,
                    value=float(devw[key]), step=0.05, format="%.2f",
                    key=f"dw_{key}",
                )
        dev_total = sum(new_devw.values())
        if abs(dev_total - 1.0) > 0.001:
            st.warning(f"Developer weights sum to **{dev_total:.2f}** — must be 1.00.", icon="⚠️")

    # ── Save Button ───────────────────────────────────────────────────────────
    st.markdown("---")
    col_save, col_reset = st.columns([2, 5])
    with col_save:
        if st.button("💾  Save Scoring Rules", type="primary", use_container_width=True):
            can_save = abs(sum(new_weights.values()) - 1.0) <= 0.001

            if not can_save:
                st.error("Factor weights must sum to 1.00 before saving.")
            else:
                # Build updated rules dict
                updated = {
                    "scoring": {
                        "weights": new_weights,
                        "construction_progress": {
                            "optimal_min": new_cp_min,
                            "optimal_max": new_cp_max,
                            "score_below_optimal": round(new_cp_below, 2),
                            "score_in_optimal": round(new_cp_in, 2),
                            "score_above_optimal": round(new_cp_above, 2),
                            "score_complete": round(new_cp_complete, 2),
                        },
                        "delay_severity": {
                            "no_delay_score": round(new_ds_no, 2),
                            "moderate_delay_min_days": int(new_ds_mod_min),
                            "moderate_delay_max_days": int(new_ds_mod_max),
                            "moderate_delay_score": round(new_ds_mod, 2),
                            "severe_delay_max_days": int(new_ds_severe_max),
                            "severe_delay_score": round(new_ds_severe, 2),
                            "extreme_delay_score": round(new_ds_extreme, 2),
                        },
                        "extension_history": {
                            "scores": {k: round(v, 2) for k, v in new_eh_scores.items()},
                            "four_plus_score": round(new_eh_4plus, 2),
                        },
                        "project_viability": {
                            "active_score": round(new_pv_active, 2),
                            "completed_score": round(new_pv_completed, 2),
                            "lapsed_score": round(new_pv_lapsed, 3),
                            "deregistered_score": round(new_pv_deregistered, 3),
                            "abeyance_score": round(new_pv_abeyance, 2),
                            "unknown_score": round(new_pv_unknown, 2),
                        },
                        "location": {
                            "tier1_districts": [d.strip() for d in tier1_text.splitlines() if d.strip()],
                            "tier2_districts": [d.strip() for d in tier2_text.splitlines() if d.strip()],
                            "tier1_score": round(new_loc_t1, 2),
                            "tier2_score": round(new_loc_t2, 2),
                            "other_score": round(new_loc_other, 2),
                        },
                    },
                    "developer_scoring": {
                        "weights": {k: round(v, 2) for k, v in new_devw.items()},
                        "completion_rate": rules["developer_scoring"]["completion_rate"],
                        "on_time_rate": rules["developer_scoring"]["on_time_rate"],
                        "no_lapse_rate": rules["developer_scoring"]["no_lapse_rate"],
                        "portfolio_size": rules["developer_scoring"]["portfolio_size"],
                    },
                }
                try:
                    _save_scoring_rules(updated)
                    st.success(
                        "✅ **Saved to config/scoring_rules.yaml.** "
                        "Re-run Modules 3–6 to apply the new rules.",
                        icon="💾",
                    )
                except Exception as e:
                    st.error(f"Failed to save: {e}")


# ═════════════════════════════════════════════════════════════════════════════
# TAB 3 — View Report
# ═════════════════════════════════════════════════════════════════════════════

with tab_report:
    st.markdown("## Latest Deal Origination Report")

    report_path = _latest_report_html()

    if not report_path:
        st.info(
            "No report found yet. Run the full pipeline first (▶ Run Pipeline tab).",
            icon="📭",
        )
    else:
        rel = report_path.relative_to(BASE_DIR)
        st.caption(f"Showing: `{rel}`")

        col_open, col_info = st.columns([2, 5])
        with col_open:
            with open(report_path, encoding="utf-8") as f:
                html_bytes = f.read().encode("utf-8")
            st.download_button(
                "⬇  Download HTML",
                data=html_bytes,
                file_name=report_path.name,
                mime="text/html",
                use_container_width=True,
            )
        with col_info:
            st.caption(
                "To export as PDF: open the downloaded HTML in Chrome → File → Print → Save as PDF"
            )

        # --- Summary metrics from JSON sibling
        json_path = report_path.with_suffix(".json")
        if json_path.exists():
            with open(json_path, encoding="utf-8") as f:
                summary_data = json.load(f)
            s = summary_data.get("summary", {})

            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("Scored Projects", s.get("total_projects_scored", "—"))
            m2.metric("Flag for Review", s.get("flag_for_review_count", "—"))
            m3.metric("Monitor", s.get("monitor_count", "—"))
            m4.metric("Pass", s.get("pass_count", "—"))
            m5.metric("Top Score", f"{s.get('max_opportunity_score', 0):.1f} / 100")

        # --- Embedded report
        st.markdown("---")
        with open(report_path, encoding="utf-8") as f:
            html_content = f.read()

        # Scale down the report into an iframe
        import streamlit.components.v1 as components
        components.html(html_content, height=900, scrolling=True)
