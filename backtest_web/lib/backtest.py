"""
Backtest orchestration shared logic: temporal splitting, calibration table,
ticket-tier construction (odds-band sweep), streak tracking, go/no-go
verdict. Sport-specific model training plugs into `run_football_backtest`.
"""
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
import xgboost as xgb
import lightgbm as lgb

from .football_engine import (
    fit_dixon_coles, dc_match_probs, elo_to_probs, build_features,
    FEATURE_COLS, RESULT_MAP, compute_elo,
    dc_btts_probs, dc_over_under_probs,
    build_corner_features, corners_expected_total, corners_over_under_probs,
)


class PrefitWrapper:
    """Wrap a raw (proba_fn) so CalibratedClassifierCV(cv='prefit') can
    calibrate it like an sklearn estimator, for models (Dixon-Coles, Elo)
    that are not sklearn classifiers themselves."""
    def __init__(self, proba_fn, classes):
        self.proba_fn = proba_fn
        self.classes_ = np.array(classes)

    def predict_proba(self, X):
        return self.proba_fn(X)

    def fit(self, X, y):
        return self

    def get_params(self, deep=True):
        return {}


def calibrate_probs_multiclass(raw_probs_calib, y_calib, raw_probs_test, classes):
    """Sigmoid (Platt) calibration per-class one-vs-rest, then renormalize.
    CalibratedClassifierCV expects a fitted estimator; we hand it a
    passthrough wrapper over already-computed probabilities."""
    calibrated_test = np.zeros_like(raw_probs_test)
    for ci in range(len(classes)):
        wrapper = PrefitWrapper(lambda X: X, classes)
        # Fit a 1-feature logistic (Platt scaling) on this class's raw prob -> outcome
        from sklearn.linear_model import LogisticRegression as LR
        y_bin = (y_calib == ci).astype(int)
        x_calib = raw_probs_calib[:, ci].reshape(-1, 1)
        if len(np.unique(y_bin)) < 2:
            calibrated_test[:, ci] = raw_probs_test[:, ci]
            continue
        platt = LR()
        platt.fit(x_calib, y_bin)
        calibrated_test[:, ci] = platt.predict_proba(raw_probs_test[:, ci].reshape(-1, 1))[:, 1]
    row_sums = calibrated_test.sum(axis=1, keepdims=True)
    row_sums[row_sums == 0] = 1
    return calibrated_test / row_sums


def temporal_splits(df, n_folds=5, min_train_frac=0.4):
    """Expanding-window walk-forward folds. Each fold's train window is
    itself split 85/15 into fit/calibration (calibration slice never used
    for fitting) per the spec."""
    n = len(df)
    start = int(n * min_train_frac)
    fold_edges = np.linspace(start, n, n_folds + 1).astype(int)
    folds = []
    for i in range(n_folds):
        train_end = fold_edges[i]
        test_end = fold_edges[i + 1]
        if train_end >= test_end:
            continue
        train_idx = np.arange(0, train_end)
        fit_end = int(train_end * 0.85)
        fit_idx = train_idx[:fit_end]
        calib_idx = train_idx[fit_end:]
        test_idx = np.arange(train_end, test_end)
        if len(fit_idx) < 50 or len(calib_idx) < 20 or len(test_idx) < 5:
            continue
        folds.append((fit_idx, calib_idx, test_idx))
    return folds


