"""Camada de acesso à Binance Spot via CCXT.

Mestres usam chaves SOMENTE LEITURA. A conta seguidora usa chave com permissão de
trade spot (nunca habilite saque).
"""
from .models import Fill, Trade


class BinanceSpot:
    def __init__(self, api_key: str, api_secret: str, testnet: bool):
        import ccxt  # importado aqui para a simulação rodar sem ccxt instalado

        self.x = ccxt.binance({
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
            "options": {"defaultType": "spot"},
        })
        if testnet:
            self.x.set_sandbox_mode(True)
        self.x.load_markets()

    def fetch_trades(self, symbol: str, since_ms: int) -> list[Trade]:
        """Todos os trades desde since_ms. A Binance limita cada consulta a janelas de 24h,
        então paginamos dia a dia (e dentro do dia, de 500 em 500)."""
        day = 86_400_000
        now = self.x.milliseconds()
        out: dict[str, Trade] = {}
        start = since_ms
        while start <= now:
            end = min(start + day - 1, now)
            cursor = start
            while True:
                raw = self.x.fetch_my_trades(symbol, since=cursor, limit=500,
                                             params={"endTime": end})
                for t in raw:
                    out[str(t["id"])] = Trade(
                        id=str(t["id"]), symbol=t["symbol"], side=t["side"],
                        amount=float(t["amount"]), price=float(t["price"]),
                        cost=float(t["cost"]), timestamp=int(t["timestamp"]))
                if len(raw) < 500:
                    break
                cursor = int(raw[-1]["timestamp"]) + 1
            start = end + 1
        return sorted(out.values(), key=lambda t: (t.timestamp, t.id))

    def price(self, symbol: str) -> float:
        return float(self.x.fetch_ticker(symbol)["last"])

    def balances(self) -> dict[str, float]:
        b = self.x.fetch_balance()
        return {k: float(v) for k, v in b["total"].items() if v}

    def equity_usdt(self, symbols: list[str]) -> float:
        """Patrimônio aproximado: USDT + ativos base dos símbolos monitorados."""
        bal = self.balances()
        total = bal.get("USDT", 0.0)
        for s in symbols:
            base = s.split("/")[0]
            if bal.get(base):
                total += bal[base] * self.price(s)
        return total

    def base_balance(self, symbol: str) -> float:
        return self.balances().get(symbol.split("/")[0], 0.0)

    def market_buy_usdt(self, symbol: str, usdt: float) -> Fill:
        o = self.x.create_market_buy_order_with_cost(symbol, usdt)
        return self._fill(symbol, "buy", o)

    def market_sell(self, symbol: str, amount: float) -> Fill:
        amount = float(self.x.amount_to_precision(symbol, amount))
        o = self.x.create_market_sell_order(symbol, amount)
        return self._fill(symbol, "sell", o)

    @staticmethod
    def _fill(symbol: str, side: str, o: dict) -> Fill:
        amount = float(o.get("filled") or o.get("amount") or 0)
        cost = float(o.get("cost") or 0)
        price = float(o.get("average") or (cost / amount if amount else 0))
        return Fill(symbol, side, amount, price, cost)
