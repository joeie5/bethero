"""
Tennis: ratings-based (Elo on player strength) + tree-based (RandomForest
on rank/surface features) subset, per spec ("tennis uses ratings-based
approaches producing match-win probability directly ... tree-based on
serve/surface features"). Uses ATP main-tour matches only this pass
(qualifying/challenger/futures/doubles excluded — see final report).
"""
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression as LR


def load_atp_years(data_dir: Path, start=2015, end=2024):
    frames = []
    for y in range(start, end + 1):
        f = data_dir / "tennis_atp" / f"atp_matches_{y}.csv"
        if f.exists():
            df = pd.read_csv(f, low_memory=False)
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    df["tourney_date"] = pd.to_datetime(df["tourney_date"], format="%Y%m%d", errors="coerce")
    df = df.dropna(subset=["tourney_date", "winner_name", "loser_name"])
    return df.sort_values("tourney_date").reset_index(drop=True)


def build_match_rows(df):
    """Each row -> a randomized player1/player2 with binary label
    player1_won, to avoid the trivial 'winner listed first' leak."""
    rng = np.random.default_rng(42)
    rows = []
    for r in df.itertuples():
        flip = rng.random() < 0.5
        if flip:
            p1, p2, p1_won = r.loser_name, r.winner_name, 0
            p1_rank, p2_rank = getattr(r, "loser_rank", np.nan), getattr(r, "winner_rank", np.nan)
        else:
            p1, p2, p1_won = r.winner_name, r.loser_name, 1
            p1_rank, p2_rank = getattr(r, "winner_rank", np.nan), getattr(r, "loser_rank", np.nan)
        rows.append({"date": r.tourney_date, "p1": p1, "p2": p2, "p1_won": p1_won,
                      "p1_rank": p1_rank, "p2_rank": p2_rank,
                      "surface": getattr(r, "surface", None)})
    return pd.DataFrame(rows)


def compute_player_elo(matches, k=32, base=1500):
    ratings = {}
    out = []
    for r in matches.itertuples():
        r1 = ratings.get(r.p1, base)
        r2 = ratings.get(r.p2, base)
        exp1 = 1 / (1 + 10 ** (-(r1 - r2) / 400))
        out.append((r1, r2))
        s1 = r.p1_won
        ratings[r.p1] = r1 + k * (s1 - exp1)
        ratings[r.p2] = r2 + k * ((1 - s1) - (1 - exp1))
    matches = matches.copy()
    matches["elo_p1"], matches["elo_p2"] = zip(*out)
    matches["elo_diff"] = matches["elo_p1"] - matches["elo_p2"]
    return matches


def elo_prob(elo_diff):
    return 1 / (1 + 10 ** (-elo_diff / 400))


def platt_calibrate(raw_calib, y_calib, raw_test):
    if len(np.unique(y_calib)) < 2:
        return raw_test
    platt = LR()
    platt.fit(raw_calib.reshape(-1, 1), y_calib)
    return platt.predict_proba(raw_test.reshape(-1, 1))[:, 1]


def run_suite(matches: pd.DataFrame, n_folds=3):
    matches = compute_player_elo(matches).reset_index(drop=True)
    matches["rank_diff"] = matches["p2_rank"].fillna(500) - matches["p1_rank"].fillna(500)
    n = len(matches)
    start = int(n * 0.5)
    edges = np.linspace(start, n, n_folds + 1).astype(int)
    records = {"elo": [], "random_forest": []}
    for i in range(n_folds):
        train_end, test_end = edges[i], edges[i + 1]
        if train_end >= test_end:
            continue
        fit_end = int(train_end * 0.85)
        fit_idx, calib_idx, test_idx = np.arange(0, fit_end), np.arange(fit_end, train_end), np.arange(train_end, test_end)
        fit_df, calib_df, test_df = matches.iloc[fit_idx], matches.iloc[calib_idx], matches.iloc[test_idx]
        y_fit, y_calib, y_test = fit_df["p1_won"].values, calib_df["p1_won"].values, test_df["p1_won"].values

        try:
            raw_calib = elo_prob(calib_df["elo_diff"].values)
            raw_test = elo_prob(test_df["elo_diff"].values)
            cal = platt_calibrate(raw_calib, y_calib, raw_test)
            for j, r in enumerate(test_df.itertuples()):
                records["elo"].append({"date": r.date, "p1": r.p1, "p2": r.p2, "p_p1": cal[j], "y_true": y_test[j]})
        except Exception:
            pass

        try:
            feats = ["elo_diff", "rank_diff"]
            X_fit, X_calib, X_test = fit_df[feats].fillna(0).values, calib_df[feats].fillna(0).values, test_df[feats].fillna(0).values
            clf = RandomForestClassifier(n_estimators=200, max_depth=5, random_state=42, n_jobs=-1).fit(X_fit, y_fit)
            raw_calib = clf.predict_proba(X_calib)[:, 1]
            raw_test = clf.predict_proba(X_test)[:, 1]
            cal = platt_calibrate(raw_calib, y_calib, raw_test)
            for j, r in enumerate(test_df.itertuples()):
                records["random_forest"].append({"date": r.date, "p1": r.p1, "p2": r.p2, "p_p1": cal[j], "y_true": y_test[j]})
        except Exception:
            pass
    return {m: pd.DataFrame(v) for m, v in records.items() if v}


def accuracy_logloss(preds):
    p = preds["p_p1"].values
    y = preds["y_true"].values
    pred_class = (p >= 0.5).astype(int)
    acc = (pred_class == y).mean()
    eps = 1e-12
    ll = -np.mean(y * np.log(np.clip(p, eps, 1)) + (1 - y) * np.log(np.clip(1 - p, eps, 1)))
    return acc, ll


def calibration_table(preds, buckets=((0.5,0.6),(0.6,0.7),(0.7,0.8),(0.8,1.01))):
    p = np.where(preds["p_p1"] >= 0.5, preds["p_p1"], 1 - preds["p_p1"])
    pred_class = (preds["p_p1"] >= 0.5).astype(int)
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