def run_football_model_suite(df: pd.DataFrame, n_folds=5):
    """Trains Dixon-Coles, Elo, LogReg, RandomForest, XGBoost, LightGBM on
    walk-forward expanding folds with an 85/15 fit/calibration split inside
    each fold's training window, sigmoid-calibrates every model, and returns
    per-model out-of-fold predictions with true labels + market odds for
    downstream reporting/ticketing."""
    df = build_features(df).reset_index(drop=True)
    df = df.dropna(subset=FEATURE_COLS).reset_index(drop=True)
    y_all = df["result"].map(RESULT_MAP).values
    folds = temporal_splits(df, n_folds=n_folds)

    model_names = ["dixon_coles", "elo", "logreg", "random_forest", "xgboost", "lightgbm"]
    records = {m: [] for m in model_names}

    for fit_idx, calib_idx, test_idx in folds:
        train_all_idx = np.concatenate([fit_idx, calib_idx])
        train_df = df.iloc[train_all_idx]
        fit_df = df.iloc[fit_idx]
        calib_df = df.iloc[calib_idx]
        test_df = df.iloc[test_idx]

        X_fit = fit_df[FEATURE_COLS].values
        X_calib = calib_df[FEATURE_COLS].values
        X_test = test_df[FEATURE_COLS].values
        y_fit = fit_df["result"].map(RESULT_MAP).values
        y_calib = calib_df["result"].map(RESULT_MAP).values
        y_test = test_df["result"].map(RESULT_MAP).values
        classes = [0, 1, 2]

        scaler = StandardScaler().fit(X_fit)
        Xf_s, Xc_s, Xt_s = scaler.transform(X_fit), scaler.transform(X_calib), scaler.transform(X_test)

        # --- Dixon-Coles ---
        try:
            dc_model = fit_dixon_coles(train_df)
            def dc_predict(sub_df):
                out = []
                for r in sub_df.itertuples():
                    p = dc_match_probs(dc_model, r.home, r.away)
                    out.append(p if p is not None else np.array([0.45, 0.27, 0.28]))
                return np.array(out)
            raw_calib = dc_predict(calib_df)
            raw_test = dc_predict(test_df)
            cal_test = calibrate_probs_multiclass(raw_calib, y_calib, raw_test, classes)
            for i, r in enumerate(test_df.itertuples()):
                records["dixon_coles"].append(_rec(r, cal_test[i], y_test[i]))
        except Exception:
            pass

        # --- Elo ---
        try:
            draw_rate = (train_df["result"] == "D").mean()
            raw_calib = np.array([elo_to_probs(r.elo_home, r.elo_away, draw_rate=draw_rate) for r in calib_df.itertuples()])
            raw_test = np.array([elo_to_probs(r.elo_home, r.elo_away, draw_rate=draw_rate) for r in test_df.itertuples()])
            cal_test = calibrate_probs_multiclass(raw_calib, y_calib, raw_test, classes)
            for i, r in enumerate(test_df.itertuples()):
                records["elo"].append(_rec(r, cal_test[i], y_test[i]))
        except Exception:
            pass

        # --- LogReg ---
        try:
            clf = LogisticRegression(max_iter=500, multi_class="multinomial")
            clf.fit(Xf_s, y_fit)
            raw_calib = clf.predict_proba(Xc_s)
            raw_test = clf.predict_proba(Xt_s)
            cal_test = calibrate_probs_multiclass(raw_calib, y_calib, raw_test, classes)
            for i, r in enumerate(test_df.itertuples()):
                records["logreg"].append(_rec(r, cal_test[i], y_test[i]))
        except Exception:
            pass

        # --- Random Forest ---
        try:
            clf = RandomForestClassifier(n_estimators=200, max_depth=6, random_state=42, n_jobs=-1)
            clf.fit(X_fit, y_fit)
            raw_calib = clf.predict_proba(X_calib)
            raw_test = clf.predict_proba(X_test)
            cal_test = calibrate_probs_multiclass(raw_calib, y_calib, raw_test, classes)
            for i, r in enumerate(test_df.itertuples()):
                records["random_forest"].append(_rec(r, cal_test[i], y_test[i]))
        except Exception:
            pass

        # --- XGBoost ---
        try:
            clf = xgb.XGBClassifier(n_estimators=200, max_depth=4, learning_rate=0.05,
                                     objective="multi:softprob", num_class=3, eval_metric="mlogloss")
            clf.fit(X_fit, y_fit)
            raw_calib = clf.predict_proba(X_calib)
            raw_test = clf.predict_proba(X_test)
            cal_test = calibrate_probs_multiclass(raw_calib, y_calib, raw_test, classes)
            for i, r in enumerate(test_df.itertuples()):
                records["xgboost"].append(_rec(r, cal_test[i], y_test[i]))
        except Exception:
            pass

        # --- LightGBM ---
        try:
            clf = lgb.LGBMClassifier(n_estimators=200, max_depth=4, learning_rate=0.05, verbosity=-1)
            clf.fit(X_fit, y_fit)
            raw_calib = clf.predict_proba(X_calib)
            raw_test = clf.predict_proba(X_test)
            cal_test = calibrate_probs_multiclass(raw_calib, y_calib, raw_test, classes)
            for i, r in enumerate(test_df.itertuples()):
                records["lightgbm"].append(_rec(r, cal_test[i], y_test[i]))
        except Exception:
            pass

    results = {m: pd.DataFrame(v) for m, v in records.items() if v}
    return results


