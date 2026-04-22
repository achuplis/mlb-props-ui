"""
Databricks SQL connection helpers for the MLB Props dashboard.

Env vars required (load from .env.local before running):
  DATABRICKS_HOST        e.g. adb-7405609964991497.17.azuredatabricks.net
  DATABRICKS_HTTP_PATH   e.g. /sql/1.0/warehouses/ac4be41b5fb8a853
  DATABRICKS_TOKEN       PAT starting with dapi...
"""

import os
from contextlib import contextmanager

from databricks import sql


def _conn_params() -> dict:
    return dict(
        server_hostname=os.environ["DATABRICKS_HOST"],
        http_path=os.environ["DATABRICKS_HTTP_PATH"],
        access_token=os.environ["DATABRICKS_TOKEN"],
    )


@contextmanager
def get_cursor():
    """Context manager that yields a live Databricks SQL cursor."""
    with sql.connect(**_conn_params()) as conn:
        with conn.cursor() as cur:
            yield cur


def ensure_tables() -> None:
    """
    Create gold-layer tables required by the dashboard if they don't exist.
    Safe to call on every app startup — CREATE TABLE IF NOT EXISTS is idempotent.
    Also adds analytics columns (edge_pct, model_prob) if the table was created
    before they were added to the schema.
    """
    with get_cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS main.mlb_props_gold.bet_results (
                game_date      DATE,
                pitcher_id     BIGINT,
                pitcher_name   STRING,
                bookmaker_key  STRING,
                line           DOUBLE,
                side           STRING,
                odds_american  INT,
                kelly_pct      DOUBLE,
                stake_units    DOUBLE,
                result         STRING,
                profit_units   DOUBLE,
                logged_at      TIMESTAMP,
                edge_pct       DOUBLE,
                model_prob     DOUBLE
            ) USING DELTA
        """)
        # Schema migration: add analytics columns if table already existed without them
        for col_ddl in ("edge_pct DOUBLE", "model_prob DOUBLE"):
            try:
                cur.execute(
                    f"ALTER TABLE main.mlb_props_gold.bet_results "
                    f"ADD COLUMNS ({col_ddl})"
                )
            except Exception:
                pass  # column already exists — safe to ignore
