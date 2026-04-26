"""
MLB Props Engine — Streamlit Dashboard

Workflow:
  1. Place Bets  — check which flagged edges you actually placed; confirms to bet_results as 'pending'
  2. Settle Bets — mark pending bets win/loss/push/void after games finish
  3. P&L         — cumulative results chart (settled bets only; unconfirmed edges never appear)

Run locally:
  source .env.local && streamlit run app.py
"""

import os
from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

load_dotenv(".env.local")

import db  # noqa: E402 — must be after load_dotenv

# ── Constants ─────────────────────────────────────────────────────────────────

# !! KEEP IN SYNC with:
#   notebooks/monte_carlo_simulator.py  → EDGE_THRESHOLD        (currently 0.08)
#   notebooks/inference_pipeline.py     → EDGE_THRESHOLD_OVER/UNDER (currently 0.08)
#
# The simulator writes ALL pitcher/line/book combinations to mart_betting_edges,
# not just flagged ones. This constant is the UI's own display filter.
# If you change the threshold in either notebook, update this value to match —
# otherwise the Place Bets tab will show bets the notebooks no longer consider edges.
EDGE_THRESHOLD = 0.10

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="MLB Props Engine",
    page_icon="⚾",
    layout="wide",
)

# ── One-time init ─────────────────────────────────────────────────────────────

@st.cache_resource
def init():
    db.ensure_tables()

init()

st.title("⚾ MLB Props Engine")
st.caption(f"Edge = model prob − no-vig implied prob  |  Threshold: {EDGE_THRESHOLD*100:.0f}%  |  Kelly: 0.25×")

# ── Tabs ──────────────────────────────────────────────────────────────────────

tab_place, tab_settle, tab_pnl = st.tabs(["Place Bets", "Settle Bets", "P&L"])


# ── Data loaders ─────────────────────────────────────────────────────────────

def _fetch(query: str) -> pd.DataFrame:
    with db.get_cursor() as cur:
        cur.execute(query)
        rows = cur.fetchall()
        if not rows:
            return pd.DataFrame()
        cols = [desc[0] for desc in cur.description]
    return pd.DataFrame(rows, columns=cols)


@st.cache_data(ttl=300)
def load_edges(game_date_str: str) -> pd.DataFrame:
    """Flagged edges from mart_betting_edges for a given date."""
    return _fetch(f"""
        SELECT
            COALESCE(p.pitcher_name, CAST(e.pitcher_id AS STRING)) AS pitcher_name,
            e.bookmaker_key                                         AS book,
            e.line,
            CASE WHEN e.edge_over >= e.edge_under THEN 'Over'  ELSE 'Under' END AS side,
            ROUND(CASE WHEN e.edge_over >= e.edge_under
                       THEN e.model_prob_over  ELSE e.model_prob_under  END * 100, 1) AS model_pct,
            ROUND(CASE WHEN e.edge_over >= e.edge_under
                       THEN e.fair_prob_over   ELSE e.fair_prob_under   END * 100, 1) AS market_pct,
            ROUND(CASE WHEN e.edge_over >= e.edge_under
                       THEN e.edge_over        ELSE e.edge_under        END * 100, 1) AS edge_pct,
            ROUND(CASE WHEN e.edge_over >= e.edge_under
                       THEN e.kelly_over       ELSE e.kelly_under       END * 100, 2) AS kelly_pct,
            CASE WHEN e.edge_over >= e.edge_under
                 THEN e.odds_over ELSE e.odds_under END                 AS odds,
            e.pitcher_id
        FROM main.mlb_props_gold.mart_betting_edges e
        LEFT JOIN main.mlb_props_silver.pitcher_name_lookup p
               ON e.pitcher_id = p.pitcher_id
        WHERE e.game_date = '{game_date_str}'
          AND (e.edge_over > {EDGE_THRESHOLD} OR e.edge_under > {EDGE_THRESHOLD})
          AND e.has_rolling_window = true
        ORDER BY edge_pct DESC
    """)


