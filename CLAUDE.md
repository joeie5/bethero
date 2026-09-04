# BetHero — Claude Code Project Brief

Save this as CLAUDE.md in the repo root before starting a session, or paste it as the first message. It consolidates everything decided across a full night of rigorous backtesting into the constraints and task list needed to actually build this. Read the whole thing before writing any code — the constraints in Section 1 override anything that looks like a shortcut later.

## 1. HARD CONSTRAINTS — violating any of these invalidates the entire pipeline

These aren't preferences. Each one exists because breaking it produced a real, measured failure tonight.

### 1.1 — No post-match statistic may ever be a same-match input feature

A reviewed (never-executed) training script left FTHG, FTAG, HC, AC, etc. in as model features while predicting outcomes derived from those same columns — the model would have been trained to find the answer already sitting in its own inputs.

These columns may only be used as (a) the label itself, or (b) input to a rolling average computed strictly from matches before the one being predicted. Never as a same-match feature:

`FTHG, FTAG, HTHG, HTAG, HTR, HS, AS, HST, AST, HC, AC, HY, AY, HR, AR`

Every feature-preparation function must explicitly exclude this full list, not just the label columns. Write a unit test that asserts none of these column names appear in the final feature set passed to `model.fit()`.

### 1.2 — Every model requires temporal-split calibration. No exceptions.

An uncalibrated model tested tonight claimed 84% confidence while being right 45% of the time. The required pattern, for every model, every market, every sport:

- Walk-forward retrain on an expanding window (quarterly cadence validated tonight)
- Hold out the last ~15% of each training window purely for calibration — never used for fitting
- Fit sigmoid (Platt) calibration on that held-out slice
- For count-based markets (corners, cards) specifically: use Negative Binomial, not Poisson — both showed real overdispersion (variance/mean ratios of 1.21 and 1.29, confirmed against real data). Re-estimate the dispersion parameter from only prior data at each retrain.

Verification: after training, print a calibration table (predicted-confidence bucket vs actual hit rate) for every model. No bucket should be more than ~10 points off. If it is, the model does not proceed to ticket-building.

### 1.3 — Two-sided market evaluation, not one fixed direction

Locking a market to one direction (e.g., only ever checking BTTS "Yes") silently discards genuinely valuable picks on the other side. Every match must have both sides of every applicable market evaluated, and the higher-confidence side selected — not a hardcoded convention.

Exception, decided deliberately: Corners uses two separate, asymmetric lines (Over 7.5 and Under 9.5) rather than two-sided evaluation of one line — a single-line two-sided test showed "Under" essentially never wins at 7.5 because the line is too easy to clear, so two distinct thresholds are used instead.

### 1.4 — Ticket tiers must enforce real leg count, not just target odds

A "3-odds" Goals ticket was found stacking 5–10 legs to reach its target odds while still being labeled 3-odds. Every tier construction must check and report actual leg count, not assume it from the odds target.

### 1.5 — 3-odds (2-4 legs) is the only currently-validated tier. 5-odds and 10-odds are gated.

Every market and construction method tested tonight — real market-priced tickets, model-derived tickets, single-market isolation, multi-market blends — degraded past 4 legs and became unreliable by 10, without exception. This is compounding probability math, not a fixable selection-quality problem: a genuinely good 70%-accurate leg still only compounds to 17% at 5 legs.

Do not ship 5-odds or 10-odds to real users just because a deadline arrived. They stay behind the go/no-go bar in Section 4 regardless of timeline pressure. The one exception worth prioritizing: Corners@7.5 in isolation produced a real, calibrated 10-odds sample (96 tickets, 10.4% actual vs 8.2% modeled) — seed that tier from Corners specifically rather than a diluted multi-market blend.

### 1.6 — Market-diversity cap: max 2 legs of the same market per ticket

Without this, an uncalibrated or simply high-volume market will dominate ticket construction — confirmed directly (one market took 53.6% of all picked legs before this cap was added). Enforce in every accumulator-building path.

## 2. Exact markets and lines — final, decided scope

| Market | Selections | Model |
|---|---|---|
| BTTS | Yes, No | Two-sided, calibrated classifier |
| Goals | Over 1.5, Over 2.5, Under 3.5 | Dixon-Coles derived, edge-based selection across the three lines — not raw-confidence selection, which was tested and found to always collapse to the safest extreme, never using the 2.5 line |
| Corners | Over 7.5, Under 9.5 | Negative Binomial + Platt calibration, per line, walk-forward |
| Cards | Over 3.5, Under 3.5 | Negative Binomial + Platt calibration — must pass its own isolation test (Section 4) before inclusion; it caused real harm uncalibrated tonight |

