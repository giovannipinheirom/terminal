# Laboratório Copy Trade (paper trading, 24/7)

**Dinheiro fictício, mercado real.** Não precisa de conta, chave de API nem instalar nada
além do **Python 3.10 ou mais novo** (<https://www.python.org/downloads/>; no Windows marque
"Add python.exe to PATH" na instalação).

- **Windows:** dois cliques em `iniciar_laboratorio.bat`. Se abrir num editor de texto em vez
  de rodar, clique com o botão direito no arquivo → **Abrir**, ou rode `py -m lab` no terminal
  dentro da pasta.
- **Mac / Linux:** no terminal, dentro da pasta: `bash iniciar_laboratorio.sh`

O painel abre em <http://127.0.0.1:8765>.

O que roda:

| Nicho | Agentes | Dados reais de |
|---|---|---|
| Cripto (BTC, ETH, SOL) | 30 estratégias (médias, RSI, rompimento, Bollinger, momentum, MACD) + 3 aleatórias + "comprar e segurar" | Binance, candles de 1 min |
| Memecoins (Solana) | 24 caçadores com parâmetros diferentes + 2 aleatórios | Dexscreener, a cada 1 min |
| Opções binárias | 13 apostadores (1 e 5 min), com saldo para pagamentos de 80/85/90% | Binance |

- **Copy bot:** a cada hora escolhe os 5 melhores agentes de cada nicho (lucro menos
  metade da queda máxima, mínimo de 3 trades) e copia as operações deles.
- **Realismo:** 0,1% de taxa e 0,05% de slippage em cripto. Nas memecoins, 1% de taxa,
  impacto no preço pela liquidez da pool e rug pull (perda de 90%) quando a moeda some.
- **Agentes "macaco":** operam aleatoriamente. Servem de régua: se uma estratégia não
  ganha deles, o lucro é sorte.
- **Relatório diário** em `relatorios/AAAA-MM-DD.md`, pronto para colar no Claude
  (aba "Rotinas e perguntas" no painel).
- O estado fica salvo em `lab_state.pkl`. Se você desligar e religar, ele continua de onde
  parou e preenche até ~16 h de candles que perdeu.

---

# CopyTrader — copy trading local na Binance Spot (dinheiro real/testnet)

Um bot que **monitora contas mestre**, **aprende com o histórico de cada uma** e
**replica as operações** numa conta seguidora, com limites de risco.

## Como funciona

```
 Mestre A ─┐                       ┌─────────────┐
 Mestre B ─┼─► Monitor (lê trades) ─► Cérebro     ─► Copiador ─► Conta seguidora
 Mestre C ─┘    a cada 5s          │ avalia cada  │  (limites      (Binance)
                                   │ mestre       │   de risco)
                                   └─────────────┘
```

1. **Aquecimento:** ao iniciar, baixa os últimos `warmup_days` de trades de cada mestre
   e "educa" o cérebro. **Nada do histórico é copiado.**
2. **Cérebro:** para cada mestre calcula taxa de acerto, *profit factor* (lucro ÷ perda)
   e *drawdown* (maior queda). Daí sai um multiplicador:
   - `0` → **pausado** (drawdown alto ou perdendo). Novas compras não são copiadas,
     mas as vendas continuam sendo copiadas para você sair das posições.
   - `0.5` → **em teste** (menos de `min_closed_trades` trades fechados).
   - até `1.5` → **ativo**. Quanto melhor o mestre, mais capital ele recebe.
   O cérebro continua aprendendo com cada trade novo.
3. **Cópia proporcional:**
   - **Compra:** se o mestre usou 10% do patrimônio dele, você usa 10% de
     `budget_usdt × multiplicador`.
   - **Venda:** se o mestre vendeu metade da posição, você vende metade da sua.
4. **Limites de risco:** valor máximo por ordem, orçamento por mestre, limite de perda
   diária e ordens mínimas da Binance.

Cada mestre tem as próprias posições na conta seguidora (ficam no SQLite). Assim, a venda
de um mestre nunca mexe no que foi comprado copiando outro.

## Instalação (Windows)

```bash
py -m pip install -r requirements.txt
```

```bash
copy config.example.toml config.toml
```

```bash
copy .env.example .env
```

## Chaves de API

- **Mestres:** crie a chave só com **"Enable Reading"**. O bot só lê os trades.
- **Seguidora:** **"Enable Spot & Margin Trading"**. **Nunca** habilite saque
  (*Withdrawals*) e, se puder, restrinja a chave ao IP da sua máquina.
- Coloque as chaves no `.env`. Esse arquivo nunca deve ser compartilhado nem versionado.

## Rodando — siga esta ordem

1. **Simulação offline** (sem chaves, só confere a lógica):
   ```bash
   py simulate.py
   ```
2. **Testnet + dry_run** (`testnet = true`, `dry_run = true`): crie as chaves em
   <https://testnet.binance.vision>, opere manualmente nas contas mestre da testnet e
   veja o bot registrar as cópias simuladas.
3. **Testnet com ordens** (`dry_run = false`): as ordens vão de verdade para a testnet.
4. **Conta real**: só depois de semanas na testnet. Comece com `budget_usdt` e
   `max_order_usdt` pequenos.

```bash
py -m copytrader config.toml
```

Para parar, use `Ctrl+C`. O status de cada mestre aparece no log a cada ~5 minutos.

## Arquivos

| Arquivo | O que faz |
|---|---|
| `copytrader/engine.py` | Loop principal: aquecimento, monitoramento e despacho |
| `copytrader/brain.py` | Avaliação dos mestres (o "cérebro") |
| `copytrader/copier.py` | Cálculo do tamanho das ordens e limites de risco |
| `copytrader/exchange.py` | Binance Spot via CCXT (paginação de 24h da API) |
| `copytrader/storage.py` | SQLite: trades vistos, posições e log de ordens |
| `simulate.py` | Teste offline com exchange falsa |

## Limitações conhecidas

- **Só funciona com mestres que te dão chave de leitura.** Os "lead traders" públicos do
  Copy Trading da Binance não expõem as ordens por API oficial.
- **Detecção por consulta periódica (polling)**, com atraso de alguns segundos.
  O próximo passo seria usar WebSocket (*user data stream*).
- **Só ordens a mercado**, só Spot e só pares em USDT.
- **Taxas** não entram no cálculo de PnL.

> Aviso: isto é software experimental, não recomendação de investimento.
> Você pode perder dinheiro. Teste na testnet antes de usar com dinheiro real.
