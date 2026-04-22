"""
Seed bet_results with mock data for local UI testing.

Usage:
  source .env.local && python seed_mock_data.py          # insert mock rows
  source .env.local && python seed_mock_data.py --reset  # wipe table first, then insert
"""

import sys
from datetime import date, timedelta

import pandas as pd
from dotenv import load_dotenv

load_dotenv(".env.local")

import db  # noqa: E402

# ── Mock rows ─────────────────────────────────────────────────────────────────
# Spread across 4 dates: 3 settled, 1 pending (today)
# Covers: both sides, 3 books, various lines, 3 edge buckets

TODAY = date.today()

MOCK_BETS = [
    # ── 3 days ago — all settled ──────────────────────────────────────────────
    dict(game_date=TODAY - timedelta(days=3), pitcher_id=592789, pitcher_name="Gerrit Cole",
         bookmaker_key="fanduel",  line=6.5, side="Over",  odds_american=-115,
         kelly_pct=0.031, stake_units=1.0, result="win",  profit_units=0.87,
         edge_pct=0.082, model_prob=0.63),

    dict(game_date=TODAY - timedelta(days=3), pitcher_id=605483, pitcher_name="Dylan Cease",
         bookmaker_key="fanatics", line=5.5, side="Over",  odds_american=-110,
         kelly_pct=0.045, stake_units=1.5, result="loss", profit_units=-1.5,
         edge_pct=0.051, model_prob=0.58),

    dict(game_date=TODAY - timedelta(days=3), pitcher_id=669923, pitcher_name="Spencer Strider",
         bookmaker_key="betrivers", line=7.5, side="Over", odds_american=120,
         kelly_pct=0.038, stake_units=1.0, result="win",  profit_units=1.20,
         edge_pct=0.094, model_prob=0.67),

    dict(game_date=TODAY - timedelta(days=3), pitcher_id=641154, pitcher_name="Zac Gallen",
         bookmaker_key="fanduel",  line=4.5, side="Under", odds_american=-130,
         kelly_pct=0.033, stake_units=1.0, result="loss", profit_units=-1.0,
         edge_pct=0.041, model_prob=0.59),

    # ── 2 days ago — all settled ──────────────────────────────────────────────
    dict(game_date=TODAY - timedelta(days=2), pitcher_id=543037, pitcher_name="Max Scherzer",
         bookmaker_key="fanatics", line=5.5, side="Over",  odds_american=-105,
         kelly_pct=0.052, stake_units=2.0, result="win",  profit_units=1.90,
         edge_pct=0.087, model_prob=0.65),

    dict(game_date=TODAY - timedelta(days=2), pitcher_id=554430, pitcher_name="Clayton Kershaw",
         bookmaker_key="fanduel",  line=4.5, side="Over",  odds_american=-120,
         kelly_pct=0.034, stake_units=1.0, result="win",  profit_units=0.83,
         edge_pct=0.044, model_prob=0.57),

    dict(game_date=TODAY - timedelta(days=2), pitcher_id=656302, pitcher_name="Logan Webb",
         bookmaker_key="betrivers", line=5.5, side="Over", odds_american=-108,
         kelly_pct=0.041, stake_units=1.5, result="loss", profit_units=-1.5,
         edge_pct=0.063, model_prob=0.60),

    dict(game_date=TODAY - timedelta(days=2), pitcher_id=663158, pitcher_name="Kevin Gausman",
         bookmaker_key="fanatics", line=6.5, side="Under", odds_american=-112,
         kelly_pct=0.036, stake_units=1.0, result="push", profit_units=0.0,
         edge_pct=0.055, model_prob=0.61),

    dict(game_date=TODAY - timedelta(days=2), pitcher_id=592332, pitcher_name="Chris Sale",
         bookmaker_key="fanduel",  line=7.5, side="Over",  odds_american=115,
         kelly_pct=0.029, stake_units=0.75, result="win", profit_units=0.86,
         edge_pct=0.091, model_prob=0.66),

    # ── Yesterday — all settled ───────────────────────────────────────────────
    dict(game_date=TODAY - timedelta(days=1), pitcher_id=477132, pitcher_name="Justin Verlander",
         bookmaker_key="betrivers", line=5.5, side="Over", odds_american=-110,
         kelly_pct=0.048, stake_units=1.5, result="win",  profit_units=1.36,
         edge_pct=0.079, model_prob=0.64),

    dict(game_date=TODAY - timedelta(days=1), pitcher_id=621111, pitcher_name="Corbin Burnes",
         bookmaker_key="fanduel",  line=6.5, side="Over",  odds_american=-118,
         kelly_pct=0.055, stake_units=2.0, result="win",  profit_units=1.69,
         edge_pct=0.103, model_prob=0.68),

    dict(game_date=TODAY - timedelta(days=1), pitcher_id=664285, pitcher_name="Hunter Greene",
         bookmaker_key="fanatics", line=6.5, side="Over",  odds_american=-105,
         kelly_pct=0.039, stake_units=1.0, result="loss", profit_units=-1.0,
         edge_pct=0.046, model_prob=0.58),

    dict(game_date=TODAY - timedelta(days=1), pitcher_id=657277, pitcher_name="Framber Valdez",
         bookmaker_key="betrivers", line=4.5, side="Over", odds_american=-125,
         kelly_pct=0.031, stake_units=1.0, result="loss", profit_units=-1.0,
         edge_pct=0.035, model_prob=0.55),

    dict(game_date=TODAY - timedelta(days=1), pitcher_id=605400, pitcher_name="Sandy Alcantara",
         bookmaker_key="fanduel",  line=5.5, side="Under", odds_american=-102,
         kelly_pct=0.044, stake_units=1.5, result="win",  profit_units=1.47,
         edge_pct=0.071, model_prob=0.62),

]