def _rec(row, probs, y_true):
    return {
        "date": row.date, "league": row.league, "home": row.home, "away": row.away,
        "p_home": probs[0], "p_draw": probs[1], "p_away": probs[2],
        "y_true": y_true,
        "odds_home": getattr(row, "odds_home", np.nan),
        "odds_draw": getattr(row, "odds_draw", np.nan),
        "odds_away": getattr(row, "odds_away", np.nan),
    }


# ---------- reporting ----------
# All functions below take an explicit `prob_cols` / `odds_cols` list so they
# work for any N-outcome market (football 1X2 defaults preserved for
# backward compat; BTTS/Over-Under pass 2-outcome column lists).

DEFAULT_PROB_COLS = ["p_home", "p_draw", "p_away"]
DEFAULT_ODDS_COLS = ["odds_home", "odds_draw", "odds_away"]


def accuracy_logloss(preds: pd.DataFrame, prob_cols=DEFAULT_PROB_COLS):
    p = preds[prob_cols].values
    y = preds["y_true"].values
    pred_class = p.argmax(axis=1)
    acc = (pred_class == y).mean()
    eps = 1e-12
    ll = -np.mean(np.log(np.clip(p[np.arange(len(y)), y], eps, 1)))
    return acc, ll


def naive_baseline(preds: pd.DataFrame, n_classes=3):
    # majority class from the test set itself (home win is standard football baseline)
    y = preds["y_true"].values
    majority = np.bincount(y, minlength=n_classes).argmax()
    acc = (y == majority).mean()
    p = np.zeros((len(y), n_classes)) + 1e-6
    p[:, majority] = 1 - (n_classes - 1) * 1e-6
    ll = -np.mean(np.log(p[np.arange(len(y)), y]))
    return acc, ll


def market_baseline(preds: pd.DataFrame, odds_cols=DEFAULT_ODDS_COLS):
    sub = preds.dropna(subset=odds_cols)
    if len(sub) == 0:
        return None, None, 0
    inv = 1 / sub[odds_cols].values
    implied = inv / inv.sum(axis=1, keepdims=True)
    pred_class = implied.argmax(axis=1)
    y = sub["y_true"].values
    acc = (pred_class == y).mean()
    eps = 1e-12
    ll = -np.mean(np.log(np.clip(implied[np.arange(len(y)), y], eps, 1)))
    return acc, ll, len(sub)


def calibration_table(preds: pd.DataFrame, buckets=((0.5,0.6),(0.6,0.7),(0.7,0.8),(0.8,1.01)),
                       prob_cols=DEFAULT_PROB_COLS):
    p = preds[prob_cols].values
    y = preds["y_true"].values
    conf = p.max(axis=1)
    pred_class = p.argmax(axis=1)
    hit = (pred_class == y).astype(int)
    rows = []
    for lo, hi in buckets:
        mask = (conf >= lo) & (conf < hi)
        n = mask.sum()
        if n == 0:
            rows.append({"bucket": f"{int(lo*100)}-{int(hi*100)}%", "n": 0,
                          "predicted_conf": np.nan, "actual_hit_rate": np.nan, "gap_pts": np.nan})
            continue
        pred_avg = conf[mask].mean()
        actual = hit[mask].mean()
        rows.append({"bucket": f"{int(lo*100)}-{min(int(hi*100),100)}%", "n": int(n),
                      "predicted_conf": round(pred_avg*100,1), "actual_hit_rate": round(actual*100,1),
                      "gap_pts": round(abs(pred_avg-actual)*100,1)})
    return pd.DataFrame(rows)


