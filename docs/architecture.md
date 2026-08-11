# Arquitetura — App de controle de investimentos

Uso pessoal (single-user), local-first, com acesso remoto via VPN pessoal (Tailscale). Referência de produto: Investidor10. Stack em TypeScript ponta a ponta (frontend desktop com um shell nativo em Rust, via Tauri).

## 1. Contexto

```
                         ┌────────────────────┐
                         │        Você          │
                         └──────────┬───────────┘
                                    │
                          ┌─────────▼──────────┐
                          │    Desktop App        │
                          │  (Tauri + React)      │
                          └─────────┬────────────┘
                                    │  HTTPS/WSS (localhost ou Tailscale
                                    │  se quiser acessar remoto)
                          ┌─────────▼──────────┐
                          │     API Backend      │
                          │  (Fastify + TS)      │
                          └─────────┬────────────┘
                                    │
        ┌───────────────┬──────────┼──────────────┬────────────────┐
        │                │                          │                  │
┌───────▼──────┐ ┌───────▼───────┐        ┌─────────▼────────┐ ┌───────▼────────┐
│  PostgreSQL   │ │     Redis      │        │  brapi.dev API    │ │   BCB API       │
│ (dados próprios)│ │ (cache/fila)  │        │ (cotações, logos, │ │ (CDI/Selic,     │
│                │ │                │        │  histórico)        │ │  gratuita/oficial)│
└───────────────┘ └────────────────┘        └───────────────────┘ └─────────────────┘

        Fonte adicional (fora do sistema): extrato de movimentação B3,
        exportado manualmente pelo usuário e importado via upload de CSV.
```

Não há integração automática com login da B3 (ver seção 7 — decisão de segurança). O extrato é baixado por você no site da B3 e importado como arquivo.

## 2. Containers

| Container | Responsabilidade | Tecnologia |
|---|---|---|
| Desktop App | Dashboard, carteira, proventos, metas, simulador de aporte — app nativo instalável (macOS/Windows/Linux), só a camada de UI | Tauri 2 (shell Rust) + React + Vite + Tailwind + Recharts |
| API Backend | Regras de negócio, autenticação, orquestração | Node.js + Fastify + Prisma |
| Worker | Jobs agendados e assíncronos (ver 4.4) | BullMQ sobre Redis, processo separado do backend |
| PostgreSQL | Fonte da verdade dos dados do usuário | Postgres 16, rodando em Docker local |
| Redis | Fila de jobs + cache de cotações (evita estourar rate limit das APIs gratuitas) | Redis 7 |

Todos os containers sobem via **Docker Compose** numa única máquina (seu computador, NAS ou Raspberry Pi). Sem dependência de nuvem pública.

## 3. Arquitetura interna do backend (hexagonal)

```
src/
  domain/               # regras de negócio puras, sem I/O — testadas em isolamento
    entities/           # Asset, Transaction, Position, Dividend, CorporateAction,
                         # AllocationTarget, PortfolioSnapshot, Indicator
    services/
      average-price-calculator.ts
      recalculation-engine.ts
      rebalance-calculator.ts
      indicator-calculator.ts       # marcadores, preço teto (Bazin), preço justo (Graham)
      corporate-action-applier.ts

  application/           # casos de uso — orquestram domínio + portas
    use-cases/
      record-transaction.ts
      import-b3-statement.ts
      simulate-contribution.ts
      reinvest-dividends.ts
      get-portfolio-growth.ts

  ports/                 # interfaces que a infraestrutura implementa
    market-data-provider.port.ts
    transaction-repository.port.ts
    price-history-repository.port.ts
    job-scheduler.port.ts

  infrastructure/
    persistence/         # implementações Prisma dos repositórios
    market-data/
      brapi-provider.ts          # implementa market-data-provider.port
      bcb-provider.ts            # CDI/Selic
    b3-import/
      statement-csv-parser.ts    # extrai transações + eventos corporativos + proventos
    jobs/
      daily-snapshot.job.ts
      price-poll.job.ts          # polling de cotação em pregão, broadcast via WS
    http/
      rest/                      # controllers, gerados a partir do OpenAPI
      websocket/                 # canal de cotação em tempo (quase) real
```

Regra de dependência: `domain` não conhece `infrastructure`. Isso é o que permite trocar o provedor de cotações (ex: sair do free tier pra um pago no futuro) sem tocar em nenhuma regra de negócio, e testar `domain`/`application` inteiramente com mocks das portas — sem banco, sem rede.

## 4. Fluxos principais

### 4.1 Cotação "tempo real"
1. `price-poll.job` roda a cada 15–30s em horário de pregão (B3: 10h–17h, horário de Brasília), busca cotação dos ativos que você possui via `market-data-provider`.
2. Preço é cacheado no Redis (evita re-consultar a API externa se múltiplos clientes estiverem conectados).
3. Backend propaga a atualização via WebSocket pro app desktop conectado.
4. Fora do pregão, o job roda em intervalo bem mais espaçado (ou não roda), já que preço não muda.

