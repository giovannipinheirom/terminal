"""Ponto de entrada: python -m copytrader [config.toml]"""
import logging
import sys

from .config import load_config
from .engine import Engine
from .exchange import BinanceSpot
from .storage import Storage


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s",
                        datefmt="%H:%M:%S")
    cfg = load_config(sys.argv[1] if len(sys.argv) > 1 else "config.toml")

    missing = [m.name for m in cfg.masters if not m.api_key]
    if missing:
        sys.exit(f"Faltam chaves dos mestres no .env: {', '.join(missing)}")
    if not cfg.dry_run and not cfg.follower_key:
        sys.exit("Falta FOLLOWER_KEY/FOLLOWER_SECRET no .env (obrigatório fora do dry_run)")

    follower = BinanceSpot(cfg.follower_key, cfg.follower_secret, cfg.testnet)
    masters = {m.name: BinanceSpot(m.api_key, m.api_secret, cfg.testnet) for m in cfg.masters}
    engine = Engine(cfg, follower, masters, Storage(cfg.db_path))
    try:
        engine.run()
    except KeyboardInterrupt:
        logging.info("encerrado. status final:\n%s", engine.status())


if __name__ == "__main__":
    main()
