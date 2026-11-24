"""Simulação offline (sem Binance, sem chaves): verifica a lógica do sistema.

Dois mestres com histórico: "bom" (lucra com frequência) e "ruim" (perde muito).
Depois do aquecimento, os dois fazem novos trades e conferimos o que foi copiado.
Rode: py simulate.py
"""
import logging
import os
import tempfile

from copytrader.config import BrainCfg, Config, MasterCfg, RiskCfg
from copytrader.engine import Engine
from copytrader.models import Trade
from copytrader.storage import Storage

DAY = 86_400_000
NOW = 1_800_000_000_000


class FakeExchange:
    def __init__(self, prices):
        self.prices = prices
        self.trades: dict[str, list[Trade]] = {}
        self.equity = 1000.0

    def add(self, t: Trade):
        self.trades.setdefault(t.symbol, []).append(t)

    def fetch_trades(self, symbol, since_ms):
        return [t for t in self.trades.get(symbol, []) if t.timestamp >= since_ms]

    def price(self, symbol):
        return self.prices[symbol]

    def equity_usdt(self, symbols):
        return self.equity


def T(i, side, amount, price, ts, sym="BTC/USDT"):
    return Trade(str(i), sym, side, amount, price, amount * price, ts)


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
    prices = {"BTC/USDT": 100.0}
    good, bad, follower = FakeExchange(prices), FakeExchange(prices), FakeExchange(prices)

    # histórico (aquecimento): "bom" ganha 6 de 7, "ruim" perde 6 de 7
    for k in range(7):
        ts = NOW - (20 - k) * DAY
        good.add(T(f"g{k}b", "buy", 1, 100, ts))
        good.add(T(f"g{k}s", "sell", 1, 110 if k else 95, ts + 1000))
        bad.add(T(f"r{k}b", "buy", 1, 100, ts))
        bad.add(T(f"r{k}s", "sell", 1, 70 if k else 105, ts + 1000))

    cfg = Config(
        testnet=True, dry_run=True, poll_seconds=0, symbols=["BTC/USDT"],
        db_path=os.path.join(tempfile.mkdtemp(), "sim.db"),
        follower_key="", follower_secret="",
        masters=[MasterCfg("bom", budget_usdt=200), MasterCfg("ruim", budget_usdt=200)],
        brain=BrainCfg(), risk=RiskCfg(max_order_usdt=50, min_order_usdt=6),
    )
    clock = [NOW]
    eng = Engine(cfg, follower, {"bom": good, "ruim": bad}, Storage(cfg.db_path),
                 clock=lambda: clock[0])
    eng.warmup()
    print("\n== depois do aquecimento ==\n" + eng.status())

    b = eng.brains
    assert b["bom"].multiplier > 1.0, b["bom"].summary()
    assert b["ruim"].paused, b["ruim"].summary()
    assert eng.db.all_positions() == [], "nada do histórico pode ser copiado"

    # novos trades ao vivo: os dois compram 2 BTC a 100 (20% de um patrimônio de 1000)
    good.add(T("g-live-1", "buy", 2, 100, NOW + 1000))
    bad.add(T("r-live-1", "buy", 2, 100, NOW + 1000))
    eng.poll_once()
    pos = {(m, s): (q, c) for m, s, q, c in eng.db.all_positions()}
    assert ("ruim", "BTC/USDT") not in pos, "mestre pausado não pode ser copiado"
    q, c = pos[("bom", "BTC/USDT")]
    expected = 0.2 * 200 * b["bom"].multiplier
    assert abs(c - min(expected, 50)) < 1e-6, (c, expected)
    print(f"\ncompra copiada do 'bom': {c:.2f} USDT (esperado {min(expected, 50):.2f})")

    # mestre vende metade a 120 -> seguidor vende metade
    prices["BTC/USDT"] = 120.0
    good.add(T("g-live-2", "sell", 1, 120, NOW + 2000))
    eng.poll_once()
    q2, _ = eng.db.position("bom", "BTC/USDT")
    assert abs(q2 - q / 2) < 1e-9, (q2, q)
    print(f"venda parcial: posição {q:.4f} -> {q2:.4f} BTC")

    # mestre vende o resto -> seguidor zera
    good.add(T("g-live-3", "sell", 1, 120, NOW + 3000))
    eng.poll_once()
    assert eng.db.position("bom", "BTC/USDT")[0] == 0
    pnl = eng.db.realized_pnl_since(0)
    assert pnl > 0
    print(f"posição zerada, lucro realizado simulado: {pnl:+.2f} USDT")

    # trade repetido não é copiado duas vezes
    eng.poll_once()
    assert eng.db.position("bom", "BTC/USDT")[0] == 0

    print("\n== status final ==\n" + eng.status())
    print("\nOK: todas as verificações passaram")


if __name__ == "__main__":
    main()