@st.cache_data(ttl=30)
def load_placed(game_date_str: str) -> pd.DataFrame:
    """Bets already confirmed for a given date (any result status)."""
    return _fetch(f"""
        SELECT pitcher_name, bookmaker_key AS book, line, side, odds_american AS odds,
               stake_units AS stake, result
        FROM main.mlb_props_gold.bet_results
        WHERE game_date = '{game_date_str}'
        ORDER BY pitcher_name
    """)


@st.cache_data(ttl=30)
def load_pending() -> pd.DataFrame:
    """All bets awaiting a result across all dates."""
    df = _fetch("""
        SELECT game_date, pitcher_name, bookmaker_key AS book, line, side,
               odds_american AS odds, stake_units AS stake, result
        FROM main.mlb_props_gold.bet_results
        WHERE result = 'pending'
        ORDER BY game_date ASC, pitcher_name ASC
    """)
    if not df.empty:
        df["game_date"] = pd.to_datetime(df["game_date"]).dt.date
    return df


@st.cache_data(ttl=120)
def load_name_review() -> pd.DataFrame:
    """Pitcher names from Odds API that need manual match confirmation."""
    return _fetch("""
        SELECT pitcher_name AS odds_name, pitcher_id, match_type, fuzzy_score, fuzzy_candidate
        FROM main.mlb_props_silver.pitcher_name_lookup
        WHERE match_type IN ('fuzzy_review', 'unmatched')
        ORDER BY match_type DESC, fuzzy_score ASC
    """)


@st.cache_data(ttl=300)
def load_confirmed_pitchers() -> pd.DataFrame:
    """All confirmed pitcher name→MLBAM ID mappings (options for the review dropdown)."""
    return _fetch("""
        SELECT DISTINCT pitcher_id, fuzzy_candidate AS chadwick_name
        FROM main.mlb_props_silver.pitcher_name_lookup
        WHERE match_type NOT IN ('unmatched')
          AND pitcher_id IS NOT NULL
        ORDER BY fuzzy_candidate
    """)


@st.cache_data(ttl=60)
def load_settled() -> pd.DataFrame:
    """Settled bets for P&L reporting (excludes pending)."""
    df = _fetch("""
        SELECT game_date, pitcher_name, bookmaker_key AS book, line, side,
               odds_american AS odds, stake_units AS stake, result, profit_units,
               logged_at, edge_pct, model_prob
        FROM main.mlb_props_gold.bet_results
        WHERE result IN ('win', 'loss', 'push', 'void')
        ORDER BY game_date DESC, logged_at DESC
    """)
    if not df.empty:
        df["game_date"] = pd.to_datetime(df["game_date"]).dt.date
        df["logged_at"] = pd.to_datetime(df["logged_at"])
    return df


# ── Tab 1: Place Bets ─────────────────────────────────────────────────────────