# ── Mock edges for today (written to mart_betting_edges so Place Bets tab shows the data editor)
# Mirrors the shape written by inference_pipeline.py
MOCK_EDGES = [
    dict(game_pk=748000, pitcher_id=592789,
         bookmaker_key="fanduel",   line=7.5,
         model_prob_over=0.65, model_prob_under=0.35,
         fair_prob_over=0.562, fair_prob_under=0.438,
         edge_over=0.088, edge_under=-0.088,
         odds_over=110, odds_under=-130,
         kelly_over=0.041, kelly_under=0.0,
         predicted_k_rate=0.285, has_rolling_window=True, n_sims=50000,
         pitcher_name="Gerrit Cole"),

    dict(game_pk=748001, pitcher_id=669923,
         bookmaker_key="fanatics",  line=6.5,
         model_prob_over=0.70, model_prob_under=0.30,
         fair_prob_over=0.588, fair_prob_under=0.412,
         edge_over=0.112, edge_under=-0.112,
         odds_over=-115, odds_under=-105,
         kelly_over=0.058, kelly_under=0.0,
         predicted_k_rate=0.302, has_rolling_window=True, n_sims=50000,
         pitcher_name="Spencer Strider"),

    dict(game_pk=748002, pitcher_id=605483,
         bookmaker_key="betrivers", line=5.5,
         model_prob_over=0.41, model_prob_under=0.59,
         fair_prob_over=0.476, fair_prob_under=0.524,
         edge_over=-0.066, edge_under=0.066,
         odds_over=-108, odds_under=-112,
         kelly_over=0.0, kelly_under=0.035,
         predicted_k_rate=0.238, has_rolling_window=True, n_sims=50000,
         pitcher_name="Dylan Cease"),

    dict(game_pk=748003, pitcher_id=641154,
         bookmaker_key="fanduel",   line=4.5,
         model_prob_over=0.57, model_prob_under=0.43,
         fair_prob_over=0.524, fair_prob_under=0.476,
         edge_over=0.046, edge_under=-0.046,
         odds_over=-120, odds_under=100,
         kelly_over=0.033, kelly_under=0.0,
         predicted_k_rate=0.221, has_rolling_window=True, n_sims=50000,
         pitcher_name="Zac Gallen"),
]

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    reset = "--reset" in sys.argv

    db.ensure_tables()

    with db.get_cursor() as cur:
        if reset:
            cur.execute("DELETE FROM main.mlb_props_gold.bet_results")
            print("bet_results cleared.")
            cur.execute(
                f"DELETE FROM main.mlb_props_gold.mart_betting_edges WHERE game_date = '{TODAY}'"
            )
            print("mart_betting_edges (today) cleared.")

        now = pd.Timestamp.now(tz="UTC").isoformat()

        # ── Seed bet_results (past dates only — today left empty so Place Bets shows editor) ──
        print("\nSeeding bet_results (settled history)...")
        inserted = 0
        for bet in MOCK_BETS:
            cur.execute(
                """
                INSERT INTO main.mlb_props_gold.bet_results
                    (game_date, pitcher_id, pitcher_name, bookmaker_key, line, side,
                     odds_american, kelly_pct, stake_units, result, profit_units,
                     logged_at, edge_pct, model_prob)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    str(bet["game_date"]),
                    bet["pitcher_id"],
                    bet["pitcher_name"],
                    bet["bookmaker_key"],
                    bet["line"],
                    bet["side"],
                    bet["odds_american"],
                    bet["kelly_pct"],
                    bet["stake_units"],
                    bet["result"],
                    bet["profit_units"],
                    now,
                    bet["edge_pct"],
                    bet["model_prob"],
                ],
            )
            inserted += 1
            print(f"  {bet['game_date']}  {bet['pitcher_name']:<22}  {bet['result']}")
        print(f"  → {inserted} rows inserted into bet_results")

        # ── Seed mart_betting_edges for today (powers Place Bets tab) ──
        print(f"\nSeeding mart_betting_edges for {TODAY}...")
        for edge in MOCK_EDGES:
            cur.execute(
                """
                INSERT INTO main.mlb_props_gold.mart_betting_edges
                    (game_date, game_pk, pitcher_id, bookmaker_key, line,
                     model_prob_over, model_prob_under,
                     fair_prob_over,  fair_prob_under,
                     edge_over,       edge_under,
                     odds_over,       odds_under,
                     kelly_over,      kelly_under,
                     predicted_k_rate, has_rolling_window, n_sims, generated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    str(TODAY),
                    edge["game_pk"],
                    edge["pitcher_id"],
                    edge["bookmaker_key"],
                    edge["line"],
                    edge["model_prob_over"],
                    edge["model_prob_under"],
                    edge["fair_prob_over"],
                    edge["fair_prob_under"],
                    edge["edge_over"],
                    edge["edge_under"],
                    edge["odds_over"],
                    edge["odds_under"],
                    edge["kelly_over"],
                    edge["kelly_under"],
                    edge["predicted_k_rate"],
                    edge["has_rolling_window"],
                    edge["n_sims"],
                    now,
                ],
            )
            print(f"  {edge['pitcher_name']:<22}  line={edge['line']}  edge={edge['edge_over']*100:.1f}%")
        print(f"  → {len(MOCK_EDGES)} rows inserted into mart_betting_edges")

    print("\nDone. Run: source .env.local && streamlit run app.py")


if __name__ == "__main__":
    main()