## 3. What's fixed vs what's new — codebase state

A prior audit found `app/ml/` had never successfully executed (every import pointed at the wrong path — `app.feature_engineer` instead of `app.ml.feature_engineer`), `app/services/accumulator_builder.py` contained a leaked API key and duplicated prediction logic with a hand-built feature array mismatched to what the model was actually trained on, and `app/routers/admin.py` had zero authentication on destructive endpoints.

Task order:

1. Fix the import paths across `app/ml/` (`feature_engineer.py`, `predictor.py`, `feature_store.py`, `training_pipeline_logic.py`)
2. Delete `app/services/accumulator_builder.py` entirely — rotate the leaked key if not already done. One prediction path only, in `app/ml/`.
3. Add `feature_names` to `EnsembleModel.save()` — `predictor.py` already checks for this artifact but nothing writes it
4. Rewrite every query in `TrainingDataLoader`/`predictor.py` against the live schema (`fixtures`, `match_results`, `team_form_cache`, `predictions`) — not the abandoned `matches`/`match_feature_cache` tables
5. Add auth dependency to `app/routers/admin.py` before this is reachable on the VPS
6. Fix `match_id: int → str` everywhere — the schema uses composite `(sport, fixture_id)` text keys

## 4. Go/No-Go gate — required before anything reaches a real user

Per market, per sport:

- Calibration table: no bucket more than ~10 points off
- 3-odds: real sample (50+ tickets), actual win rate at or above modeled
- Cards specifically: must clear this bar in isolation (its own standalone 3/5/10-odds test), not only as part of a pooled blend — pooling is exactly what let it dominate silently before anyone checked its composition

Anything that doesn't clear the bar goes on an explicit "delayed" list. Surface it, don't bury it in an otherwise-green report.

## 5. Historical data sourcing — 27 leagues, two tiers, verify don't assume

**Main tier** (proven precedent — this is what tonight's testing used): England, Scotland, Germany, Italy, Spain, France, Netherlands, Belgium, Portugal, Turkey, Greece. Season-by-season files, multiple divisions, deep bookmaker/stats coverage, from football-data.co.uk's primary league pages.

**Extra tier** (structurally different, depth unconfirmed): Argentina, Austria, Brazil, China, Denmark, Finland, Ireland, Japan, Mexico, Norway, Poland, Romania, Russia, Sweden, Switzerland, USA. Single combined file per country from football-data.co.uk's newer "extra leagues" section. Do not assume these have the same corners/cards/multi-bookmaker columns as the Main tier — verify each country's actual column set on first ingestion, and run each through Section 4's gate independently. A thin Extra-tier country might only support 1X2 prediction, not the full market set in Section 2.

**Other sports** (tennis, cricket, NBA/NFL/MLB/NHL): sourcing already confirmed — tennis-data.co.uk, Cricsheet.org, nba_api/nfl_data_py/pybaseball, historical odds via SportsbookReviewsOnline or Kaggle. Cricket specifically: re-source from Cricsheet's full ball-by-ball data — an earlier pull used a stripped-down file with no score data at all, and that's a sourcing gap, not an inherent cricket data limitation.

## 6. Deployment — VPS, Docker already installed

Four services: `api` (FastAPI), `worker` (APScheduler — not Celery, the old render.yaml referenced a worker that never existed), `backtest-web` (Streamlit, runs fully offline against local CSVs, no live API dependency), `redis` (local, caching + rate-limit tracking via the existing `api_key_usage` table). Database is the already-live Supabase project — service role key from `.env`, no local Postgres. All ports bound to 127.0.0.1, SSH tunnel access only until real auth is in front of it.

Sequencing: the backtest webapp runs first, against every sport/league with available data, this week. Only sports/leagues that clear Section 4's gate get wired into live ingestion and ticket generation. The season deadline does not override this order.

## 7. First action

Before writing any implementation code: read `app/ml/feature_engineer.py`, `app/ml/predictor.py`, and `app/services/accumulator_builder.py` as they currently exist in the repo, and confirm in writing which of Section 1's constraints each one currently violates. Fix Section 3's task list before touching Section 2's market logic — the market spec is worthless on top of a feature-leakage run.
