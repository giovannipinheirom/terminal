"""O "cérebro": aprende com o histórico de cada mestre e decide quanto confiar nele.

Para cada mestre ele reconstrói as posições (preço médio), calcula o lucro realizado
de cada venda e mantém estatísticas: taxa de acerto, profit factor e drawdown.
Disso sai um multiplicador:
    0                 -> mestre pausado (não abre novas compras; vendas ainda são copiadas)
    probation         -> poucos trades fechados, ainda em teste
    até max_multiplier -> mestre com bom desempenho recebe mais capital
"""
from dataclasses import dataclass, field

from .config import BrainCfg
from .models import Trade


@dataclass
class MasterBrain:
    name: str
    cfg: BrainCfg
    positions: dict[str, list[float]] = field(default_factory=dict)  # symbol -> [qty, avg]
    closed: int = 0
    wins: int = 0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    cum_pnl: float = 0.0
    peak_pnl: float = 0.0
    max_exposure: float = 0.0
    max_dd_pct: float = 0.0

    def qty(self, symbol: str) -> float:
        return self.positions.get(symbol, [0.0, 0.0])[0]

    def learn(self, t: Trade) -> None:
        qty, avg = self.positions.get(t.symbol, [0.0, 0.0])
        if t.side == "buy":
            new_qty = qty + t.amount
            avg = (qty * avg + t.cost) / new_qty if new_qty else 0.0
            self.positions[t.symbol] = [new_qty, avg]
        else:
            sold = min(t.amount, qty)  # o que foi comprado antes do histórico é ignorado
            if sold > 0:
                pnl = (t.price - avg) * sold
                self.closed += 1
                if pnl > 0:
                    self.wins += 1
                    self.gross_profit += pnl
                else:
                    self.gross_loss += -pnl
                self.cum_pnl += pnl
                self.peak_pnl = max(self.peak_pnl, self.cum_pnl)
            self.positions[t.symbol] = [qty - sold, avg if qty - sold > 1e-12 else 0.0]

        exposure = sum(q * a for q, a in self.positions.values())
        self.max_exposure = max(self.max_exposure, exposure)
        base = self.max_exposure + self.peak_pnl
        if base > 0:
            dd = min((self.peak_pnl - self.cum_pnl) / base * 100, 100.0)
            self.max_dd_pct = max(self.max_dd_pct, dd)

    # ---- métricas ----
    @property
    def win_rate(self) -> float:
        return self.wins / self.closed if self.closed else 0.0

    @property
    def profit_factor(self) -> float:
        if self.gross_loss == 0:
            return 3.0 if self.gross_profit > 0 else 0.0
        return min(self.gross_profit / self.gross_loss, 3.0)

    @property
    def paused(self) -> bool:
        if self.closed < self.cfg.min_closed_trades:
            return False
        return (self.max_dd_pct > self.cfg.max_drawdown_pct
                or self.profit_factor < self.cfg.min_profit_factor)

    @property
    def multiplier(self) -> float:
        if self.paused:
            return 0.0
        if self.closed < self.cfg.min_closed_trades:
            return self.cfg.probation_multiplier
        dd_factor = max(0.0, 1 - self.max_dd_pct / self.cfg.max_drawdown_pct)
        m = (self.profit_factor / 2) * (0.5 + self.win_rate) * dd_factor
        return round(min(max(m, 0.0), self.cfg.max_multiplier), 3)

    def summary(self) -> str:
        status = "PAUSADO" if self.paused else (
            "teste" if self.closed < self.cfg.min_closed_trades else "ativo")
        return (f"{self.name:<12} {status:<8} mult={self.multiplier:<5} trades={self.closed:<4} "
                f"acerto={self.win_rate:5.1%} PF={self.profit_factor:4.2f} "
                f"DD={self.max_dd_pct:5.1f}% PnL={self.cum_pnl:+.2f}")
