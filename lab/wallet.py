"""Carteira de papel (dinheiro fictício) com taxas e slippage realistas."""
from collections import deque


class Wallet:
    def __init__(self, name: str, cash: float = 1000.0, fee: float = 0.001):
        self.name = name
        self.start = cash
        self.cash = cash
        self.fee = fee
        self.pos: dict = {}              # chave -> {"symbol", "qty", "cost", "ts"}
        self.last_prices: dict[str, float] = {}
        self.buys = self.sells = self.wins = self.closed = 0
        self.symbols: set[str] = set()
        self.realized = 0.0
        self.trades = deque(maxlen=300)
        self.history = deque(maxlen=3000)  # (ts, patrimônio)
        self.peak = cash
        self.max_dd = 0.0
        self.listeners: list = []

    # ------------------------------------------------------------------
    def equity(self) -> float:
        v = self.cash
        for p in self.pos.values():
            px = self.last_prices.get(p["symbol"])
            v += p["qty"] * px if px else p["cost"]
        return v

    def mark(self, ts: int, prices: dict[str, float]) -> None:
        self.last_prices.update(prices)
        eq = self.equity()
        if not self.history or ts - self.history[-1][0] >= 60_000:
            self.history.append((ts, round(eq, 2)))
        self.peak = max(self.peak, eq)
        if self.peak > 0:
            self.max_dd = max(self.max_dd, (self.peak - eq) / self.peak * 100)

    # ------------------------------------------------------------------
    def buy(self, ts: int, symbol: str, usd: float, price: float, slip: float, key=None):
        usd = min(usd, self.cash)
        if usd < 1 or price <= 0:
            return None
        eq_before = self.equity()
        px = price * (1 + slip)
        qty = usd * (1 - self.fee) / px
        k = key or symbol
        p = self.pos.setdefault(k, {"symbol": symbol, "qty": 0.0, "cost": 0.0, "ts": ts})
        p["qty"] += qty
        p["cost"] += usd
        self.cash -= usd
        self.buys += 1
        self.symbols.add(symbol)
        self.last_prices.setdefault(symbol, price)
        self.trades.append({"ts": ts, "side": "buy", "symbol": symbol, "price": px, "usd": usd})
        for fn in self.listeners:
            fn(self, "buy", ts, symbol, usd / eq_before if eq_before else 0, price, slip)
        return px

    def sell(self, ts: int, key, price: float, slip: float, haircut: float = 1.0):
        p = self.pos.pop(key, None)
        if not p:
            return None
        px = price * (1 - slip) * haircut
        usd = p["qty"] * px * (1 - self.fee)
        pnl = usd - p["cost"]
        self.cash += usd
        self.sells += 1
        self.closed += 1
        self.realized += pnl
        if pnl > 0:
            self.wins += 1
        self.trades.append({"ts": ts, "side": "sell", "symbol": p["symbol"], "price": px,
                            "usd": usd, "pnl": pnl})
        for fn in self.listeners:
            fn(self, "sell", ts, p["symbol"], 1.0, price, slip)
        return pnl

    # ------------------------------------------------------------------
    @property
    def ret_pct(self) -> float:
        return (self.equity() / self.start - 1) * 100

    @property
    def win_rate(self) -> float:
        return self.wins / self.closed * 100 if self.closed else 0.0

    def summary(self) -> dict:
        return {
            "name": self.name, "equity": round(self.equity(), 2),
            "pnl": round(self.equity() - self.start, 2), "ret": round(self.ret_pct, 2),
            "buys": self.buys, "sells": self.sells, "coins": len(self.symbols),
            "closed": self.closed, "win_rate": round(self.win_rate, 1),
            "max_dd": round(self.max_dd, 1), "open": len(self.pos),
        }
