"""Tipos de dados compartilhados."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Trade:
    """Uma execução (fill) feita por uma conta mestre."""
    id: str
    symbol: str      # ex: "BTC/USDT"
    side: str        # "buy" ou "sell"
    amount: float    # quantidade do ativo base
    price: float
    cost: float      # amount * price, na moeda de cotação (USDT)
    timestamp: int   # ms


@dataclass(frozen=True)
class Fill:
    """Resultado de uma ordem enviada para a conta seguidora."""
    symbol: str
    side: str
    amount: float
    price: float
    cost: float