### 4.2 Lançamento retroativo + recálculo
1. `record-transaction` grava a transação no ledger imutável.
2. Dispara `recalculation-engine` como job assíncrono (não bloqueia a resposta da API).
3. O motor recalcula, em ordem cronológica: posição/preço médio do ativo → snapshots diários de patrimônio no intervalo afetado (busca preço histórico via `market-data-provider` se ainda não estiver em cache) → elegibilidade a proventos no intervalo.
4. Enquanto processa, a API expõe um status (`recalculating: true`) pra UI mostrar feedback.
5. Execução é idempotente: rodar o mesmo recálculo duas vezes produz o mesmo estado final — propriedade validada por teste automatizado.

### 4.3 Importação de extrato B3
1. Upload do CSV/Excel exportado da área do investidor B3.
2. Parser classifica cada linha: compra/venda, provento (com bruto/líquido), ou evento corporativo (desdobramento/grupamento/bonificação/subscrição).
3. Deduplicação: compara ticker + data + quantidade + preço contra o que já existe antes de gravar, pra não duplicar o que você já lançou manualmente.
4. Eventos gravados disparam o mesmo motor de recálculo do item 4.2.

### 4.4 Catch-up ao iniciar

Como o backend não roda 24/7 (o computador é desligado, o app é fechado), o `daily-snapshot` pode perder dias. Uma tabela `SystemState` (chave/valor) guarda `ultimoSnapshotData` e `ultimaExecucaoEm`. Ao subir a API:
1. Compara `ultimoSnapshotData` com a data de hoje.
2. `computeMissingSnapshotDates` (packages/domain) calcula os dias faltantes.
3. O mesmo motor de recálculo da seção 4.2 processa cada dia faltante, em ordem, atualizando `ultimoSnapshotData` incrementalmente — se cair no meio, a próxima subida retoma do ponto certo.

Detalhe completo em [business-rules.md §8.1](business-rules.md#81-catch-up-ao-iniciar-o-app).

### 4.5 Jobs agendados (worker)
- `daily-snapshot`: roda após fechamento do pregão, grava `PortfolioSnapshot` do dia (total, por categoria, decomposição aporte/valorização/provento reinvestido).
- `price-poll`: descrito em 4.1.
- Alertas de falha: como não há equipe de oncall, falha de job grava log estruturado e also gera notificação simples (ex: e-mail ou push) pra você saber que um recálculo não completou — importante pra confiança nos números.

## 5. Segurança

- Autenticação single-user: usuário + senha (argon2), sessão via JWT de vida curta + refresh token.
- Sem integração de login com a B3 (decisão deliberada — ver conversa: não guardar credenciais de terceiros).
- Segredos (API keys) em variáveis de ambiente, nunca no repositório.
- HTTPS mesmo local, via certificado do próprio Tailscale (que já provê TLS ponta a ponta) ou mkcert para uso puramente LAN.
- Rate limiting nas rotas da API; validação de payload em toda rota (zod, compartilhado com os schemas do OpenAPI).
- Backup automático diário do Postgres (`pg_dump`) + exportação livre de dados sob demanda (CSV/JSON) pelo usuário.
- **Tauri**: o app desktop declara explicitamente, em `tauri.conf.json`, quais capabilities tem acesso (rede só pro host da API configurado, sistema de arquivos só pra diálogo de importar CSV/exportar backup). Diferente de Electron, não há Node.js exposto ao frontend — a superfície de ataque do processo desktop fica bem menor.

## 6. Observabilidade

- Logs estruturados (pino) no backend e worker.
- Correlação por `requestId` entre API e jobs assíncronos disparados por ela.
- Painel simples de "última execução dos jobs" (daily-snapshot, price-poll) na própria UI, em Ajustes — visibilidade mínima sem precisar de Grafana/Datadog para um projeto pessoal.

## 7. Deploy

- `docker-compose.yml` na raiz do repo sobe: `api`, `worker`, `postgres`, `redis`. Configurado para iniciar junto com o sistema (serviço/daemon do SO), já que o app desktop depende dele estar no ar.
- O app desktop aponta pra URL local (`localhost`) por padrão, ou pro hostname do Tailscale se você quiser abrir o app noutra máquina apontando pro mesmo backend — configurável nas Ajustes do app.
- Sem exposição de porta pública na internet.

## 8. Estrutura do monorepo

```
/
  apps/
    api/            # backend Fastify
    worker/         # jobs assíncronos
    desktop/        # app Tauri
      src/          # frontend React + Vite
      src-tauri/    # shell nativo Rust (config de capabilities, build por SO)
  packages/
    domain/         # entidades e regras de negócio compartilhadas (usado por api e worker)
    api-client/     # client TS gerado a partir do openapi.yaml, usado pelo desktop
    config/         # eslint/tsconfig compartilhados
  docs/
    architecture.md
    business-rules.md
    openapi/
      openapi.yaml
  docker-compose.yml
```

Gerenciado com pnpm workspaces + Turborepo (build incremental, cache local).
