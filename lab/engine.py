"""O laboratório: roda todos os agentes no mercado real com dinheiro fictício,
o copy bot segue os melhores e tudo fica salvo em disco."""
import logging
import pickle
import time
from collections import deque
from pathlib import Path

from . import market
from .agents import BinaryAgent, binary_agents, crypto_agents, meme_agents
from .wallet import Wallet

log = logging.getLogger("lab")
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
CRYPTO_SLIP = 0.0005        # 0,05% de diferença de preço na execução
HOUR = 3_600_000


def meme_slip(usd: float, liq: float) -> float:
    """Impacto da ordem no preço da pool + ~1% de taxas da DEX/prioridade."""
    if liq <= 0:
        return 0.5
    return min(2 * usd / liq + 0.01, 0.5)


def now_ms() -> int:
    return int(time.time() * 1000)


# ======================================================================
class CopyBot:
    """Segue os K melhores agentes de um nicho e copia as operações deles,
    proporcional ao tamanho de cada operação."""

    def __init__(self, niche: str, agents: list, k: int = 5, min_closed: int = 3):
        self.niche, self.k, self.min_closed = niche, k, min_closed
        self.wallet = Wallet(f"copybot-{niche}")
        self.agents = agents
        self.following: list[str] = []
        self.last_rank = 0
        self.log = deque(maxlen=100)
        for a in agents:
            a.wallet.listeners.append(self.on_event)

    def score(self, a):
        w = a.wallet
        if w.closed < self.min_closed:
            return None
        return w.ret_pct - 0.5 * w.max_dd

    def ranking(self):
        scored = [(self.score(a), a) for a in self.agents]
        return sorted([x for x in scored if x[0] is not None], key=lambda x: -x[0])

    def rerank(self, ts: int, slip_for) -> None:
        self.last_rank = ts
        new = [a.name for s, a in self.ranking() if s > 0][: self.k]
        dropped = [n for n in self.following if n not in new]
        for key in [k for k in self.wallet.pos if k[0] in dropped]:
            sym = self.wallet.pos[key]["symbol"]
            px = self.wallet.last_prices.get(sym)
            if px:
                self.wallet.sell(ts, key, px, slip_for(sym))
        if new != self.following:
            self.log.append({"ts": ts, "msg": f"agora seguindo: {', '.join(new) or 'ninguém (nenhum agente com lucro)'}"})
        self.following = new

    def on_event(self, w, kind, ts, symbol, frac, price, slip):
        if w.name not in self.following:
            return
        key = (w.name, symbol)
        if kind == "buy":
            usd = frac * self.wallet.equity() / self.k
            if usd >= 1 and self.wallet.buy(ts, symbol, usd, price, slip, key=key):
                self.log.append({"ts": ts, "msg": f"copiou COMPRA de {w.name}: {symbol} US$ {usd:.2f}"})
        elif key in self.wallet.pos:
            pnl = self.wallet.sell(ts, key, price, slip)
            self.log.append({"ts": ts, "msg": f"copiou VENDA de {w.name}: {symbol} resultado US$ {pnl:+.2f}"})


