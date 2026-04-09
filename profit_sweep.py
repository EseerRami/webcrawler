"""
Daily profit sweep tracker.

Reads the day's realized P&L from an Alpaca account, earmarks a
configurable percentage (default 20%) into a local ledger, and keeps
a running "personal bucket" balance. Does NOT move money — the
ledger tells you how much to manually transfer out of your brokerage.

Usage:
    export ALPACA_API_KEY=...
    export ALPACA_SECRET_KEY=...
    python profit_sweep.py             # record today's sweep
    python profit_sweep.py --show      # print ledger and exit
    python profit_sweep.py --pct 0.15  # use 15% instead of default 20%
    python profit_sweep.py --paper     # use Alpaca paper-trading endpoint
"""

import argparse
import os
import sqlite3
from datetime import date, datetime

from alpaca.trading.client import TradingClient

DB_PATH = "profit_sweep.db"
DEFAULT_SWEEP_PCT = 0.20


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sweeps (
            sweep_date TEXT PRIMARY KEY,
            daily_pnl REAL NOT NULL,
            sweep_amount REAL NOT NULL,
            running_balance REAL NOT NULL,
            recorded_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def get_daily_pnl(client: TradingClient) -> float:
    """Today's equity minus prior close equity, per Alpaca account."""
    account = client.get_account()
    return float(account.equity) - float(account.last_equity)


def current_balance(conn) -> float:
    row = conn.execute(
        "SELECT running_balance FROM sweeps ORDER BY sweep_date DESC LIMIT 1"
    ).fetchone()
    return row[0] if row else 0.0


def record_sweep(conn, pnl: float, sweep_pct: float) -> tuple[float, float]:
    today = date.today().isoformat()
    already = conn.execute(
        "SELECT 1 FROM sweeps WHERE sweep_date = ?", (today,)
    ).fetchone()
    if already:
        raise SystemExit(f"Sweep for {today} already recorded.")

    # Only sweep on winning days — never pull money out on a loss.
    sweep = max(pnl, 0.0) * sweep_pct
    new_balance = current_balance(conn) + sweep
    conn.execute(
        "INSERT INTO sweeps VALUES (?, ?, ?, ?, ?)",
        (today, pnl, sweep, new_balance, datetime.utcnow().isoformat()),
    )
    conn.commit()
    return sweep, new_balance


def show_ledger(conn) -> None:
    rows = conn.execute(
        "SELECT sweep_date, daily_pnl, sweep_amount, running_balance "
        "FROM sweeps ORDER BY sweep_date"
    ).fetchall()
    if not rows:
        print("No sweeps recorded yet.")
        return
    print(f"{'date':<12}{'daily_pnl':>12}{'sweep':>12}{'balance':>14}")
    for d, pnl, sweep, bal in rows:
        print(f"{d:<12}{pnl:>12.2f}{sweep:>12.2f}{bal:>14.2f}")
    print(f"\nPersonal bucket balance: ${rows[-1][3]:.2f}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--show", action="store_true", help="Print the ledger and exit"
    )
    parser.add_argument(
        "--pct",
        type=float,
        default=DEFAULT_SWEEP_PCT,
        help=f"Sweep percentage as decimal (default {DEFAULT_SWEEP_PCT})",
    )
    parser.add_argument(
        "--paper",
        action="store_true",
        help="Use Alpaca paper-trading endpoint instead of live",
    )
    args = parser.parse_args()

    if not 0 < args.pct <= 1:
        raise SystemExit("--pct must be between 0 and 1")

    conn = init_db()

    if args.show:
        show_ledger(conn)
        return

    api_key = os.environ.get("ALPACA_API_KEY")
    secret_key = os.environ.get("ALPACA_SECRET_KEY")
    if not api_key or not secret_key:
        raise SystemExit("Set ALPACA_API_KEY and ALPACA_SECRET_KEY env vars.")

    client = TradingClient(api_key, secret_key, paper=args.paper)
    pnl = get_daily_pnl(client)
    sweep, balance = record_sweep(conn, pnl, args.pct)

    print(f"Daily P&L:               ${pnl:>10.2f}")
    print(f"Swept ({args.pct:.0%}):               ${sweep:>10.2f}")
    print(f"Personal bucket balance: ${balance:>10.2f}")
    if sweep > 0:
        print(f"\n-> Manually transfer ${sweep:.2f} out of your brokerage.")


if __name__ == "__main__":
    main()
