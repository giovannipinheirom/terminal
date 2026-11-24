"""Os agentes (os "traders" que o copy bot pode seguir).

Cada agente tem uma carteira de US$ 1000 fictícios e uma estratégia diferente.
Também existem agentes ALEATÓRIOS ("macacos"): se uma estratégia não bate os macacos,
o resultado dela é sorte, não habilidade.
"""
import random

from .wallet import Wallet


# ============================================================ indicadores
def ema(xs, n):
    k = 2 / (n + 1)
    e = xs[0]
    for x in xs[1:]:
        e = x * k + e * (1 - k)
    return e


def rsi(xs, n=14):
    if len(xs) <= n:
        return 50.0
    gains = losses = 0.0
    for a, b in zip(xs[-n - 1:-1], xs[-n:]):
        d = b - a
        gains += max(d, 0)
        losses += max(-d, 0)
    if losses == 0:
        return 100.0
    return 100 - 100 / (1 + gains / losses)


def bollinger(xs, n=20, k=2.0):
    w = xs[-n:]
    m = sum(w) / len(w)
    sd = (sum((x - m) ** 2 for x in w) / len(w)) ** 0.5
    return m - k * sd, m, m + k * sd


# ============================================================ cripto (spot, só compra)
class CryptoAgent:
    niche = "cripto"
    kind = "?"

    def __init__(self, name: str):
        self.name = name
        self.wallet = Wallet(name)

    def signal(self, c: list[float], h: list[float], l: list[float], holding: bool):
        """Retorna 'buy', 'sell' ou None."""
        raise NotImplementedError


class EmaCross(CryptoAgent):
    kind = "Cruzamento de médias"

    def __init__(self, f, s):
        super().__init__(f"ema-{f}x{s}")
        self.f, self.s = f, s

    def signal(self, c, h, l, holding):
        w = c[-self.s * 3:]
        fast, slow = ema(w, self.f), ema(w, self.s)
        if not holding and fast > slow:
            return "buy"
        if holding and fast < slow:
            return "sell"


class RsiReversion(CryptoAgent):
    kind = "RSI (reversão)"

    def __init__(self, n, lo, hi):
        super().__init__(f"rsi-{n}-{lo}/{hi}")
        self.n, self.lo, self.hi = n, lo, hi

    def signal(self, c, h, l, holding):
        r = rsi(c, self.n)
        if not holding and r < self.lo:
            return "buy"
        if holding and r > self.hi:
            return "sell"


class Breakout(CryptoAgent):
    kind = "Rompimento"

    def __init__(self, n, exit_n):
        super().__init__(f"rompe-{n}/{exit_n}")
        self.n, self.exit_n = n, exit_n

    def signal(self, c, h, l, holding):
        if len(c) <= self.n:
            return None
        if not holding and c[-1] > max(h[-self.n - 1:-1]):
            return "buy"
        if holding and c[-1] < min(l[-self.exit_n - 1:-1]):
            return "sell"


class BollingerReversion(CryptoAgent):
    kind = "Bollinger (reversão)"

    def __init__(self, n, k):
        super().__init__(f"boll-{n}-{k}")
        self.n, self.k = n, k

    def signal(self, c, h, l, holding):
        if len(c) < self.n:
            return None
        lo, mid, hi = bollinger(c, self.n, self.k)
        if not holding and c[-1] < lo:
            return "buy"
        if holding and c[-1] > mid:
            return "sell"


class Momentum(CryptoAgent):
    kind = "Momentum"

    def __init__(self, n, pct):
        super().__init__(f"mom-{n}-{pct}%")
        self.n, self.pct = n, pct

    def signal(self, c, h, l, holding):
        if len(c) <= self.n:
            return None
        roc = (c[-1] / c[-self.n - 1] - 1) * 100
        if not holding and roc > self.pct:
            return "buy"
        if holding and roc < 0:
            return "sell"


class Macd(CryptoAgent):
    kind = "MACD"

    def __init__(self, f, s, sig):
        super().__init__(f"macd-{f}/{s}/{sig}")
        self.f, self.s, self.sig = f, s, sig

    def signal(self, c, h, l, holding):
        w = c[-self.s * 4:]
        if len(w) < self.s + self.sig:
            return None
        line = [ema(w[:i], self.f) - ema(w[:i], self.s) for i in range(len(w) - self.sig, len(w) + 1)]
        m, s = line[-1], ema(line, self.sig)
        if not holding and m > s:
            return "buy"
        if holding and m < s:
            return "sell"


class Monkey(CryptoAgent):
    kind = "Aleatório (controle)"

    def __init__(self, seed):
        super().__init__(f"macaco-{seed}")
        self.rng = random.Random(seed)

    def signal(self, c, h, l, holding):
        if self.rng.random() < 0.03:
            return "sell" if holding else "buy"


class HoldAgent(CryptoAgent):
    kind = "Comprar e segurar"

    def __init__(self):
        super().__init__("segurar")

    def signal(self, c, h, l, holding):
        return None if holding else "buy"


def crypto_agents() -> list[CryptoAgent]:
    a: list[CryptoAgent] = []
    a += [EmaCross(f, s) for f, s in [(5, 20), (9, 21), (12, 26), (20, 50), (5, 13), (8, 34), (3, 10), (10, 30)]]
    a += [RsiReversion(*p) for p in [(14, 30, 70), (14, 25, 65), (7, 20, 80), (21, 35, 65)]]
    a += [Breakout(*p) for p in [(20, 10), (55, 20), (30, 15), (10, 5), (5, 3)]]
    a += [BollingerReversion(*p) for p in [(20, 2.0), (20, 2.5), (30, 2.0)]]
    a += [Momentum(*p) for p in [(10, 0.2), (30, 0.4), (60, 0.6), (5, 0.1)]]
    a += [Macd(12, 26, 9), Macd(8, 17, 9)]
    a += [Monkey(s) for s in (1, 2, 3)]
    a += [HoldAgent()]
    return a  # 30 agentes