# ======================================================================
class Lab:
    def __init__(self):
        self.crypto = crypto_agents()
        self.meme = meme_agents()
        self.binary = binary_agents()
        self.copy = {"cripto": CopyBot("cripto", self.crypto),
                     "memecoin": CopyBot("memecoin", self.meme)}
        self.candles: dict[str, list] = {s: [] for s in SYMBOLS}
        self.meme_q: dict[str, dict] = {}
        self.meme_names: dict[str, str] = {}
        self.meme_watch: list[str] = []
        self.meme_missing: dict[str, int] = {}
        self.last_trending = 0
        self.started = now_ms()
        self.decisions = 0
        self.last_report_day = None

    # ------------------------------------------------------------------ cripto + binárias
    def catch_up(self, limit: int = 1000) -> None:
        """Baixa candles recentes e processa os que ainda não vimos (em ordem de tempo)."""
        allk = []
        for s in SYMBOLS:
            try:
                allk += [(k["t"], s, k) for k in market.klines(s, limit)]
            except Exception as e:
                log.warning("falha ao baixar %s: %s", s, e)
        for _, s, k in sorted(allk, key=lambda x: (x[0], x[1])):
            self.on_candle(s, k)

    def on_candle(self, s: str, k: dict) -> None:
        arr = self.candles[s]
        if arr and k["t"] <= arr[-1]["t"]:
            return
        arr.append(k)
        if len(arr) > 1500:
            del arr[:-1500]
        ts, price = k["t"] + 60_000, k["c"]
        win = arr[-300:]
        c = [x["c"] for x in win]
        h = [x["h"] for x in win]
        l = [x["l"] for x in win]
        prices = {s: price}

        if len(c) >= 60:
            for a in self.crypto:
                w = a.wallet
                sig = a.signal(c, h, l, s in w.pos)
                self.decisions += 1
                if sig == "buy":
                    w.buy(ts, s, min(w.cash, w.equity() / len(SYMBOLS)), price, CRYPTO_SLIP)
                elif sig == "sell":
                    w.sell(ts, s, price, CRYPTO_SLIP)
            self._binary(s, len(arr) - 1, c, price, ts)

        for a in self.crypto:
            a.wallet.mark(ts, prices)
        cb = self.copy["cripto"]
        cb.wallet.mark(ts, prices)
        if ts - cb.last_rank >= HOUR:
            cb.rerank(ts, lambda sym: CRYPTO_SLIP)

    def _binary(self, s, idx, c, price, ts):
        for b in self.binary:
            keep = []
            for bet in b.open:
                if bet["sym"] == s and idx >= bet["idx"] + b.expiry:
                    up, down = price > bet["entry"], price < bet["entry"]
                    if not up and not down:
                        b.ties += 1
                    elif (bet["dir"] == "up") == up:
                        b.wins += 1
                    else:
                        b.losses += 1
                else:
                    keep.append(bet)
            b.open = keep
            self.decisions += 1
            if any(x["sym"] == s for x in b.open):
                continue
            d = b.predict(c)
            if d:
                b.open.append({"sym": s, "idx": idx, "entry": price, "dir": d, "ts": ts})
                b.bets += 1

    # ------------------------------------------------------------------ memecoins
    def meme_tick(self) -> None:
        ts = now_ms()
        if ts - self.last_trending > 5 * 60_000 or not self.meme_watch:
            t = market.trending_solana_tokens()
            if t:
                self.meme_watch = t[:60]
            self.last_trending = ts
        held = {k for a in self.meme for k in a.wallet.pos}
        held |= {k[1] for k in self.copy["memecoin"].wallet.pos}
        q = market.meme_quotes(list(dict.fromkeys(self.meme_watch + sorted(held))))
        if not q:
            return
        self.meme_q = q
        for a, x in q.items():
            self.meme_names[a] = x["symbol"]
        for addr in held:
            self.meme_missing[addr] = 0 if addr in q else self.meme_missing.get(addr, 0) + 1
        prices = {a: x["price"] for a, x in q.items()}

        for agent in self.meme:
            w = agent.wallet
            w.mark(ts, prices)
            for addr, pos in list(w.pos.items()):
                qq = q.get(addr)
                if qq is None:
                    if self.meme_missing.get(addr, 0) >= 10:   # sumiu: trata como rug pull
                        w.sell(ts, addr, w.last_prices.get(addr, 0), 0.5, haircut=0.1)
                    continue
                value = pos["qty"] * qq["price"]
                if qq["liq"] < 2000 or agent.wants_exit(pos, qq, ts):
                    w.sell(ts, addr, qq["price"], meme_slip(value, qq["liq"]))
            for addr, qq in q.items():
                if len(w.pos) >= agent.MAX_OPEN:
                    break
                if addr in w.pos or qq["liq"] < 20_000 or qq["vol_h1"] < 5_000:
                    continue
                self.decisions += 1
                if agent.wants_entry(qq):
                    w.buy(ts, addr, agent.TRADE_USD, qq["price"], meme_slip(agent.TRADE_USD, qq["liq"]))

        cb = self.copy["memecoin"]
        cb.wallet.mark(ts, prices)
        if ts - cb.last_rank >= HOUR:
            cb.rerank(ts, lambda sym: meme_slip(50, (self.meme_q.get(sym) or {}).get("liq", 0)))

    # ------------------------------------------------------------------ persistência
    def save(self, path: Path) -> None:
        tmp = path.with_suffix(".tmp")
        with open(tmp, "wb") as f:
            pickle.dump(self, f)
        tmp.replace(path)

    @staticmethod
    def load(path: Path) -> "Lab | None":
        if not path.exists():
            return None
        try:
            with open(path, "rb") as f:
                return pickle.load(f)
        except Exception as e:
            log.warning("não consegui ler o estado salvo (%s); começando do zero", e)
            return None
