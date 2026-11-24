"""Persistência em SQLite: trades vistos dos mestres, posições da conta seguidora, log de ordens."""
import sqlite3
import time

from .models import Fill, Trade

SCHEMA = """
CREATE TABLE IF NOT EXISTS master_trades (
    master TEXT, id TEXT, symbol TEXT, side TEXT, amount REAL, price REAL, cost REAL, ts INTEGER,
    PRIMARY KEY (master, symbol, id)
);
CREATE TABLE IF NOT EXISTS follower_positions (
    master TEXT, symbol TEXT, qty REAL, cost REAL,
    PRIMARY KEY (master, symbol)
);
CREATE TABLE IF NOT EXISTS follower_orders (
    ts INTEGER, master TEXT, symbol TEXT, side TEXT, amount REAL, price REAL, cost REAL,
    pnl REAL, dry_run INTEGER, reason TEXT
);
"""


class Storage:
    def __init__(self, path: str):
        self.db = sqlite3.connect(path)
        self.db.executescript(SCHEMA)

    # ---- trades dos mestres ----
    def add_master_trade(self, master: str, t: Trade) -> bool:
        """Grava o trade; retorna False se já tinha sido visto."""
        cur = self.db.execute(
            "INSERT OR IGNORE INTO master_trades VALUES (?,?,?,?,?,?,?,?)",
            (master, t.id, t.symbol, t.side, t.amount, t.price, t.cost, t.timestamp),
        )
        self.db.commit()
        return cur.rowcount == 1

    def master_trades(self, master: str) -> list[Trade]:
        rows = self.db.execute(
            "SELECT id, symbol, side, amount, price, cost, ts FROM master_trades "
            "WHERE master=? ORDER BY ts, id", (master,)
        ).fetchall()
        return [Trade(*r) for r in rows]

    def last_trade_ts(self, master: str, symbol: str) -> int | None:
        r = self.db.execute(
            "SELECT MAX(ts) FROM master_trades WHERE master=? AND symbol=?", (master, symbol)
        ).fetchone()
        return r[0]

    # ---- posições da conta seguidora (separadas por mestre) ----
    def position(self, master: str, symbol: str) -> tuple[float, float]:
        r = self.db.execute(
            "SELECT qty, cost FROM follower_positions WHERE master=? AND symbol=?", (master, symbol)
        ).fetchone()
        return (r[0], r[1]) if r else (0.0, 0.0)

    def set_position(self, master: str, symbol: str, qty: float, cost: float) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO follower_positions VALUES (?,?,?,?)", (master, symbol, qty, cost)
        )
        self.db.commit()

    def all_positions(self) -> list[tuple[str, str, float, float]]:
        return self.db.execute(
            "SELECT master, symbol, qty, cost FROM follower_positions WHERE qty > 0"
        ).fetchall()

    # ---- log de ordens ----
    def log_order(self, master: str, f: Fill, pnl: float, dry_run: bool, reason: str) -> None:
        self.db.execute(
            "INSERT INTO follower_orders VALUES (?,?,?,?,?,?,?,?,?,?)",
            (int(time.time() * 1000), master, f.symbol, f.side, f.amount, f.price, f.cost,
             pnl, int(dry_run), reason),
        )
        self.db.commit()

    def realized_pnl_since(self, ts_ms: int) -> float:
        r = self.db.execute(
            "SELECT COALESCE(SUM(pnl), 0) FROM follower_orders WHERE ts >= ?", (ts_ms,)
        ).fetchone()
        return r[0]
