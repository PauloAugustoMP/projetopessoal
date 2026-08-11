# Estratégia de testes

## Pirâmide

```
                    ▲
                   /E2E\          poucos — golden paths no app desktop (Playwright)
                  /------\
                 /Integração\     moderados — apps/api contra Postgres real
                /------------\
               / Contrato/adapter\  poucos — mocks do provedor de cotações
              /--------------------\
             /      Unitários        \  muitos — packages/domain, sem I/O
            /--------------------------\
```

Regra geral: se uma regra de negócio pode ser testada sem banco e sem rede, ela **deve** ser testada em `packages/domain`, não reimplicitamente só por um teste de integração. Isso mantém a suíte rápida (roda em segundos, sem Docker) e os testes de integração enxutos (só verificam a fiação, não a lógica em si).

## 1. Testes unitários — `packages/domain`

- **Ferramenta**: Vitest.
- **Cobertura esperada**: alta (meta ≥ 90% de linhas) — é lógica pura, sem desculpa pra não testar.
- **O que cobrir**: todo case listado em [business-rules.md](business-rules.md), especialmente os casos de borda já sinalizados no documento (posição zerando, venda maior que posição, todos os ativos acima da meta, LPA/VPA negativos, app fechado por semanas, etc).
- **Já implementado** (Sprint 0): `average-price-calculator`, `corporate-action-applier`, `rebalance-calculator`, `indicator-calculator`, `snapshot-catchup` — ver `packages/domain/src/services/*.test.ts`.
- **Convenção**: um arquivo `*.test.ts` ao lado de cada arquivo de serviço. Nome do teste descreve o comportamento em português, não a implementação (`"não altera o preço médio numa venda"`, não `"testa função applySell"`).
- **Nunca mockar dentro do domínio** — se um teste de domínio "precisa" de um mock, é sinal de que a peça pertence à infraestrutura, não ao domínio.

## 2. Testes de integração — `apps/api`

- **Ferramenta**: Vitest + `fastify.inject()` (dispensa subir servidor HTTP de verdade) contra um Postgres real rodando em container (mesmo `docker-compose.yml`, banco de teste separado — `investor_test`).
- **O que cobrir**:
  - CRUD de transações e o motor de recálculo disparando de ponta a ponta contra o banco (não só a função pura do domínio — aqui importa que a fila/job realmente rode e persista).
  - Importação de extrato B3: upload → parse → dedup → gravação, com arquivos de exemplo em `apps/api/test/fixtures/`.
  - Catch-up de snapshot na inicialização: simular `ultimoSnapshotData` no passado, subir o módulo, conferir que os snapshots faltantes foram criados.
  - Autenticação e autorização (rotas protegidas rejeitando requisição sem token).
  - Validações de payload (Zod) retornando 400 nos formatos esperados pelo `openapi.yaml`.
- **Isolamento**: cada arquivo de teste roda dentro de uma transação de banco revertida ao final (ou `TRUNCATE` entre testes) — testes não podem depender de ordem de execução nem deixar sujeira para o próximo.
- **Sem rede externa**: o provedor de cotações é substituído pelo mock da seção 3 — testes de integração não devem depender do brapi.dev estar no ar.

## 3. Testes de contrato / adapter

- **O que é**: testes do adapter `brapi-provider.ts` (e `bcb-provider.ts`) contra respostas **gravadas** (fixtures JSON reais, capturadas uma vez e versionadas), não contra a API ao vivo.
- **Por quê**: prova que o adapter sabe interpretar o formato de resposta real da API, sem tornar a suíte dependente de rede ou sujeita a rate limit.
- **O que cobrir**: mapeamento de campos (inclusive `logourl` ausente → fallback tratado em outra camada), erro de rate limit / timeout do provedor sendo propagado como erro de domínio conhecido (não como exceção genérica), série histórica com dias faltantes (feriado/fim de semana).
- **Atualização das fixtures**: quando a API do provedor mudar o formato, recapturar manualmente e versionar — não automatizar a captura dentro do CI.

## 4. Testes E2E — app desktop

- **Ferramenta**: Playwright, apontando pro build web do Tauri (`tauri dev` expõe a webview via WebDriver; alternativamente, roda o mesmo frontend Vite direto num browser para testes mais rápidos, já que a lógica de UI não depende do shell nativo — só funcionalidades específicas do SO, como diálogo de arquivo, exigem o binário Tauri de fato).
- **Golden paths cobertos** (um teste por fluxo, não por tela):
  1. Login → dashboard carrega com dados reais.
  2. Lançar transação (compra) → posição e patrimônio atualizam na tela.
  3. Lançar transação retroativa → conferir que o dashboard reflete o recálculo (aceitando o estado "recalculando..." antes do resultado final).
  4. Importar extrato B3 → resumo da importação exibido, posições atualizadas.
  5. Definir meta de alocação → simular aporte → ver sugestão de compra coerente com a meta.
  6. Reinvestir saldo de proventos → saldo zera, compras sugeridas aparecem.
  7. Abrir tooltip de um indicador → texto explicativo visível.
- **Fora do escopo do E2E**: variações de regra de negócio (isso já está exaustivamente coberto nos testes unitários do domínio) — o E2E só prova que a tela certa mostra o dado certo.

## 5. Dados de teste

- Factories simples em `packages/domain/test/factories.ts` (reaproveitadas pelos testes de integração) para gerar `Transaction`, `Asset`, `Dividend` etc. com valores padrão sensatos e overrides pontuais — evita testes poluídos com objetos gigantes montados na mão.
- Fixtures de extrato B3 (`apps/api/test/fixtures/*.csv`) anonimizadas — nunca usar um extrato real seu num arquivo versionado.

## 6. O que cada sprint entrega em testes

Ver [sprints.md](sprints.md) — cada sprint tem sua própria "Definição de pronto" com os testes correspondentes; não existe uma fase separada de "testar tudo no final". A suíte cresce junto com a feature.

## 7. Rodando a suíte

```bash
# unitários (rápido, sem Docker)
npm run test -w packages/domain

# integração (precisa do docker-compose up com o banco de teste)
npm run test -w apps/api

# tudo
npm test

# E2E (precisa da API rodando e do app desktop buildado/dev)
npm run test:e2e -w apps/desktop
```

## 8. O que conscientemente não testamos

- Comportamento exato de bibliotecas de terceiros (Fastify, Prisma, Tauri) — confiamos no contrato delas.
- Precisão de cotação do provedor externo — validamos que *usamos* o dado retornado corretamente, não que o dado em si está certo (isso é responsabilidade do provedor).
- Carga/performance — fora de escopo para uso single-user.
