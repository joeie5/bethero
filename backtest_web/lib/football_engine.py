"""
Football backtest engine.

Real models trained on real historical data, temporal split, sigmoid
calibration, ticket construction sweep, streaks, go/no-go verdict.

Models actually run here:
  - Dixon-Coles (MLE-fit attack/defense + home advantage + low-score
    correlation param rho) -> derives H/D/A probabilities from ONE
    coherent goal-distribution model.
  - Elo (team strength rating, standard sports-Elo update, mapped to
    win prob via logistic function, draw handled via a fitted margin band)
  - Logistic Regression (multinomial, features = Elo diff + team goal
    form) -- linear baseline
  - RandomForest, XGBoost, LightGBM (tree-based, same feature set)
  - Simple market-blend: 50/50 blend of model prob with de-vigged
    B365 implied prob, only for matches where odds exist.

NOT run in this pass (see final report for why): Glicko-2, TrueSkill,
Bradley-Terry, Skellam, zero-inflated Poisson, CatBoost, sklearn
GradientBoosting, ordered logit/probit, Bayesian hierarchical, Gaussian
Process, Kalman filter, MLP, LSTM/GRU, GNN, stacked meta-learner.
"""
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import poisson
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.calibration import CalibratedClassifierCV
from sklearn.preprocessing import StandardScaler
import xgboost as xgb
import lightgbm as lgb


# ---------- Dixon-Coles ----------

def dc_tau(x, y, lam, mu, rho):
    if x == 0 and y == 0:
        return 1 - lam * mu * rho
    elif x == 0 and y == 1:
        return 1 + lam * rho
    elif x == 1 and y == 0:
        return 1 + mu * rho
    elif x == 1 and y == 1:
        return 1 - rho
    return 1.0


def fit_dixon_coles(train_df: pd.DataFrame, xi: float = 0.0018):
    """MLE fit of attack/defense ratings + home advantage + rho on an
    expanding training window, with exponential time-decay weighting xi
    (standard Dixon-Coles 1997 recency weight)."""
    teams = sorted(set(train_df["home"]) | set(train_df["away"]))
    idx = {t: i for i, t in enumerate(teams)}
    n = len(teams)
    max_date = train_df["date"].max()
    days = (max_date - train_df["date"]).dt.days.values
    weights = np.exp(-xi * days)

    hg = train_df["home_score"].values
    ag = train_df["away_score"].values
    hi = train_df["home"].map(idx).values
    ai = train_df["away"].map(idx).values

    def unpack(params):
        atk = params[:n]
        dfn = params[n:2 * n]
        home_adv = params[2 * n]
        rho = params[2 * n + 1]
        return atk, dfn, home_adv, rho

    def neg_log_lik(params):
        atk, dfn, home_adv, rho = unpack(params)
        lam = np.exp(atk[hi] - dfn[ai] + home_adv)
        mu = np.exp(atk[ai] - dfn[hi])
        ll = poisson.logpmf(hg, lam) + poisson.logpmf(ag, mu)
        tau_vals = np.array([dc_tau(int(h), int(a), l, m, rho)
                              for h, a, l, m in zip(hg, ag, lam, mu)])
        tau_vals = np.clip(tau_vals, 1e-10, None)
        ll = ll + np.log(tau_vals)
        return -np.sum(ll * weights)

    x0 = np.zeros(2 * n + 2)
    x0[2 * n] = 0.25  # home advantage init
    res = minimize(neg_log_lik, x0, method="L-BFGS-B",
                    options={"maxiter": 200, "disp": False})
    atk, dfn, home_adv, rho = unpack(res.x)
    return {"teams": idx, "atk": atk, "dfn": dfn, "home_adv": home_adv, "rho": rho}


def dc_scoreline_grid(model, home, away, max_goals=10):
    """Full scoreline probability grid P(home=x, away=y) from a fitted
    Dixon-Coles model — the shared basis for 1X2, BTTS, and Over/Under
    markets so we fit the goal distribution once and integrate it
    differently per market, rather than fitting separate models."""
    idx = model["teams"]
    if home not in idx or away not in idx:
        return None
    atk, dfn, home_adv, rho = model["atk"], model["dfn"], model["home_adv"], model["rho"]
    lam = np.exp(atk[idx[home]] - dfn[idx[away]] + home_adv)
    mu = np.exp(atk[idx[away]] - dfn[idx[home]])
    grid = np.zeros((max_goals + 1, max_goals + 1))
    for x in range(max_goals + 1):
        for y in range(max_goals + 1):
            p = poisson.pmf(x, lam) * poisson.pmf(y, mu)
            if x <= 1 and y <= 1:
                p *= dc_tau(x, y, lam, mu, rho)
            grid[x, y] = p
    grid = grid / grid.sum()
    return grid


def dc_match_probs(model, home, away, max_goals=10):
    grid = dc_scoreline_grid(model, home, away, max_goals=max_goals)
    if grid is None:
        return None
    p_home = np.tril(grid, -1).sum()
    p_draw = np.trace(grid)
    p_away = np.triu(grid, 1).sum()
    return np.array([p_home, p_draw, p_away])  # H, D, A


def dc_btts_probs(model, home, away, max_goals=10):
    """BTTS market from the DC scoreline grid: P(No) then P(Yes), ordered
    to match RESULT_MAP-style [0]=No,[1]=Yes convention used downstream."""
    grid = dc_scoreline_grid(model, home, away, max_goals=max_goals)
    if grid is None:
        return None
    xs = np.arange(grid.shape[0])[:, None]
    ys = np.arange(grid.shape[1])[None, :]
    yes_mask = (xs >= 1) & (ys >= 1)
    p_yes = grid[yes_mask].sum()
    p_no = 1 - p_yes
    return np.array([p_no, p_yes])