with tab_place:
    selected_date = st.date_input(
        "Game date",
        value=date.today(),
        help="Select the date you want to confirm bets for. Defaults to today.",
    )
    date_str = str(selected_date)
    already = load_placed(date_str)

    if not already.empty:
        # Already confirmed for this date — show read-only summary
        settled_count = (already["result"] != "pending").sum()
        pending_count = (already["result"] == "pending").sum()
        st.success(
            f"**{len(already)} bet(s) confirmed** for {selected_date}  "
            f"— {settled_count} settled, {pending_count} pending"
        )
        st.dataframe(
            already.rename(columns={
                "pitcher_name": "Pitcher", "book": "Book", "line": "Line",
                "side": "Side", "odds": "Odds", "stake": "Stake", "result": "Result",
            }),
            use_container_width=True,
            hide_index=True,
        )
        st.caption("Go to **Settle Bets** to log results for pending bets.")

    else:
        edges = load_edges(date_str)

        if edges.empty:
            st.info(
                f"No flagged edges for **{selected_date}**.  \n"
                "Run `inference_pipeline` after lineups post (~17:00 UTC) "
                "and odds post (~18:00 UTC)."
            )
        else:
            st.markdown(
                f"**{len(edges)} edge(s) flagged** for {selected_date}. "
                "Check the bets you actually placed and set your stake."
            )
            st.caption("Only checked rows will be tracked in P&L.")

            # Build editable dataframe
            edit_df = edges.assign(place=False, stake=1.0)

            edited = st.data_editor(
                edit_df,
                column_config={
                    "place":        st.column_config.CheckboxColumn(
                                        "Place?", default=False, width="small"
                                    ),
                    "stake":        st.column_config.NumberColumn(
                                        "Stake (units)", min_value=0.01,
                                        max_value=20.0, step=0.25, format="%.2f"
                                    ),
                    "pitcher_name": st.column_config.TextColumn("Pitcher"),
                    "book":         st.column_config.TextColumn("Book"),
                    "line":         st.column_config.NumberColumn("Line", format="%.1f"),
                    "side":         st.column_config.TextColumn("Side"),
                    "model_pct":    st.column_config.NumberColumn("Model %", format="%.1f"),
                    "market_pct":   st.column_config.NumberColumn("Market %", format="%.1f"),
                    "edge_pct":     st.column_config.NumberColumn("Edge %", format="%.1f"),
                    "kelly_pct":    st.column_config.NumberColumn("Kelly %", format="%.2f"),
                    "odds":         st.column_config.NumberColumn("Odds"),
                    "pitcher_id":   None,  # hidden
                },
                disabled=["pitcher_name", "book", "line", "side",
                          "model_pct", "market_pct", "edge_pct", "kelly_pct", "odds"],
                use_container_width=True,
                hide_index=True,
                key=f"place_editor_{date_str}",
            )

            selected = edited[edited["place"] == True]  # noqa: E712
            st.caption(f"{len(selected)} bet(s) selected")

            if st.button(
                f"Confirm {len(selected)} bet(s) placed",
                disabled=len(selected) == 0,
                type="primary",
            ):
                now = pd.Timestamp.now(tz="UTC").isoformat()
                with db.get_cursor() as cur:
                    for _, row in selected.iterrows():
                        cur.execute(
                            """
                            INSERT INTO main.mlb_props_gold.bet_results
                                (game_date, pitcher_id, pitcher_name, bookmaker_key, line, side,
                                 odds_american, kelly_pct, stake_units, result, profit_units,
                                 logged_at, edge_pct, model_prob)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            [
                                date_str,
                                int(row["pitcher_id"]),
                                str(row["pitcher_name"]),
                                str(row["book"]),
                                float(row["line"]),
                                str(row["side"]),
                                int(row["odds"]),
                                float(row["kelly_pct"]) / 100,
                                float(row["stake"]),
                                "pending",
                                0.0,                            # profit_units — filled in when settled
                                now,
                                float(row["edge_pct"]) / 100,  # edge as decimal e.g. 0.05
                                float(row["model_pct"]) / 100, # model prob as decimal e.g. 0.62
                            ],
                        )
                st.success(f"Confirmed {len(selected)} bet(s) for {selected_date}.")
                load_placed.clear()
                st.rerun()

    # ── Name matching review ──────────────────────────────────────────────────
    # Surfaces Odds API pitcher names that couldn't be auto-matched to MLBAM IDs.
    # Corrections saved here update pitcher_name_lookup directly.
    # NOTE: re-running build_pitcher_lookup.py (full overwrite) will wipe manual_confirmed rows.
    # To make corrections permanent, also add them to NAME_OVERRIDES in that notebook.
    st.divider()
    review_df = load_name_review()
    n_review  = len(review_df)
    label     = (
        f"⚠️ Name matching review — {n_review} item(s) need attention"
        if n_review > 0
        else "Name matching review — all names matched ✓"
    )

    with st.expander(label, expanded=n_review > 0):
        if review_df.empty:
            st.success("All pitcher names from The Odds API are matched to MLBAM IDs.")
        else:
            st.caption(
                "**Left:** name as received from The Odds API.  "
                "**Suggested Match:** best fuzzy guess.  "
                "**Confirmed Match:** select the correct Statcast name to save."
            )
            confirmed_df = load_confirmed_pitchers()
            name_to_id   = dict(zip(
                confirmed_df["chadwick_name"],
                confirmed_df["pitcher_id"].astype(int),
            ))
            name_options = sorted(confirmed_df["chadwick_name"].dropna().tolist())

            display = review_df.copy()
            display["confirmed_match"] = display.apply(
                lambda r: (
                    r["fuzzy_candidate"]
                    if r["match_type"] == "fuzzy_review" and r["fuzzy_candidate"] in name_to_id
                    else None
                ),
                axis=1,
            )
            display = display[["odds_name", "fuzzy_candidate", "fuzzy_score",
                                "match_type", "confirmed_match"]]

            edited = st.data_editor(
                display,
                column_config={
                    "odds_name":       st.column_config.TextColumn("Odds API Name"),
                    "fuzzy_candidate": st.column_config.TextColumn("Suggested Match"),
                    "fuzzy_score":     st.column_config.NumberColumn("Score", format="%d", width="small"),
                    "match_type":      st.column_config.TextColumn("Status", width="small"),
                    "confirmed_match": st.column_config.SelectboxColumn(
                                           "Confirmed Match",
                                           options=name_options,
                                           required=False,
                                       ),
                },
                disabled=["odds_name", "fuzzy_candidate", "fuzzy_score", "match_type"],
                use_container_width=True,
                hide_index=True,
                key="name_review_editor",
            )

            changed = edited[edited["confirmed_match"].notna() & (edited["confirmed_match"] != "")]
            st.caption(f"{len(changed)} correction(s) ready to save")

            if st.button(
                f"Save {len(changed)} name correction(s)",
                disabled=len(changed) == 0,
                key="save_name_corrections_btn",
            ):
                with db.get_cursor() as cur:
                    for _, row in changed.iterrows():
                        new_id = name_to_id.get(row["confirmed_match"])
                        if new_id is None:
                            continue
                        cur.execute(
                            """
                            UPDATE main.mlb_props_silver.pitcher_name_lookup
                            SET    pitcher_id = ?, match_type = 'manual_confirmed',
                                   fuzzy_candidate = ?
                            WHERE  pitcher_name = ?
                            """,
                            [int(new_id), str(row["confirmed_match"]), str(row["odds_name"])],
                        )
                st.success(f"Saved {len(changed)} correction(s).")
                load_name_review.clear()
                st.rerun()


# ── Tab 2: Settle Bets ────────────────────────────────────────────────────────

def _compute_result(side: str, line: float, actual_ks: int) -> str:
    ks = float(actual_ks)
    ln = float(line)
    if side.lower() == "over":
        return "win" if ks > ln else ("push" if ks == ln else "loss")
    else:
        return "win" if ks < ln else ("push" if ks == ln else "loss")


def _compute_profit(result: str, stake: float, odds: int) -> float:
    if result == "win":
        return stake * (odds / 100 if odds > 0 else 100 / abs(odds))
    if result == "loss":
        return -stake
    return 0.0


@st.cache_data(ttl=30)
def load_auto_settle_candidates() -> pd.DataFrame:
    """
    Pending bets that have Statcast data available — ready to auto-settle.
    Joins bet_results (pending) → int_pitcher_game_outcomes on (pitcher_id, game_date).
    Statcast data is typically loaded by 13:00 UTC the day after games are played.
    """
    return _fetch("""
        SELECT
            b.game_date,
            b.pitcher_id,
            b.pitcher_name,
            b.bookmaker_key  AS book,
            b.line,
            b.side,
            b.odds_american  AS odds,
            b.stake_units    AS stake,
            o.strikeouts     AS actual_ks
        FROM main.mlb_props_gold.bet_results b
        JOIN main.mlb_props_silver.int_pitcher_game_outcomes o
          ON b.pitcher_id = o.pitcher_id
         AND b.game_date  = o.game_date
        WHERE b.result = 'pending'
        ORDER BY b.game_date ASC, b.pitcher_name ASC
    """)


with tab_settle:
    pending = load_pending()

    if pending.empty:
        st.info("No pending bets — confirm bets on the **Place Bets** tab first.")
    else:
        st.markdown(f"**{len(pending)} pending bet(s)** across all dates.")

        # ── Auto-settle from Statcast ──────────────────────────────────────────
        st.subheader("Auto-settle from Statcast")
        st.info(
            "**Data availability:** Statcast results for a given game date are typically "
            "loaded the following day after the `statcast_ingest` function runs (~13:00 UTC / 9 AM ET). "
            "Bets from last night's games will not be auto-settleable until the next afternoon. "
            "Use the **Manual settle** section below for any bets where data is not yet available."
        )

        candidates = load_auto_settle_candidates()

        if candidates.empty:
            st.info("No Statcast data found for pending bets yet — check back after 13:00 UTC the day after games finish.")
        else:
            # Preview what will be settled
            preview = candidates.copy()
            preview["result"] = preview.apply(
                lambda r: _compute_result(r["side"], r["line"], r["actual_ks"]), axis=1
            )
            preview["profit"] = preview.apply(
                lambda r: _compute_profit(r["result"], float(r["stake"]), int(r["odds"])), axis=1
            )

            st.dataframe(
                preview[["game_date", "pitcher_name", "book", "line", "side",
                          "actual_ks", "result", "profit"]]
                .rename(columns={
                    "game_date":    "Date",
                    "pitcher_name": "Pitcher",
                    "book":         "Book",
                    "line":         "Line",
                    "side":         "Side",
                    "actual_ks":    "Actual Ks",
                    "result":       "Result",
                    "profit":       "P&L",
                }),
                use_container_width=True,
                hide_index=True,
            )

            if st.button(
                f"Auto-settle {len(candidates)} bet(s)",
                type="primary",
                key="auto_settle_btn",
            ):
                with db.get_cursor() as cur:
                    for _, row in preview.iterrows():
                        cur.execute(
                            """
                            UPDATE main.mlb_props_gold.bet_results
                            SET    result = ?, profit_units = ?
                            WHERE  game_date     = ?
                              AND  pitcher_id    = ?
                              AND  bookmaker_key = ?
                              AND  line          = ?
                              AND  side          = ?
                            """,
                            [
                                str(row["result"]),
                                round(float(row["profit"]), 4),
                                str(row["game_date"]),
                                int(row["pitcher_id"]),
                                str(row["book"]),
                                float(row["line"]),
                                str(row["side"]),
                            ],
                        )
                wins   = (preview["result"] == "win").sum()
                losses = (preview["result"] == "loss").sum()
                pushes = (preview["result"] == "push").sum()
                net    = preview["profit"].sum()
                st.success(
                    f"Settled {len(preview)} bet(s): "
                    f"{wins}W / {losses}L / {pushes}P — {net:+.2f} units"
                )
                load_pending.clear()
                load_settled.clear()
                load_auto_settle_candidates.clear()
                st.rerun()

        # ── Manual fallback for bets without Statcast data yet ─────────────────
        if not candidates.empty:
            # Key on (game_date, pitcher_name, book, line, side) — same as UPDATE WHERE clause
            auto_keys = set(
                zip(candidates["game_date"].astype(str), candidates["pitcher_name"],
                    candidates["book"], candidates["line"].astype(str), candidates["side"])
            )
            no_data_pending = pending[
                ~pending.apply(
                    lambda r: (str(r["game_date"]), r["pitcher_name"],
                               r["book"], str(r["line"]), r["side"]) in auto_keys,
                    axis=1,
                )
            ]
        else:
            no_data_pending = pending

        if not no_data_pending.empty:
            st.divider()
            st.subheader("Manual settle")
            st.caption("Statcast data not yet available for these bets — settle manually or check back later.")

            RESULT_OPTIONS = ["pending", "win", "loss", "push", "void"]

            manual_edit = st.data_editor(
                no_data_pending,
                column_config={
                    "game_date":    st.column_config.DateColumn("Date"),
                    "pitcher_name": st.column_config.TextColumn("Pitcher"),
                    "book":         st.column_config.TextColumn("Book"),
                    "line":         st.column_config.NumberColumn("Line", format="%.1f"),
                    "side":         st.column_config.TextColumn("Side"),
                    "odds":         st.column_config.NumberColumn("Odds"),
                    "stake":        st.column_config.NumberColumn("Stake", format="%.2f"),
                    "result":       st.column_config.SelectboxColumn(
                                        "Result",
                                        options=RESULT_OPTIONS,
                                        required=True,
                                        width="medium",
                                    ),
                },
                disabled=["game_date", "pitcher_name", "book", "line", "side", "odds", "stake"],
                use_container_width=True,
                hide_index=True,
                key="manual_settle_editor",
            )

            changed = manual_edit[manual_edit["result"] != "pending"]
            st.caption(f"{len(changed)} result(s) ready to save")

            if st.button(
                f"Save {len(changed)} manual result(s)",
                disabled=len(changed) == 0,
                type="secondary",
                key="manual_settle_btn",
            ):
                with db.get_cursor() as cur:
                    for _, row in changed.iterrows():
                        result = str(row["result"])
                        profit = _compute_profit(result, float(row["stake"]), int(row["odds"]))
                        cur.execute(
                            """
                            UPDATE main.mlb_props_gold.bet_results
                            SET    result = ?, profit_units = ?
                            WHERE  game_date     = ?
                              AND  pitcher_name  = ?
                              AND  bookmaker_key = ?
                              AND  line          = ?
                              AND  side          = ?
                            """,
                            [
                                result,
                                round(profit, 4),
                                str(row["game_date"]),
                                str(row["pitcher_name"]),
                                str(row["book"]),
                                float(row["line"]),
                                str(row["side"]),
                            ],
                        )
                st.success(f"Saved {len(changed)} result(s).")
                load_pending.clear()
                load_settled.clear()
                st.rerun()


# ── Tab 3: P&L ────────────────────────────────────────────────────────────────

def _breakdown(df: pd.DataFrame, group_col: str) -> pd.DataFrame:
    """Aggregate settled bets by a grouping column into a summary table."""
    settled = df[df["result"].isin(["win", "loss"])]
    grp = df.groupby(group_col)
    s_grp = settled.groupby(group_col)
    summary = pd.DataFrame({
        "Bets":       grp.size(),
        "Wins":       s_grp.apply(lambda x: (x["result"] == "win").sum()),
        "Losses":     s_grp.apply(lambda x: (x["result"] == "loss").sum()),
        "Net Units":  grp["profit_units"].sum().round(2),
        "Staked":     grp["stake"].sum().round(2),
    }).fillna(0)
    summary["Win %"]  = (summary["Wins"] / (summary["Wins"] + summary["Losses"]).clip(lower=1) * 100).round(0).astype(int).astype(str) + "%"
    summary["ROI %"]  = ((summary["Net Units"] / summary["Staked"].clip(lower=0.01)) * 100).round(1).astype(str) + "%"
    return summary.drop(columns=["Staked"]).reset_index().rename(columns={group_col: group_col.replace("_", " ").title()})


with tab_pnl:
    results = load_settled()

    if results.empty:
        st.info("No settled results yet — settle bets on the **Settle Bets** tab.")
    else:
        # ── Summary metrics ──
        wins   = (results["result"] == "win").sum()
        losses = (results["result"] == "loss").sum()
        net    = results["profit_units"].sum()
        roi    = net / results["stake"].sum() * 100 if results["stake"].sum() > 0 else 0

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Settled bets", len(results))
        c2.metric("Record",       f"{wins}W – {losses}L")
        c3.metric("Win %",        f"{wins / max(wins + losses, 1) * 100:.0f}%")
        c4.metric("Net units",    f"{net:+.2f}",
                  delta=f"ROI {roi:+.1f}%",
                  delta_color="normal" if net >= 0 else "inverse")

        # ── Cumulative P&L chart ──
        chart_df = (
            results
            .sort_values("logged_at")
            .assign(cum_pnl=lambda df: df["profit_units"].cumsum())
        )
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=chart_df["logged_at"],
            y=chart_df["cum_pnl"],
            mode="lines+markers",
            line=dict(color="#00cc66", width=2),
            marker=dict(size=6),
            hovertemplate="%{x|%Y-%m-%d}<br>Cumulative: %{y:+.2f} units<extra></extra>",
        ))
        fig.add_hline(y=0, line_dash="dash", line_color="#666666")
        fig.update_layout(
            title="Cumulative P&L (settled bets only)",
            xaxis_title=None,
            yaxis_title="Units",
            template="plotly_dark",
            margin=dict(t=40, b=20),
            height=320,
        )
        st.plotly_chart(fig, use_container_width=True)

        # ── Season breakdown ──────────────────────────────────────────────────
        st.subheader("Season breakdown")
        st.caption(
            "Helps identify where the model's edge is real vs where you're leaking. "
            "Small samples early in the season — treat patterns as directional, not definitive."
        )

        # Derived columns for bucketing
        def _line_bucket(ln):
            if ln <= 4.5:  return "≤ 4.5"
            if ln <= 5.5:  return "5.0 – 5.5"
            if ln <= 6.5:  return "6.0 – 6.5"
            return "≥ 7.0"

        def _edge_bucket(ep):
            if pd.isna(ep): return "Unknown"
            pct = ep * 100
            if pct < 5:  return "3 – 5%"
            if pct < 8:  return "5 – 8%"
            return "8%+"

        results["line_bucket"] = results["line"].apply(_line_bucket)
        results["edge_bucket"] = results["edge_pct"].apply(_edge_bucket)

        col_book, col_side = st.columns(2)

        with col_book:
            st.markdown("**By book**")
            st.dataframe(
                _breakdown(results, "book"),
                use_container_width=True,
                hide_index=True,
            )

        with col_side:
            st.markdown("**By side (Over / Under)**")
            st.dataframe(
                _breakdown(results, "side"),
                use_container_width=True,
                hide_index=True,
            )

        col_line, col_edge = st.columns(2)

        with col_line:
            st.markdown("**By line range**")
            line_order = ["≤ 4.5", "5.0 – 5.5", "6.0 – 6.5", "≥ 7.0"]
            line_bd = _breakdown(results, "line_bucket")
            line_bd["Line Bucket"] = pd.Categorical(line_bd["Line Bucket"], categories=line_order, ordered=True)
            st.dataframe(
                line_bd.sort_values("Line Bucket"),
                use_container_width=True,
                hide_index=True,
            )

        with col_edge:
            st.markdown("**Edge calibration** *(are bigger edges actually winning more?)*")
            has_edge = results["edge_pct"].notna().any()
            if not has_edge:
                st.caption("Edge data not available for bets placed before this feature was added.")
            else:
                edge_order = ["3 – 5%", "5 – 8%", "8%+", "Unknown"]
                edge_bd = _breakdown(results, "edge_bucket")
                edge_bd["Edge Bucket"] = pd.Categorical(edge_bd["Edge Bucket"], categories=edge_order, ordered=True)
                # Add avg model prob column
                model_avg = (
                    results[results["model_prob"].notna()]
                    .groupby("edge_bucket")["model_prob"]
                    .mean()
                    .mul(100).round(1)
                    .rename("Avg Model %")
                    .reset_index()
                    .rename(columns={"edge_bucket": "Edge Bucket"})
                )
                edge_bd = edge_bd.merge(model_avg, on="Edge Bucket", how="left")
                st.dataframe(
                    edge_bd.sort_values("Edge Bucket"),
                    use_container_width=True,
                    hide_index=True,
                )
                st.caption(
                    "**Avg Model %** is what the model predicted at bet time. "
                    "**Win %** is what actually happened. "
                    "Consistent over-performance vs model = edge is real. "
                    "Consistent under-performance = model is overconfident in that bucket."
                )

        # ── Full results table ────────────────────────────────────────────────
        st.subheader("All results")
        st.dataframe(
            results[["game_date", "pitcher_name", "book", "line", "side",
                      "odds", "stake", "edge_pct", "model_prob", "result", "profit_units"]]
            .assign(
                edge_pct=lambda df: df["edge_pct"].map(lambda v: f"{v*100:.1f}%" if pd.notna(v) else "—"),
                model_prob=lambda df: df["model_prob"].map(lambda v: f"{v*100:.1f}%" if pd.notna(v) else "—"),
            )
            .rename(columns={
                "game_date":    "Date",
                "pitcher_name": "Pitcher",
                "book":         "Book",
                "line":         "Line",
                "side":         "Side",
                "odds":         "Odds",
                "stake":        "Stake",
                "edge_pct":     "Edge %",
                "model_prob":   "Model %",
                "result":       "Result",
                "profit_units": "P&L",
            }),
            use_container_width=True,
            hide_index=True,
        )