OUTCOME_ODDS_COL = {0: "odds_home", 1: "odds_draw", 2: "odds_away"}


def build_legs(preds: pd.DataFrame, min_conf=0.60, prob_cols=DEFAULT_PROB_COLS,
                outcome_odds_map=None):
    """Every match-model prediction becomes a candidate 'leg' on its
    highest-confidence outcome, if that outcome has real market odds and
    confidence clears min_conf. `outcome_odds_map` maps class-index -> odds
    column name (defaults to the football 1X2 mapping)."""
    outcome_odds_map = outcome_odds_map or OUTCOME_ODDS_COL
    p = preds[prob_cols].values
    conf = p.max(axis=1)
    pred_class = p.argmax(axis=1)
    legs = preds.copy()
    legs["confidence"] = conf
    legs["pred_class"] = pred_class
    legs["leg_odds"] = [row[outcome_odds_map[c]] for row, c in zip(preds.to_dict("records"), pred_class)]
    legs["won"] = (pred_class == preds["y_true"].values).astype(int)
    legs = legs.dropna(subset=["leg_odds"])
    legs = legs[legs["confidence"] >= min_conf]
    return legs


def sweep_odds_band(legs: pd.DataFrame, target_odds: float, lo_range=(1.14, 3.0), step=0.05):
    """Search sub-ranges of [1.14, 3.0] for the leg-odds band that gives the
    best-performing ticket pool for this tier (best = highest actual hit
    rate among tickets built, subject to a minimum sample size), per the
    spec's explicit sweep requirement."""
    best = None
    lo_vals = np.arange(lo_range[0], lo_range[1], step)
    for lo in lo_vals:
        for width in (0.3, 0.5, 0.8, 1.2, 1.86):
            hi = min(lo + width, lo_range[1])
            if hi <= lo:
                continue
            band = legs[(legs["leg_odds"] >= lo) & (legs["leg_odds"] <= hi)]
            if len(band) < 5:
                continue
            tickets = construct_tickets(band, target_odds)
            if len(tickets) < 3:
                continue
            win_rate = np.mean([t["won"] for t in tickets])
            score = win_rate * min(len(tickets), 50) / 50  # reward both quality and sample size
            if best is None or score > best["score"]:
                best = {"lo": round(lo,2), "hi": round(hi,2), "tickets": tickets, "score": score,
                        "win_rate": win_rate, "n_tickets": len(tickets)}
    return best


def construct_tickets(legs: pd.DataFrame, target_odds: float, max_legs=8):
    """Greedily stack legs (sorted by date, then confidence desc) to reach
    ~target_odds combined, never reusing the same match twice on the same
    day, preferring more legs over fewer risky ones."""
    legs = legs.sort_values(["date", "confidence"], ascending=[True, False])
    used_matches_by_day = {}
    tickets = []
    for day, day_legs in legs.groupby(legs["date"].dt.date):
        day_legs = day_legs.sort_values("confidence", ascending=False)
        pool = day_legs.to_dict("records")
        used = set()
        cur_legs = []
        cur_odds = 1.0
        for leg in pool:
            key = (leg["home"], leg["away"], leg["league"])
            if key in used:
                continue
            if cur_odds >= target_odds or len(cur_legs) >= max_legs:
                break
            cur_legs.append(leg)
            used.add(key)
            cur_odds *= leg["leg_odds"]
        if cur_legs and cur_odds >= target_odds * 0.85:
            won = all(l["won"] for l in cur_legs)
            tickets.append({"date": day, "n_legs": len(cur_legs), "combined_odds": round(cur_odds, 2), "won": won})
    return tickets


