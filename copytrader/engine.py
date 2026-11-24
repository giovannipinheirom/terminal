"""Loop principal: monitora os mestres, educa o cérebro e dispara as cópias."""
import logging
import time

from .brain import MasterBrain
from .config import Config, MasterCfg
from .copier import Copier
from .storage import Storage

log = logging.getLogger("engine")


class Engine:
    def __init__(self, cfg: Config, follower, master_clients: dict, storage: Storage,
                 clock=lambda: int(time.time() * 1000)):
        self.cfg = cfg
        self.db = storage
        self.masters = master_clients            # nome -> cliente da exchange
        self.clock = clock
        self.copier = Copier(follower, storage, cfg.risk, cfg.dry_run)
        self.brains: dict[str, MasterBrain] = {}
        self.start_ms = 0

    def warmup(self) -> None:
        """Baixa o histórico dos mestres e educa o cérebro. Nada é copiado aqui."""
        self.start_ms = self.clock()
        since_default = self.start_ms - self.cfg.brain.warmup_days * 86_400_000
        for m in self.cfg.masters:
            self._fetch_new(m, since_default)
            brain = MasterBrain(m.name, self.cfg.brain)
            for t in self.db.master_trades(m.name):
                brain.learn(t)
            self.brains[m.name] = brain
            log.info("histórico carregado: %s", brain.summary())

    def poll_once(self) -> None:
        for m in self.cfg.masters:
            try:
                self._poll_master(m)
            except Exception:
                log.exception("[%s] erro ao consultar mestre", m.name)

    def _poll_master(self, m: MasterCfg) -> None:
        new = self._fetch_new(m, self.start_ms)
        if not new:
            return
        client = self.masters[m.name]
        equity = client.equity_usdt(self.cfg.symbols)
        brain = self.brains[m.name]
        for t in new:
            if t.timestamp >= self.start_ms:
                self.copier.on_master_trade(m, brain, t, equity)
            brain.learn(t)  # aprende DEPOIS de copiar (a venda usa a posição anterior)

    def _fetch_new(self, m: MasterCfg, since_default: int):
        client = self.masters[m.name]
        new = []
        for s in self.cfg.symbols:
            last = self.db.last_trade_ts(m.name, s)
            since = last if last is not None else since_default
            for t in client.fetch_trades(s, since):
                if self.db.add_master_trade(m.name, t):
                    new.append(t)
        return sorted(new, key=lambda t: (t.timestamp, t.id))

    def status(self) -> str:
        lines = [b.summary() for b in self.brains.values()]
        for master, sym, qty, cost in self.db.all_positions():
            lines.append(f"  posição [{master}] {sym}: {qty:.6f} (custo {cost:.2f} USDT)")
        return "\n".join(lines)

    def run(self) -> None:
        self.warmup()
        log.info("monitorando %d mestre(s) em %s | dry_run=%s testnet=%s",
                 len(self.cfg.masters), ", ".join(self.cfg.symbols),
                 self.cfg.dry_run, self.cfg.testnet)
        n = 0
        while True:
            self.poll_once()
            n += 1
            if n % 60 == 0:
                log.info("status:\n%s", self.status())
            time.sleep(self.cfg.poll_seconds)
