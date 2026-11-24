"""Leitura do config.toml e das chaves no .env / variáveis de ambiente."""
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class MasterCfg:
    name: str
    budget_usdt: float          # quanto da conta seguidora fica reservado para copiar este mestre
    api_key: str = ""
    api_secret: str = ""


@dataclass
class BrainCfg:
    warmup_days: int = 30            # histórico usado para "educar" o bot ao iniciar
    min_closed_trades: int = 5       # abaixo disso o mestre fica em período de teste
    probation_multiplier: float = 0.5
    max_multiplier: float = 1.5
    max_drawdown_pct: float = 25.0   # acima disso o mestre é pausado
    min_profit_factor: float = 0.8   # abaixo disso o mestre é pausado


@dataclass
class RiskCfg:
    max_order_usdt: float = 50.0
    min_order_usdt: float = 6.0          # Binance spot exige ~5 USDT por ordem
    daily_loss_limit_usdt: float = 30.0  # atingiu -> para de abrir compras no dia


@dataclass
class Config:
    testnet: bool
    dry_run: bool
    poll_seconds: float
    symbols: list[str]
    db_path: str
    follower_key: str
    follower_secret: str
    masters: list[MasterCfg]
    brain: BrainCfg = field(default_factory=BrainCfg)
    risk: RiskCfg = field(default_factory=RiskCfg)


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def load_config(path: str = "config.toml") -> Config:
    p = Path(path)
    _load_dotenv(p.parent / ".env")
    raw = tomllib.loads(p.read_text(encoding="utf-8"))

    masters = []
    for m in raw["masters"]:
        env = m["name"].upper()
        masters.append(MasterCfg(
            name=m["name"],
            budget_usdt=float(m["budget_usdt"]),
            api_key=os.environ.get(f"MASTER_{env}_KEY", ""),
            api_secret=os.environ.get(f"MASTER_{env}_SECRET", ""),
        ))

    g = raw.get("general", {})
    return Config(
        testnet=g.get("testnet", True),
        dry_run=g.get("dry_run", True),
        poll_seconds=float(g.get("poll_seconds", 5)),
        symbols=g["symbols"],
        db_path=g.get("db_path", "copytrader.db"),
        follower_key=os.environ.get("FOLLOWER_KEY", ""),
        follower_secret=os.environ.get("FOLLOWER_SECRET", ""),
        masters=masters,
        brain=BrainCfg(**raw.get("brain", {})),
        risk=RiskCfg(**raw.get("risk", {})),
    )
