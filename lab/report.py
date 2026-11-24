"""Relatório diário em Markdown, pronto para colar no Claude (ou Codex) analisar."""
from datetime import datetime, timezone
from pathlib import Path

from .agents import BinaryAgent

PROMPT = """> **Para a IA que for analisar:** este é o relatório de um laboratório de paper trading
> (dinheiro fictício, preços reais). Analise com ceticismo: compare cada estratégia com os
> agentes "macaco" (aleatórios), aponte o que pode ser sorte, overfitting ou erro de simulação,
> e sugira UMA mudança de estratégia ou de parâmetro para testar amanhã. Não recomende colocar
> dinheiro real com base em poucos dias de dados.

"""


def _table(rows, cols):
    head = "| " + " | ".join(c for c, _ in cols) + " |\n|" + "---|" * len(cols) + "\n"
    return head + "".join("| " + " | ".join(str(f(r)) for _, f in cols) + " |\n" for r in rows)


def write_report(lab, reports_dir: Path) -> Path:
    reports_dir.mkdir(exist_ok=True)
    now = datetime.now(timezone.utc)
    hours = (now.timestamp() * 1000 - lab.started) / 3_600_000
    out = [f"# Relatório do laboratório — {now:%Y-%m-%d %H:%M} UTC\n", PROMPT,
           f"Rodando há {hours:.1f} h · {lab.decisions:,} decisões simuladas\n".replace(",", ".")]

    agent_cols = [("Agente", lambda a: a.name), ("Estratégia", lambda a: a.kind),
                  ("Resultado US$", lambda a: f"{a.wallet.equity() - a.wallet.start:+.2f}"),
                  ("Trades", lambda a: a.wallet.closed),
                  ("Acerto", lambda a: f"{a.wallet.win_rate:.0f}%"),
                  ("Queda máx.", lambda a: f"{a.wallet.max_dd:.1f}%")]

    for niche, agents in (("cripto", lab.crypto), ("memecoin", lab.meme)):
        cb = lab.copy[niche]
        s = cb.wallet.summary()
        ranked = sorted(agents, key=lambda a: -(a.wallet.equity()))
        monkeys = [a for a in agents if "macaco" in a.name]
        mk = sum(a.wallet.equity() - a.wallet.start for a in monkeys) / max(len(monkeys), 1)
        beat = sum(1 for a in agents if "macaco" not in a.name and a.wallet.equity() - a.wallet.start > mk)
        out += [f"\n## {niche.capitalize()}\n",
                f"**Copy bot:** patrimônio US$ {s['equity']:.2f} ({s['ret']:+.2f}%), "
                f"{s['closed']} trades fechados, acerto {s['win_rate']}%, queda máx. {s['max_dd']}%. "
                f"Seguindo agora: {', '.join(cb.following) or 'ninguém'}.\n",
                f"**Macacos (aleatórios):** resultado médio US$ {mk:+.2f}. "
                f"{beat} de {len(agents) - len(monkeys)} estratégias estão acima deles.\n",
                "\n### Top 10\n", _table(ranked[:10], agent_cols),
                "\n### Piores 5\n", _table(ranked[-5:], agent_cols)]

    be = {p: 100 / (1 + p) for p in BinaryAgent.PAYOUTS}
    out += ["\n## Opções binárias (só simulação)\n",
            "Para empatar, o acerto precisa ser de pelo menos " +
            ", ".join(f"{v:.1f}% (paga {int(p * 100)}%)" for p, v in be.items()) + ".\n\n",
            _table(sorted(lab.binary, key=lambda b: -b.balance(0.8)), [
                ("Agente", lambda b: b.name), ("Apostas", lambda b: b.bets),
                ("Acerto", lambda b: f"{b.win_rate:.1f}%"),
                *[(f"Saldo paga {int(p * 100)}%", (lambda p: lambda b: f"{b.balance(p):+.2f}")(p))
                  for p in BinaryAgent.PAYOUTS]])]

    path = reports_dir / f"{now:%Y-%m-%d}.md"
    path.write_text("".join(out), encoding="utf-8")
    return path
