"""
Bet Hero — Backtest Validation Tool (Prompt 2, cache-reader revision)

Standalone, offline go/no-go gate: does this sport's prediction pipeline
actually work on real historical data? Not a production feature.

IMPORTANT: this app trains NOTHING live. All results are pre-computed by
`run_all_backtests.py` (run offline / on a schedule, not on request) and
written to results_cache/. This file only reads that cache. If you find
yourself wiring a st.button to a live .fit() call, stop — that's the exact
anti-pattern this revision removes (live training on the VPS's 1.6GB RAM
previously hung/crashed the app).
"""
import warnings
warnings.filterwarnings("ignore")

import json
import streamlit as st
import pandas as pd
from pathlib import Path

from lib import sync_data

st.set_page_config(page_title="Bet Hero — Backtest Gate", layout="wide")

ROOT = Path(__file__).parent
CACHE_DIR = ROOT / "results_cache"
FOOTBALL_CACHE = CACHE_DIR / "football"

SPORT_STATUS = {
    "Football": "ready",
    "Basketball (NBA)": "not_attempted",
    "NFL": "not_attempted",
    "MLB": "not_attempted",
    "Tennis (ATP/WTA)": "not_attempted",
    "Cricket": "not_attempted",
}

MARKET_LABELS = {
    "1x2": "1X2 (match result)",
    "btts": "Both Teams to Score",
    "over_under_2.5": "Over/Under 2.5 Goals",
    "corners_9.5": "Corners Over/Under 9.5",
}

st.title("Bet Hero — Backtest Validation Gate")
st.caption(
    "Offline go/no-go tool. All verdicts below are pre-computed by an offline batch "
    "job (`run_all_backtests.py`) from real historical data — this page reads cached "
    "results only. Nothing is trained live when you use these controls."
)

with st.sidebar:
    st.header("Controls")
    if st.button("Sync raw data from Supabase Storage"):
        with st.spinner("Syncing..."):
            res = sync_data.sync_all()
        st.success("Synced. Note: this only refreshes data/ — it does NOT retrain models. "
                    "Run `python run_all_backtests.py` offline, then redeploy, to pick up new data.")
        st.json({k: (len(v) if isinstance(v, list) else v) for k, v in res.items()})

    st.markdown("---")
    manifest_path = FOOTBALL_CACHE / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        st.caption(f"Cache generated: {manifest.get('generated_at', '?')}")
        st.caption(f"Leagues trained: {len(manifest.get('leagues_trained', []))}")
    else:
        manifest = None
        st.warning("No results_cache/football/manifest.json found — run "
                   "`python run_all_backtests.py` offline first.")


def list_leagues():
    if not FOOTBALL_CACHE.exists():
        return []
    return sorted(p.name for p in FOOTBALL_CACHE.iterdir() if p.is_dir())


def list_models(league):
    d = FOOTBALL_CACHE / league
    if not d.exists():
        return []
    return sorted(p.name for p in d.iterdir() if p.is_dir())


def list_markets(league, model):
    d = FOOTBALL_CACHE / league / model
    if not d.exists():
        return []
    return sorted(p.name for p in d.iterdir() if p.is_dir())


def load_result(league, model, market):
    d = FOOTBALL_CACHE / league / model / market
    if not (d / "verdict.json").exists():
        return None
    verdict = json.loads((d / "verdict.json").read_text())
    calibration = pd.DataFrame(json.loads((d / "calibration.json").read_text()))
    tickets = json.loads((d / "tickets.json").read_text())
    return {"verdict": verdict, "calibration": calibration, "tickets": tickets}


st.markdown("### Go / No-Go status — all sports")
cols = st.columns(len(SPORT_STATUS))
for c, (sport, status) in zip(cols, SPORT_STATUS.items()):
    with c:
        if status == "ready":
            st.info(f"○ {sport}: pick League/Model/Market ->")
        else:
            st.warning(f"⏱ {sport}: not attempted this pass")

