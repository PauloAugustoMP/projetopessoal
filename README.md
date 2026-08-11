# Controle de investimentos

App pessoal de controle de investimentos (single-user), inspirado no Investidor10. Documentação completa em [`docs/`](docs/architecture.md).

## Estrutura

```
apps/
  api/       # backend Fastify + Prisma (regras de negócio expostas via REST + WebSocket)
  worker/    # jobs agendados (snapshot diário, polling de cotação)
  desktop/   # app desktop Tauri + React
packages/
  domain/    # entidades e regras de negócio puras (testadas em isolamento)
docs/
  architecture.md
  business-rules.md
  openapi/openapi.yaml
```

## Pré-requisitos

- [Node.js](https://nodejs.org) 20+
- [Docker](https://docker.com) (Postgres + Redis) — necessário para `apps/api`
- [Rust + Cargo](https://www.rust-lang.org/tools/install) — necessário para compilar `apps/desktop` (Tauri)
- No Linux, dependências de sistema do Tauri: veja [tauri.app/start/prerequisites](https://tauri.app/start/prerequisites/)

## Setup

```bash
npm install
cp .env.example .env
docker compose up -d
```

## Testes

O core de regras de negócio (`packages/domain`) tem cobertura de testes unitários e não depende de banco/rede:

```bash
npm run test -w packages/domain
```

## Rodando localmente

```bash
# backend
npm run dev -w apps/api

# desktop (precisa de Rust instalado)
npm run tauri dev -w apps/desktop
```