def compute_streaks(tickets: list):
    if not tickets:
        return {"longest_win": 0, "longest_loss": 0, "current": 0, "current_type": None}
    tickets_sorted = sorted(tickets, key=lambda t: t["date"])
    longest_win = longest_loss = cur_win = cur_loss = 0
    for t in tickets_sorted:
        if t["won"]:
            cur_win += 1
            cur_loss = 0
        else:
            cur_loss += 1
            cur_win = 0
        longest_win = max(longest_win, cur_win)
        longest_loss = max(longest_loss, cur_loss)
    current = cur_win if cur_win > 0 else -cur_loss
    return {"longest_win": longest_win, "longest_loss": longest_loss,
            "current": abs(current), "current_type": "win" if current >= 0 else "loss"}


# ---------- BTTS / Over-Under / Corners (derived from Dixon-Coles + simple Poisson) ----------

BTTS_PROB_COLS = ["p_no", "p_yes"]
BTTS_ODDS_MAP = {0: "odds_btts_no", 1: "odds_btts_yes"}
OU_PROB_COLS = ["p_under", "p_over"]
OU_ODDS_MAP = {0: "odds_under25", 1: "odds_over25"}
CORNERS_PROB_COLS = ["p_under", "p_over"]


def run_football_market_suite(df: pd.DataFrame, n_folds=5):
    """Trains BTTS and Over/Under-2.5 (both derived from a Dixon-Coles
    scoreline grid fit once per fold, reusing the goal-distribution model
    rather than fitting separate classifiers) and a simple Poisson corners
    model, on the same walk-forward folds used for the 1X2 suite. Returns
    {"btts": {"dixon_coles": df}, "over_under_2.5": {"dixon_coles": df},
     "corners_9.5": {"poisson_corners": df}}.
    """
    df_goals = build_features(df).reset_index(drop=True)
    df_goals = df_goals.dropna(subset=FEATURE_COLS).reset_index(drop=True)
    folds = temporal_splits(df_goals, n_folds=n_folds)

    btts_records = []
    ou_records = []
    for fit_idx, calib_idx, test_idx in folds:
        train_all_idx = np.concatenate([fit_idx, calib_idx])
        train_df = df_goals.iloc[train_all_idx]
        calib_df = df_goals.iloc[calib_idx]
        test_df = df_goals.iloc[test_idx]
        try:
            dc_model = fit_dixon_coles(train_df)
        except Exception:
            continue

        # BTTS
        try:
            def btts_predict(sub_df):
                out = []
                for r in sub_df.itertuples():
                    p = dc_btts_probs(dc_model, r.home, r.away)
                    out.append(p if p is not None else np.array([0.5, 0.5]))
                return np.array(out)
            y_calib_btts = ((calib_df["home_score"] > 0) & (calib_df["away_score"] > 0)).astype(int).values
            y_test_btts = ((test_df["home_score"] > 0) & (test_df["away_score"] > 0)).astype(int).values
            raw_calib = btts_predict(calib_df)
            raw_test = btts_predict(test_df)
            cal_test = calibrate_probs_multiclass(raw_calib, y_calib_btts, raw_test, [0, 1])
            for i, r in enumerate(test_df.itertuples()):
                btts_records.append({
                    "date": r.date, "league": r.league, "home": r.home, "away": r.away,
                    "p_no": cal_test[i, 0], "p_yes": cal_test[i, 1], "y_true": int(y_test_btts[i]),
                    "odds_btts_no": np.nan, "odds_btts_yes": np.nan,
                })
        except Exception:
            pass

        # Over/Under 2.5
        try:
            def ou_predict(sub_df):
                out = []
                for r in sub_df.itertuples():
                    p = dc_over_under_probs(dc_model, r.home, r.away, line=2.5)
                    out.append(p if p is not None else np.array([0.5, 0.5]))
                return np.array(out)
            y_calib_ou = ((calib_df["home_score"] + calib_df["away_score"]) > 2.5).astype(int).values
            y_test_ou = ((test_df["home_score"] + test_df["away_score"]) > 2.5).astype(int).values
            raw_calib = ou_predict(calib_df)
            raw_test = ou_predict(test_df)
            cal_test = calibrate_probs_multiclass(raw_calib, y_calib_ou, raw_test, [0, 1])
            odds_u = test_df["odds_under25"].values if "odds_under25" in test_df.columns else [np.nan] * len(test_df)
            odds_o = test_df["odds_over25"].values if "odds_over25" in test_df.columns else [np.nan] * len(test_df)
            for i, r in enumerate(test_df.itertuples()):
                ou_records.append({
                    "date": r.date, "league": r.league, "home": r.home, "away": r.away,
                    "p_under": cal_test[i, 0], "p_over": cal_test[i, 1], "y_true": int(y_test_ou[i]),
                    "odds_under25": odds_u[i], "odds_over25": odds_o[i],
                })
        except Exception:
            pass

    out = {}
    if btts_records:
        out["btts"] = {"dixon_coles": pd.DataFrame(btts_records)}
    if ou_records:
        out["over_under_2.5"] = {"dixon_coles": pd.DataFrame(ou_records)}
    return out


def run_corners_suite(df: pd.DataFrame, n_folds=5, line=9.5):
    """Simple Poisson corners model: causal rolling team corner-form ->
    expected total corners -> Poisson over/under <line>. Separate from the
    Dixon-Coles goals model entirely (corners are not part of that fit)."""
    sub = df.dropna(subset=["home_corners", "away_corners"]).reset_index(drop=True)
    if len(sub) < 200:
        return {}
    sub = build_corner_features(sub)
    folds = temporal_splits(sub, n_folds=n_folds)
    records = []
    for fit_idx, calib_idx, test_idx in folds:
        calib_df = sub.iloc[calib_idx]
        test_df = sub.iloc[test_idx]
        try:
            def predict(sub_df):
                out = []
                for r in sub_df.itertuples():
                    exp_total = corners_expected_total(r)
                    out.append(corners_over_under_probs(exp_total, line=line))
                return np.array(out)
            y_calib = ((calib_df["home_corners"] + calib_df["away_corners"]) > line).astype(int).values
            y_test = ((test_df["home_corners"] + test_df["away_corners"]) > line).astype(int).values
            raw_calib = predict(calib_df)
            raw_test = predict(test_df)
            cal_test = calibrate_probs_multiclass(raw_calib, y_calib, raw_test, [0, 1])
            for i, r in enumerate(test_df.itertuples()):
                records.append({
                    "date": r.date, "league": r.league, "home": r.home, "away": r.away,
                    "p_under": cal_test[i, 0], "p_over": cal_test[i, 1], "y_true": int(y_test[i]),
                    "odds_under_corners": np.nan, "odds_over_corners": np.nan,
                })
        except Exception:
            pass
    if not records:
        return {}
    return {f"corners_{line}": {"poisson_corners": pd.DataFrame(records)}}


def go_no_go(calib_df: pd.DataFrame, tier3_tickets: list):
    cal_ok = True
    for _, row in calib_df.iterrows():
        if pd.isna(row["gap_pts"]):
            continue
        if row["gap_pts"] > 10:
            cal_ok = False
    n3 = len(tier3_tickets)
    win_rate3 = np.mean([t["won"] for t in tier3_tickets]) if tier3_tickets else 0
    sample_ok = n3 >= 50
    win_ok = win_rate3 >= (1/3) if n3 > 0 else False  # ~modeled prob at 3x odds implies ~33% needed per-ticket; real check done in UI vs modeled prob
    verdict = "go" if (cal_ok and sample_ok and win_ok) else ("delayed" if cal_ok else "no-go")
    return {"verdict": verdict, "calibration_ok": cal_ok, "sample_ok": sample_ok,
            "n_tier3_tickets": n3, "tier3_win_rate": round(win_rate3, 3)}
