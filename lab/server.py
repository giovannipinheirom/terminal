"""Painel local: http://127.0.0.1:8765"""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .agents import BinaryAgent
from .engine import SYMBOLS, now_ms

STATIC = Path(__file__).parent / "static" / "index.html"


def build_state(lab, reports_dir: Path) -> dict:
    def agent_rows(agents, cb):
        rows = []
        for a in agents:
            s = a.wallet.summary()
            sc = cb.score(a)
            s.update(kind=a.kind, score=None if sc is None else round(sc, 2),
                     following=a.name in cb.following)
            rows.append(s)
        return sorted(rows, key=lambda r: -r["pnl"])

    def copy_view(cb, name_of=lambda s: s):
        s = cb.wallet.summary()
        return {
            **s, "following": cb.following,
            "log": list(cb.log)[-40:][::-1],
            "history": [[t // 1000, v] for t, v in cb.wallet.history][-1500:],
            "positions": [{"agent": k[0], "symbol": name_of(p["symbol"]), "cost": round(p["cost"], 2),
                           "value": round(p["qty"] * cb.wallet.last_prices.get(p["symbol"], 0), 2)}
                          for k, p in cb.wallet.pos.items()],
        }

    meme_name = lambda a: lab.meme_names.get(a, a[:6])
    memes = sorted(lab.meme_q.values(), key=lambda x: -x["vol_h1"])[:40]
    monkeys = [b for b in lab.binary if b.strategy == "macaco"]
    return {
        "now": now_ms(), "started": lab.started, "decisions": lab.decisions,
        "copy": {"cripto": copy_view(lab.copy["cripto"]),
                 "memecoin": copy_view(lab.copy["memecoin"], meme_name)},
        "crypto": agent_rows(lab.crypto, lab.copy["cripto"]),
        "meme": agent_rows(lab.meme, lab.copy["memecoin"]),
        "binary": sorted([b.summary() for b in lab.binary], key=lambda r: -r["p80"]),
        "binary_breakeven": {f"p{int(p * 100)}": round(100 / (1 + p), 1) for p in BinaryAgent.PAYOUTS},
        "binary_monkey_wr": round(sum(b.win_rate for b in monkeys) / max(len(monkeys), 1), 1),
        "memes": [{k: m[k] for k in ("symbol", "price", "liq", "vol_h1", "chg_m5", "chg_h1",
                                      "buys_m5", "sells_m5", "url")} for m in memes],
        "reports": sorted((p.name for p in reports_dir.glob("*.md")), reverse=True)[:30],
    }


def candles_payload(lab, symbol: str) -> dict:
    arr = lab.candles.get(symbol, [])[-600:]
    first = arr[0]["t"] if arr else 0
    marks = [{"time": (t["ts"] - 60_000) // 1000, "side": t["side"]}
             for t in lab.copy["cripto"].wallet.trades
             if t["symbol"] == symbol and t["ts"] - 60_000 >= first]
    return {"candles": [{"time": k["t"] // 1000, "open": k["o"], "high": k["h"], "low": k["l"],
                         "close": k["c"], "volume": k["v"]} for k in arr],
            "markers": marks}


def serve(lab, lock: threading.Lock, reports_dir: Path, make_report, port: int = 8765):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body: bytes, ctype="application/json; charset=utf-8"):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            u = urlparse(self.path)
            q = parse_qs(u.query)
            try:
                if u.path == "/":
                    return self._send(200, STATIC.read_bytes(), "text/html; charset=utf-8")
                if u.path == "/api/state":
                    with lock:
                        data = build_state(lab, reports_dir)
                    return self._send(200, json.dumps(data).encode())
                if u.path == "/api/candles":
                    s = q.get("s", ["BTCUSDT"])[0]
                    if s not in SYMBOLS:
                        return self._send(400, b"{}")
                    with lock:
                        data = candles_payload(lab, s)
                    return self._send(200, json.dumps(data).encode())
                if u.path == "/api/report":
                    name = q.get("name", [""])[0]
                    if name == "novo":
                        with lock:
                            p = make_report()
                        name = p.name
                    p = reports_dir / Path(name).name
                    if not p.exists():
                        return self._send(404, b"{}")
                    return self._send(200, json.dumps({"name": p.name, "text": p.read_text(encoding="utf-8")}).encode())
            except Exception as e:  # nunca derruba o servidor
                return self._send(500, json.dumps({"erro": str(e)}).encode())
            self._send(404, b"{}")

    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv
