"""Dados de mercado REAIS e públicos (sem chave de API).

- Cripto (BTC/ETH/SOL): API pública da Binance, candles de 1 minuto.
- Memecoins (Solana): API pública do Dexscreener.
"""
import json
import time
import urllib.request

UA = {"User-Agent": "paper-trading-lab/1.0"}


def _get(url: str, timeout: float = 15):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


# ---------------------------------------------------------------- Binance
def klines(symbol: str, limit: int = 1000) -> list[dict]:
    """Candles de 1m FECHADOS, do mais antigo para o mais novo."""
    # o último candle da resposta é sempre o que ainda está aberto: descartamos.
    # (não usamos o relógio do PC, que pode estar adiantado ou atrasado)
    raw = _get(f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1m&limit={limit + 1}")
    return [
        {"t": k[0], "o": float(k[1]), "h": float(k[2]), "l": float(k[3]), "c": float(k[4]),
         "v": float(k[5])}
        for k in raw[:-1]
    ]


# ---------------------------------------------------------------- Dexscreener
def trending_solana_tokens() -> list[str]:
    """Endereços das memecoins Solana em destaque agora."""
    out: list[str] = []
    for url in ("https://api.dexscreener.com/token-boosts/top/v1",
                "https://api.dexscreener.com/token-boosts/latest/v1",
                "https://api.dexscreener.com/token-profiles/latest/v1"):
        try:
            for t in _get(url):
                a = t.get("tokenAddress")
                if t.get("chainId") == "solana" and a and a not in out:
                    out.append(a)
        except Exception:
            pass
    return out


def meme_quotes(addresses: list[str]) -> dict[str, dict]:
    """Cotação atual de cada token (o par com mais liquidez)."""
    out: dict[str, dict] = {}
    for i in range(0, len(addresses), 30):
        batch = addresses[i:i + 30]
        try:
            pairs = _get("https://api.dexscreener.com/latest/dex/tokens/" + ",".join(batch)).get("pairs") or []
        except Exception:
            continue
        for p in pairs:
            if p.get("chainId") != "solana" or not p.get("priceUsd"):
                continue
            addr = p["baseToken"]["address"]
            liq = (p.get("liquidity") or {}).get("usd") or 0
            if addr in out and out[addr]["liq"] >= liq:
                continue
            tx5 = (p.get("txns") or {}).get("m5") or {}
            out[addr] = {
                "addr": addr,
                "symbol": p["baseToken"].get("symbol", "?"),
                "price": float(p["priceUsd"]),
                "liq": float(liq),
                "vol_h1": float((p.get("volume") or {}).get("h1") or 0),
                "chg_m5": float((p.get("priceChange") or {}).get("m5") or 0),
                "chg_h1": float((p.get("priceChange") or {}).get("h1") or 0),
                "buys_m5": int(tx5.get("buys") or 0),
                "sells_m5": int(tx5.get("sells") or 0),
                "url": p.get("url", ""),
            }
    return out