# ============================================================ memecoins
class MemeAgent:
    niche = "memecoin"
    kind = "Caçador de memecoin"
    TRADE_USD = 50.0
    MAX_OPEN = 5

    def __init__(self, min_m5, min_ratio, tp, sl, max_hold_min, monkey_seed=None):
        self.min_m5, self.min_ratio = min_m5, min_ratio
        self.tp, self.sl, self.max_hold = tp, sl, max_hold_min * 60_000
        self.rng = random.Random(monkey_seed) if monkey_seed is not None else None
        if self.rng:
            self.name, self.kind = f"meme-macaco-{monkey_seed}", "Aleatório (controle)"
        else:
            self.name = f"meme-{min_m5}%-r{min_ratio}-tp{int(tp * 100)}-{max_hold_min}m"
        self.wallet = Wallet(self.name)

    def wants_entry(self, q: dict) -> bool:
        if self.rng:
            return self.rng.random() < 0.02
        ratio = q["buys_m5"] / max(q["sells_m5"], 1)
        return q["chg_m5"] >= self.min_m5 and ratio >= self.min_ratio

    def wants_exit(self, pos: dict, q: dict, ts: int) -> bool:
        ch = q["price"] / (pos["cost"] / pos["qty"]) - 1
        return ch >= self.tp or ch <= -self.sl or ts - pos["ts"] >= self.max_hold


def meme_agents() -> list[MemeAgent]:
    a = [MemeAgent(m5, r, tp, 0.2, hold)
         for m5 in (3, 8, 15) for r in (1.2, 1.8) for tp in (0.3, 1.0) for hold in (30, 120)]
    a += [MemeAgent(0, 0, 0.3, 0.2, 60, monkey_seed=s) for s in (1, 2)]
    return a  # 26 agentes


# ============================================================ opções binárias (só simulação)
def _streak(c):
    n, d = 0, 0
    for a, b in zip(reversed(c[:-1]), reversed(c[1:])):
        s = 1 if b > a else -1 if b < a else 0
        if s == 0 or (d and s != d):
            break
        d, n = s, n + 1
    return n * d


def _b_rsi14(c, rng):
    r = rsi(c, 14)
    return "up" if r < 30 else "down" if r > 70 else None


def _b_rsi7(c, rng):
    r = rsi(c, 7)
    return "up" if r < 20 else "down" if r > 80 else None


def _b_trend_fast(c, rng):
    return "up" if ema(c[-63:], 9) > ema(c[-63:], 21) else "down"


def _b_trend_slow(c, rng):
    return "up" if ema(c[-150:], 20) > ema(c[-150:], 50) else "down"


def _b_streak_rev(c, rng):
    s = _streak(c)
    return "up" if s <= -3 else "down" if s >= 3 else None


def _b_streak_cont(c, rng):
    s = _streak(c)
    return "down" if s <= -3 else "up" if s >= 3 else None


def _b_boll(c, rng):
    lo, _, hi = bollinger(c, 20, 2)
    return "up" if c[-1] < lo else "down" if c[-1] > hi else None


def _b_monkey(c, rng):
    return rng.choice(["up", "down", None, None, None, None])


BINARY_STRATEGIES = {
    "rsi-30/70": ("RSI reversão", _b_rsi14),
    "rsi-20/80": ("RSI reversão", _b_rsi7),
    "tendencia-9/21": ("Segue tendência", _b_trend_fast),
    "tendencia-20/50": ("Segue tendência", _b_trend_slow),
    "3-velas-reversao": ("Reversão de sequência", _b_streak_rev),
    "3-velas-continua": ("Continuação de sequência", _b_streak_cont),
    "bollinger": ("Bollinger reversão", _b_boll),
    "macaco": ("Aleatório (controle)", _b_monkey),
}


class BinaryAgent:
    """Aposta se o preço vai SUBIR ou CAIR nos próximos `expiry` minutos."""
    niche = "binarias"
    STAKE = 10.0
    PAYOUTS = (0.80, 0.85, 0.90)

    def __init__(self, strategy: str, expiry: int = 5, seed: int = 0):
        self.strategy, self.expiry = strategy, expiry
        self.kind = BINARY_STRATEGIES[strategy][0]
        self.name = f"bin-{strategy}{'-' + str(seed) if seed else ''}-{expiry}min"
        self.rng = random.Random(seed)
        self.open: list[dict] = []
        self.bets = self.wins = self.losses = self.ties = 0

    def predict(self, c):
        return BINARY_STRATEGIES[self.strategy][1](c, self.rng)

    def balance(self, payout: float) -> float:
        return self.wins * self.STAKE * payout - self.losses * self.STAKE

    @property
    def win_rate(self) -> float:
        d = self.wins + self.losses
        return self.wins / d * 100 if d else 0.0

    def summary(self) -> dict:
        return {"name": self.name, "kind": self.kind, "bets": self.bets,
                "win_rate": round(self.win_rate, 1), "open": len(self.open),
                **{f"p{int(p * 100)}": round(self.balance(p), 2) for p in self.PAYOUTS}}


def binary_agents() -> list[BinaryAgent]:
    out = [BinaryAgent(s, 5) for s in BINARY_STRATEGIES if s != "macaco"]
    out += [BinaryAgent(s, 1) for s in ("rsi-30/70", "tendencia-9/21", "3-velas-reversao")]
    out += [BinaryAgent("macaco", 5, seed=s) for s in (1, 2, 3)]
    return out  # 13 agentes
