"""Replica os trades de um mestre na conta seguidora, com limites de risco."""
import logging
import time
from datetime import datetime, timezone

from .brain import MasterBrain
from .config import MasterCfg, RiskCfg
from .models import Fill, Trade
from .storage import Storage

log = logging.getLogger("copier")


class Copier:
    def __init__(self, follower, storage: Storage, risk: RiskCfg, dry_run: bool):
        self.ex = follower
        self.db = storage
        self.risk = risk
        self.dry_run = dry_run

    # ------------------------------------------------------------------
    def on_master_trade(self, m: MasterCfg, brain: MasterBrain, t: Trade,
                        master_equity: float) -> None:
        if t.side == "buy":
            self._copy_buy(m, brain, t, master_equity)
        else:
            self._copy_sell(m, brain, t)

    # ------------------------------------------------------------------
    def _copy_buy(self, m: MasterCfg, brain: MasterBrain, t: Trade, master_equity: float):
        mult = brain.multiplier
        if mult <= 0:
            return log.info("[%s] compra %s ignorada: mestre pausado", m.name, t.symbol)
        if self._daily_loss_hit():
            return log.warning("[%s] compra %s ignorada: limite de perda diária", m.name, t.symbol)
        if master_equity <= 0:
            return log.warning("[%s] patrimônio do mestre desconhecido", m.name)

        allocation = m.budget_usdt * mult
        fraction = min(t.cost / master_equity, 1.0)
        usdt = fraction * allocation

        open_cost = sum(c for mm, _, _, c in self.db.all_positions() if mm == m.name)
        usdt = min(usdt, allocation - open_cost, self.risk.max_order_usdt)
        if usdt < self.risk.min_order_usdt:
            return log.info("[%s] compra %s ignorada: valor %.2f USDT abaixo do mínimo",
                            m.name, t.symbol, usdt)

        fill = self._buy(t.symbol, usdt)
        qty, cost = self.db.position(m.name, t.symbol)
        self.db.set_position(m.name, t.symbol, qty + fill.amount, cost + fill.cost)
        self.db.log_order(m.name, fill, 0.0, self.dry_run,
                          f"mestre usou {fraction:.1%} do patrimônio, mult {mult}")
        log.info("[%s] COMPRA %s %.6f @ %.4f = %.2f USDT", m.name, t.symbol,
                 fill.amount, fill.price, fill.cost)

    def _copy_sell(self, m: MasterCfg, brain: MasterBrain, t: Trade):
        qty, cost = self.db.position(m.name, t.symbol)
        if qty <= 0:
            return
        master_before = brain.qty(t.symbol)
        fraction = 1.0 if master_before <= 0 else min(t.amount / master_before, 1.0)
        sell_qty = qty * fraction

        price = self.ex.price(t.symbol)
        # se o que sobraria ou o que seria vendido for pequeno demais para a Binance, vende tudo
        if (qty - sell_qty) * price < self.risk.min_order_usdt:
            sell_qty = qty
        if sell_qty * price < self.risk.min_order_usdt and sell_qty < qty:
            return

        fill = self._sell(t.symbol, sell_qty, price)
        avg = cost / qty
        pnl = (fill.price - avg) * fill.amount
        remaining = max(qty - fill.amount, 0.0)
        self.db.set_position(m.name, t.symbol, remaining, avg * remaining)
        self.db.log_order(m.name, fill, pnl, self.dry_run, f"mestre vendeu {fraction:.1%}")
        log.info("[%s] VENDA %s %.6f @ %.4f  PnL %+.2f USDT", m.name, t.symbol,
                 fill.amount, fill.price, pnl)

    # ------------------------------------------------------------------
    def _buy(self, symbol: str, usdt: float) -> Fill:
        if self.dry_run:
            p = self.ex.price(symbol)
            return Fill(symbol, "buy", usdt / p, p, usdt)
        return self.ex.market_buy_usdt(symbol, usdt)

    def _sell(self, symbol: str, qty: float, price: float) -> Fill:
        if self.dry_run:
            return Fill(symbol, "sell", qty, price, qty * price)
        return self.ex.market_sell(symbol, qty)

    def _daily_loss_hit(self) -> bool:
        midnight = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        pnl = self.db.realized_pnl_since(int(midnight.timestamp() * 1000))
        return pnl <= -self.risk.daily_loss_limit_usdt
