"""Roda o laboratório 24/7:  py -m lab   e abra http://127.0.0.1:8765"""
import logging
import os
import threading
import time
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

from . import market
from .engine import SYMBOLS, Lab
from .report import write_report
from .server import serve

ROOT = Path.cwd()
STATE = ROOT / "lab_state.pkl"
REPORTS = ROOT / "relatorios"


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    log = logging.getLogger("lab")
    lock = threading.Lock()

    lab = Lab.load(STATE)
    if lab:
        log.info("estado anterior carregado (%s decisões até agora)", f"{lab.decisions:,}")
    else:
        lab = Lab()
        log.info("começando do zero: aquecendo com as últimas ~16h de candles reais...")
    with lock:
        lab.catch_up()  # preenche o tempo em que ficou desligado (até ~16h)

    serve(lab, lock, REPORTS, lambda: write_report(lab, REPORTS))
    url = "http://127.0.0.1:8765"
    log.info("painel em %s  (Ctrl+C para parar)", url)
    if not os.environ.get("LAB_NO_BROWSER"):
        try:
            webbrowser.open(url)
        except Exception:
            pass

    last_meme = last_save = 0.0
    try:
        while True:
            t = time.time()
            try:
                for s in SYMBOLS:
                    ks = market.klines(s, 5)
                    with lock:
                        for k in ks:
                            lab.on_candle(s, k)
            except Exception as e:
                log.warning("cripto: %s", e)
            if t - last_meme >= 60:
                last_meme = t
                try:
                    with lock:
                        lab.meme_tick()
                except Exception as e:
                    log.warning("memecoin: %s", e)
            if t - last_save >= 60:
                last_save = t
                with lock:
                    lab.save(STATE)
                    day = datetime.now(timezone.utc).date()
                    if lab.last_report_day != day:
                        if lab.last_report_day is not None:
                            log.info("relatório diário: %s", write_report(lab, REPORTS))
                        lab.last_report_day = day
            time.sleep(10)
    except KeyboardInterrupt:
        with lock:
            lab.save(STATE)
            log.info("salvo. relatório: %s", write_report(lab, REPORTS))


if __name__ == "__main__":
    main()
