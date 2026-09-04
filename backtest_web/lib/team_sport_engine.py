"""
Generic high-scoring team-sport engine (NFL, MLB; NBA deliberately excluded
this pass, see final report). Per spec: higher-scoring sports use
ratings + tree-based + linear (+ Bayesian/neural if time permits) — Poisson
goal models don't fit. This pass runs: Elo (ratings) + Logistic Regression
(linear) + RandomForest (tree). Binary target: home win / not (NFL ties and
MLB ties are exceedingly rare and dropped).
"""
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler


def load_generic(sport: str, data_dir) -> pd.DataFrame:
    f = data_dir / sport / "all_games.csv"
    df = pd.read_csv(f, low_memory=False)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date", "home_team", "away_team", "home_score", "away_score"])
    df = df[df["home_score"] != df["away_score"]]  # drop ties for binary target
    df["result_home_win"] = (df["home_score"] > df["away_score"]).astype(int)
    df = df.sort_values("date").reset_index(drop=True)
    return df


def compute_elo_binary(df, k=20, home_adv=65, base=1500):
    ratings = {}
    out = []
    for row in df.itertuples():
        h, a = row.home_team, row.away_team
        rh = ratings.get(h, base)
        ra = ratings.get(a, base)
        exp_h = 1 / (1 + 10 ** (-((rh + home_adv) - ra) / 400))
        sh = row.result_home_win
        ratings[h] = rh + k * (sh - exp_h)
        ratings[a] = ra + k * ((1 - sh) - (1 - exp_h))
        out.append((rh, ra))
    df = df.copy()
    df["elo_home"], df["elo_away"] = zip(*out)
    df["elo_diff"] = df["elo_home"] - df["elo_away"]
    return df


def elo_prob(elo_diff, home_adv=65):
    return 1 / (1 + 10 ** (-(elo_diff + home_adv) / 400))


FEATURE_COLS = ["elo_diff", "elo_home", "elo_away"]


def temporal_folds(n, n_folds=3, min_train_frac=0.5):
    start = int(n * min_train_frac)
    edges = np.linspace(start, n, n_folds + 1).astype(int)
    folds = []
    for i in range(n_folds):
        train_end, test_end = edges[i], edges[i + 1]
        if train_end >= test_end:
            continue
        fit_end = int(train_end * 0.85)
        folds.append((np.arange(0, fit_end), np.arange(fit_end, train_end), np.arange(train_end, test_end)))
    return folds


def platt_calibrate(raw_calib, y_calib, raw_test):
    from sklearn.linear_model import LogisticRegression as LR
    if len(np.unique(y_calib)) < 2:
        return raw_test
    platt = LR()
    platt.fit(raw_calib.reshape(-1, 1), y_calib)
    return platt.predict_proba(raw_test.reshape(-1, 1))[:, 1]


def run_suite(df: pd.DataFrame, n_folds=3):
    df = compute_elo_binary(df)
    y_all = df["result_home_win"].values
    folds = temporal_folds(len(df), n_folds=n_folds)
    records = {"elo": [], "logreg": [], "random_forest": []}
    for fit_idx, calib_idx, test_idx in folds:
        fit_df, calib_df, test_df = df.iloc[fit_idx], df.iloc[calib_idx], df.iloc[test_idx]
        X_fit, X_calib, X_test = fit_df[FEATURE_COLS].values, calib_df[FEATURE_COLS].values, test_df[FEATURE_COLS].values
        y_fit, y_calib, y_test = fit_df["result_home_win"].values, calib_df["result_home_win"].values, test_df["result_home_win"].values

        # Elo
        try:
            raw_calib = elo_prob(calib_df["elo_diff"].values)
            raw_test = elo_prob(test_df["elo_diff"].values)
            cal = platt_calibrate(raw_calib, y_calib, raw_test)
            for i, r in enumerate(test_df.itertuples()):
                records["elo"].append(_rec(r, cal[i], y_test[i]))
        except Exception:
            pass

        # LogReg
        try:
            scaler = StandardScaler().fit(X_fit)
            clf = LogisticRegression(max_iter=500).fit(scaler.transform(X_fit), y_fit)
            raw_calib = clf.predict_proba(scaler.transform(X_calib))[:, 1]
            raw_test = clf.predict_proba(scaler.transform(X_test))[:, 1]
            cal = platt_calibrate(raw_calib, y_calib, raw_test)
            for i, r in enumerate(test_df.itertuples()):
                records["logreg"].append(_rec(r, cal[i], y_test[i]))
        except Exception:
            pass

        # RandomForest
        try:
            clf = RandomForestClassifier(n_estimators=200, max_depth=5, random_state=42, n_jobs=-1).fit(X_fit, y_fit)
            raw_calib = clf.predict_proba(X_calib)[:, 1]
            raw_test = clf.predict_proba(X_test)[:, 1]
            cal = platt_calibrate(raw_calib, y_calib, raw_test)
            for i, r in enumerate(test_df.itertuples()):
                records["random_forest"].append(_rec(r, cal[i], y_test[i]))
        except Exception:
            pass
    return {m: pd.DataFrame(v) for m, v in records.items() if v}


def _rec(row, p_home, y_true):
    return {"date": row.date, "home": row.home_team, "away": row.away_team,
            "p_home_win": p_home, "y_true": y_true}


def accuracy_logloss_binary(preds):
    p = preds["p_home_win"].values
    y = preds["y_true"].values
    pred_class = (p >= 0.5).astype(int)
    acc = (pred_class == y).mean()
    eps = 1e-12
    ll = -np.mean(y * np.log(np.clip(p, eps, 1)) + (1 - y) * np.log(np.clip(1 - p, eps, 1)))
    return acc, ll


def naive_baseline_binary(preds):
    y = preds["y_true"].values
    majority = int(np.bincount(y).argmax())
    acc = (y == majority).mean()
    eps = 1e-6
    ll = -np.mean(np.log(eps if majority == 0 else 1 - eps) * (y != majority) + np.log(1 - eps) * (y == majority))
    return acc, ll


def calibration_table_binary(preds, buckets=((0.5,0.6),(0.6,0.7),(0.7,0.8),(0.8,1.01))):
    p = np.where(preds["p_home_win"] >= 0.5, preds["p_home_win"], 1 - preds["p_home_win"])
    pred_class = (preds["p_home_win"] >= 0.5).astype(int)
    hit = (pred_class == preds["y_true"]).astype(int).values
    rows = []
    for lo, hi in buckets:
        mask = (p >= lo) & (p < hi)
        n = mask.sum()
        if n == 0:
            rows.append({"bucket": f"{int(lo*100)}-{int(hi*100)}%", "n": 0, "predicted_conf": np.nan, "actual_hit_rate": np.nan, "gap_pts": np.nan})
            continue
        pred_avg = p[mask].mean()
        actual = hit[mask].mean()
        rows.append({"bucket": f"{int(lo*100)}-{min(int(hi*100),100)}%", "n": int(n),
                      "predicted_conf": round(pred_avg*100,1), "actual_hit_rate": round(actual*100,1),
                      "gap_pts": round(abs(pred_avg-actual)*100,1)})
    return pd.DataFrame(rows)