st.markdown("---")
st.header("Football")

leagues = list_leagues()
if not leagues:
    st.error("No cached football results found. Run `python run_all_backtests.py` "
             "offline (see repo root), then redeploy this app.")
else:
    c1, c2, c3 = st.columns(3)
    with c1:
        league_pick = st.selectbox("League", leagues)
    models = list_models(league_pick) if league_pick else []
    with c2:
        model_pick = st.selectbox("Model", models)
    markets = list_markets(league_pick, model_pick) if model_pick else []
    with c3:
        market_pick = st.selectbox(
            "Market", markets,
            format_func=lambda m: MARKET_LABELS.get(m, m),
        )

    if league_pick and model_pick and market_pick:
        result = load_result(league_pick, model_pick, market_pick)
        if result is None:
            st.error("No cached result for this combination.")
        else:
            verdict = result["verdict"]
            cal = result["calibration"]
            tickets = result["tickets"]

            c1, c2, c3 = st.columns(3)
            c1.metric("# matches (test folds)", f"{verdict['n_matches']:,}")
            c2.metric("# legs clearing min-confidence (60%)", f"{verdict['n_legs_min_conf']:,}")
            c3.metric("Calibration", "OK" if verdict["calibration_ok"] else "FAILED")

            st.subheader("Calibration table (most important table in this tool)")
            st.dataframe(cal, use_container_width=True)
            max_gap = cal["gap_pts"].max(skipna=True)
            if verdict["calibration_ok"]:
                st.success(f"Calibration OK — worst bucket gap {max_gap:.1f} pts (bar: ≤10)" if pd.notna(max_gap)
                           else "Calibration OK — no buckets had data")
            else:
                st.error(f"Calibration FAILED — worst bucket gap {max_gap:.1f} pts (bar: ≤10)")

            st.subheader("Ticket tiers (3x / 5x / 10x) — best odds-band found (swept 1.14-3.0)")
            tcols = st.columns(3)
            for tcol, target in zip(tcols, ["3", "5", "10"]):
                with tcol:
                    st.markdown(f"**{target}x tier**")
                    tier = tickets.get(target, {})
                    n = tier.get("n_tickets", 0)
                    if not n or n < 5:
                        st.warning(f"⚠ Too few tickets built for the {target}x tier "
                                   f"({n} tickets). This is itself a finding, not hidden.")
                    else:
                        st.metric("Tickets built", n)
                        st.metric("Win rate", f"{tier['win_rate']*100:.1f}%")
                        st.caption(f"Best band found: {tier['band'][0]}–{tier['band'][1]}")
                        streak = tier["streaks"]
                        st.caption(f"Longest win streak: {streak['longest_win']} | "
                                   f"Longest loss streak: {streak['longest_loss']} | "
                                   f"Current: {streak['current']} {streak['current_type'] or ''}")

            st.subheader(f"Go / No-Go verdict — Football / {league_pick} / {model_pick} / {MARKET_LABELS.get(market_pick, market_pick)}")
            v = verdict["verdict"]
            if v == "go":
                st.success(f"✓ READY TO LAUNCH — calibration OK, {verdict['n_tier3_tickets']} tickets at 3x odds, "
                           f"win rate {verdict['tier3_win_rate']*100:.1f}%")
            elif v == "delayed":
                st.warning(f"⏱ NEEDS MORE DATA — calibration OK but sample/win-rate bar not cleared "
                           f"(n={verdict['n_tier3_tickets']}, win rate {verdict['tier3_win_rate']*100:.1f}%)")
            else:
                st.error("✗ FAILED CALIBRATION — do not launch this league/model/market combo")

st.markdown("---")
st.subheader("Sports not attempted this pass")
st.write("Basketball (NBA), NFL, MLB, Tennis (ATP/WTA), Cricket — see final report for status "
         "(time-boxed prioritization: football built fully first per the working method).")
