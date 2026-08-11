# Plano de sprints

Sequência sugerida respeitando dependências técnicas (ex: não dá pra ter simulador de aporte sem posição calculada; não dá pra ter cotação sem provedor de dados integrado). Sprints de ~1-2 semanas, ritmo solo. "Pronto" em cada sprint sempre inclui os testes correspondentes — não é uma etapa à parte (ver [testing-strategy.md](testing-strategy.md) para a estratégia completa).

## Sprint 0 — Fundação ✅ (feito)

- Documentação: [architecture.md](architecture.md), [business-rules.md](business-rules.md), [openapi/openapi.yaml](openapi/openapi.yaml)
- Monorepo (`npm workspaces`), `docker-compose.yml` (Postgres + Redis)
- `packages/domain`: entidades + regras de negócio puras já implementadas e testadas — preço médio, motor de recálculo (cálculo), eventos corporativos, rebalanceamento/aporte, indicadores (Bazin/Graham/marcadores), catch-up de snapshot na inicialização

**Pendente antes do Sprint 1**: instalar dependências e rodar `npm run test -w packages/domain` pra confirmar que os testes escritos realmente passam.

## Sprint 1 — Backend core: transações e posição

- `apps/api`: Fastify + Prisma, `schema.prisma` com os modelos do domínio
- Migração inicial do banco
- Autenticação single-user (senha + JWT, ver business-rules e architecture §5)
- Endpoints: `POST/GET/PATCH/DELETE /transactions`, `GET /positions`, `GET /assets` (autocomplete)
- Motor de recálculo (`recalculation-engine`) ligado ao Postgres de verdade — dispara ao criar/editar/remover transação, roda em fila (BullMQ)
- Validações de sanidade (venda maior que posição, ticker desconhecido)

**Definição de pronto**: testes de integração dos endpoints com Postgres real; teste de idempotência do motor de recálculo rodando contra o banco; lançar uma transação retroativa manualmente e conferir que a posição recalcula certo.

## Sprint 2 — Importação do extrato B3

- Parser de CSV/Excel do extrato B3 → transações, proventos (bruto/líquido), eventos corporativos
- Deduplicação contra transações já existentes
- Fila de "linhas para revisão manual" quando a correspondência for ambígua
- Endpoint `POST /import/b3-statement`

**Definição de pronto**: testes unitários do parser com arquivos de exemplo reais (anonimizados) cobrindo compra, venda, provento, desdobramento, bonificação, grupamento; teste de deduplicação (mesma linha importada duas vezes não duplica).

## Sprint 3 — Cotações, snapshots e catch-up

- Adapter do provedor de cotações (brapi.dev) implementando a porta `market-data-provider`
- `price-poll` job (tempo quase real) + canal WebSocket
- `daily-snapshot` job (patrimônio total, por categoria, decomposição aporte/valorização/provento)
- Estado persistido `ultimoSnapshotData` / `ultimaExecucaoEm`
- Catch-up na inicialização: ao subir a API, compara `ultimoSnapshotData` com hoje e recalcula os dias que ficaram faltando (`computeMissingSnapshotDates`, já implementado no domínio)
- Redis como cache de cotação (evita estourar rate limit do free tier)

**Definição de pronto**: teste de integração simulando "app ficou desligado 5 dias" e verificando que os 5 snapshots são preenchidos ao subir; mock do provedor de cotações para não depender de rede nos testes; teste do WebSocket entregando atualização de preço a um cliente conectado.

## Sprint 4 — App desktop (Tauri) — base

- Scaffold do projeto Tauri + React + Vite (`apps/desktop`)
- Tela de login
- Dashboard: patrimônio total, cards de resumo, gráfico de evolução, alocação por categoria, tabela de posições (com logo/avatar por categoria)
- Client TS gerado a partir do `openapi.yaml`, consumido pela UI

**Definição de pronto**: app abre e mostra dados reais vindos da API local; smoke test manual em cada SO alvo (pelo menos macOS, já que é o ambiente do usuário); teste E2E do fluxo de login.

## Sprint 5 — Metas de alocação, aporte e reinvestimento

- Tela de definição de meta (categoria % + peso por ativo, com divisão igual como padrão)
- Simulador de aporte (`POST /allocation-targets/simulate`) com a tela de sugestão de compra
- Fluxo "reinvestir dividendos" usando o saldo acumulado de proventos como aporte

**Definição de pronto**: teste E2E do fluxo completo "definir meta → simular aporte → conferir sugestão"; testes de integração validando que a soma dos percentuais de categoria é validada em `PUT /allocation-targets`.

## Sprint 6 — Indicadores e proventos

- `GET /assets/{ticker}/indicators`: P/L, P/VP, DY, ROE com marcador colorido + tooltip
- Preço teto (Bazin) e preço justo (Graham) na tela de detalhe do ativo
- Calendário de proventos (data-com / pagamento) + lista de próximos proventos
- Cadastro manual de provento anunciado

**Definição de pronto**: teste E2E abrindo o tooltip de um indicador e conferindo o texto; teste de integração do calendário retornando eventos no intervalo de datas correto.

## Sprint 7 — Segurança, backup e exportação

- Backup automático diário do Postgres (`pg_dump` agendado)
- Exportação livre de dados (CSV/JSON) sob demanda
- Log de auditoria das alterações retroativas + "desfazer última alteração"
- Revisão de rate limiting, validação de payload em todas as rotas, capabilities do Tauri restritas ao necessário

**Definição de pronto**: teste automatizado restaurando um backup e conferindo integridade; teste do fluxo de desfazer.

## Sprint 8 — Empacotamento e hardening final

- Build do instalador Tauri (macOS — ambiente do usuário; Windows/Linux se necessário depois)
- Configuração do backend pra iniciar junto com o sistema (serviço/daemon)
- Passada de testes E2E cobrindo os golden paths completos end-to-end
- Revisão do painel de "última execução dos jobs" (Ajustes) e alertas de falha

**Definição de pronto**: instalar o `.app` do zero numa máquina limpa e completar o fluxo "abrir app → lançar transação → importar extrato → ver dashboard → simular aporte" sem tocar em código.