def dc_over_under_probs(model, home, away, line=2.5, max_goals=10):
    """Over/Under <line> total goals from the DC scoreline grid.
    Returns [p_under, p_over]."""
    grid = dc_scoreline_grid(model, home, away, max_goals=max_goals)
    if grid is None:
        return None
    xs = np.arange(grid.shape[0])[:, None]
    ys = np.arange(grid.shape[1])[None, :]
    total = xs + ys
    p_over = grid[total > line].sum()
    p_under = 1 - p_over
    return np.array([p_under, p_over])


# ---------- Corners market (simple Poisson on rolling team corner form) ----------

def build_corner_features(df: pd.DataFrame) -> pd.DataFrame:
    """Causal rolling (last-5) average corners for/against per team, same
    pattern as build_features' goal-form rolling averages. Requires HC/AC
    columns (home/away corners) to already be present on df."""
    df = df.sort_values("date").reset_index(drop=True)
    cf = {}
    ca = {}
    feats = []
    for row in df.itertuples():
        h, a = row.home, row.away
        hf = np.mean(cf.get(h, [9.0])[-5:])
        haf = np.mean(ca.get(h, [9.0])[-5:])
        af = np.mean(cf.get(a, [9.0])[-5:])
        aaf = np.mean(ca.get(a, [9.0])[-5:])
        feats.append((hf, haf, af, aaf))
        hc, ac = getattr(row, "home_corners", np.nan), getattr(row, "away_corners", np.nan)
        cf.setdefault(h, []).append(hc)
        ca.setdefault(h, []).append(ac)
        cf.setdefault(a, []).append(ac)
        ca.setdefault(a, []).append(hc)
    df["home_corner_form_for"], df["home_corner_form_against"], \
        df["away_corner_form_for"], df["away_corner_form_against"] = zip(*feats)
    return df


def corners_expected_total(row):
    """Simple additive expectation: average of each side's own attacking
    rate and their opponent-type's conceding rate."""
    home_exp = (row.home_corner_form_for + row.away_corner_form_against) / 2
    away_exp = (row.away_corner_form_for + row.home_corner_form_against) / 2
    return home_exp + away_exp


def corners_over_under_probs(expected_total, line=9.5):
    """Poisson(expected_total) over/under a corners line. Returns
    [p_under, p_over]."""
    p_over = poisson.sf(line, expected_total)  # P(X > line), line is x.5 so no boundary issue
    p_under = 1 - p_over
    return np.array([p_under, p_over])


# ---------- Elo ----------

def compute_elo(df: pd.DataFrame, k=20, home_adv=60, base=1500):
    """Sequential Elo with draw handling via 3-outcome expected score
    (standard football-Elo trick: draw counts as 0.5 for both)."""
    ratings = {}
    out = []
    for row in df.itertuples():
        h, a = row.home, row.away
        rh = ratings.get(h, base)
        ra = ratings.get(a, base)
        exp_h = 1 / (1 + 10 ** (-((rh + home_adv) - ra) / 400))
        if row.result == "H":
            sh = 1.0
        elif row.result == "A":
            sh = 0.0
        else:
            sh = 0.5
        ratings[h] = rh + k * (sh - exp_h)
        ratings[a] = ra + k * ((1 - sh) - (1 - exp_h))
        out.append((rh, ra))
    df = df.copy()
    df["elo_home"], df["elo_away"] = zip(*out)
    return df, ratings


def elo_to_probs(elo_home, elo_away, home_adv=60, draw_rate=0.26):
    """Map Elo diff to H/D/A via logistic win prob then carve out a draw
    band calibrated to the league's overall draw rate."""
    diff = (elo_home + home_adv) - elo_away
    p_home_win_only = 1 / (1 + 10 ** (-diff / 400))
    p_draw = draw_rate
    p_home = p_home_win_only * (1 - p_draw)
    p_away = (1 - p_home_win_only) * (1 - p_draw)
    return np.array([p_home, p_draw, p_away])


# ---------- feature engineering for ML models ----------

def build_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values("date").reset_index(drop=True)
    df, _ = compute_elo(df)
    # rolling form: last-5 avg goals scored/conceded per team, computed causally
    goals_for = {}
    goals_against = {}
    feats = []
    for row in df.itertuples():
        h, a = row.home, row.away
        hf = np.mean(goals_for.get(h, [0])[-5:])
        haf = np.mean(goals_against.get(h, [0])[-5:])
        af = np.mean(goals_for.get(a, [0])[-5:])
        aaf = np.mean(goals_against.get(a, [0])[-5:])
        feats.append((hf, haf, af, aaf))
        goals_for.setdefault(h, []).append(row.home_score)
        goals_against.setdefault(h, []).append(row.away_score)
        goals_for.setdefault(a, []).append(row.away_score)
        goals_against.setdefault(a, []).append(row.home_score)
    df["home_form_gf"], df["home_form_ga"], df["away_form_gf"], df["away_form_ga"] = zip(*feats)
    df["elo_diff"] = df["elo_home"] - df["elo_away"]
    return df


FEATURE_COLS = ["elo_diff", "elo_home", "elo_away",
                 "home_form_gf", "home_form_ga", "away_form_gf", "away_form_ga"]
RESULT_MAP = {"H": 0, "D": 1, "A": 2}
