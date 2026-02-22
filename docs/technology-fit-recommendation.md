# Technology Fit Recommendation (Initial Planning)

## 1) Goals and constraints recap

This recommendation optimizes for:

- **$0 / near-$0 startup cost**
- **Strong long-term scaling path** without full rewrites
- **Stability + flexibility** for diverse publishing/payment providers
- **Cross-platform frontend** where we can "write once" and target **web + native Android/Board**
- **Automated testing + DevOps** from the start

## 2) Updated recommendation summary

Given the new constraint that Board is likely native Android and webview support is uncertain, the safest path to avoid duplicate UI implementation is:

- **Backend:** ASP.NET Core 8 + PostgreSQL (unchanged)
- **Frontend:** **Flutter** (single codebase compiled to web + native Android)

This replaces the earlier React-first recommendation.

## 3) Recommended stack (pragmatic default)

### Backend

- **Runtime/framework:** **ASP.NET Core 8 (Web API)**
  - Why: aligns with your current experience; excellent test tooling; high performance; first-class OpenAPI support.
- **Database:** **PostgreSQL**
  - Why: strong relational consistency for purchases/entitlements with JSONB for provider-specific configs.
- **ORM/data access:** **EF Core + targeted Dapper usage** for hot paths.
- **Cache/queue (later):** Redis (optional at first).
- **API style:** REST first, OpenAPI-generated SDKs where needed.
- **Auth:** OpenID Connect/JWT-compatible model (start simple; keep identity provider swappable).

### Frontend

- **Primary UI stack:** **Flutter + Dart**
  - Why: one UI codebase with first-class native Android output and web output.
  - Why: reduces risk of building web first and rewriting native later.
- **UI strategy:** one shared design system and feature modules across player and developer portal surfaces.
- **State management:** Riverpod or Bloc (pick one and standardize).

### DevOps & delivery

- **Containerization:** Docker + Docker Compose for backend/local dependencies.
- **CI/CD:** GitHub Actions.
- **IaC (later):** Terraform or Pulumi once infra grows.
- **Hosting (free-friendly):**
  - API: Fly.io / Render / Railway-style free tiers (verify current limits).
  - DB: managed Postgres free tier initially.
  - Web frontend artifact: Cloudflare Pages / Netlify / Vercel free tier.
  - Android builds: GitHub Actions artifacts + manual/internal distribution at MVP stage.

## 4) Why this is likely better than immediate microservices

Start as a **modular monolith** first, then split by domain when forced by scale/team boundaries.

Benefits now:

- Lower operational complexity
- Faster feature delivery
- Easier local debugging/testing
- Cheaper hosting

Still design for extraction later by enforcing:

- Strict domain boundaries (catalog, developer onboarding, payment orchestration, entitlement, install delivery)
- Async event contracts between modules
- Provider adapter interfaces

## 5) Domain architecture (initial)

Single deployable backend with internal modules:

1. **Catalog**: app/game metadata, search tags, visibility rules.
2. **Developer Integrations**: external host configs (itch, Humble, custom URLs).
3. **Payment Orchestration**: provider-neutral checkout abstraction; provider adapters.
4. **Entitlements**: purchase ownership and install permission.
5. **Delivery/Install**: console-compatible install metadata and download handoff.
6. **Identity & Access**: users, developers, admins, roles.

Each module owns its schema segment and public interfaces.

## 6) Data model direction

Use Postgres with hybrid relational + JSONB design:

- Relational tables for core entities: users, developers, products, purchases, entitlements.
- JSONB columns for provider-specific configuration payloads.
- Outbox table for integration events (for reliable async later).

This provides flexibility without sacrificing integrity.

## 7) Testing strategy (must-have from day 1)

- **Backend unit tests:** xUnit + FluentAssertions.
- **Backend integration tests:** Testcontainers (ephemeral Postgres).
- **Contract tests:** provider adapters (payments/content hosts).
- **Flutter tests:**
  - unit tests for services/state
  - widget tests for UI behavior
  - integration tests for critical flows
- **End-to-end tests:** API integration + selected UI smoke tests in CI.

CI policy:

- block merges if tests/lint/typecheck fail
- collect coverage and enforce a floor
- run migrations in CI validation job

## 8) Practical guidance for the three low-experience areas

### A) Web service hosting

1. Start with one backend service + one web frontend deployment + Android app artifact pipeline.
2. Use managed Postgres (free tier) with backup export.
3. Keep secrets in host-managed secret stores (never in repo).
4. Add health endpoints (`/health/live`, `/health/ready`) and log correlation IDs.
5. Add basic dashboards for request rate, error rate, and latency.

### B) Microservices

Use a staged approach:

- **Stage 1:** modular monolith.
- **Stage 2:** extract first service only when clear pain appears (e.g., payment processor complexity).
- **Stage 3:** add broker/event bus only once async scale warrants it.

Avoid premature microservices; preserve clean boundaries so extraction is mechanical later.

### C) Docker & environment setup

Minimum local stack:

- `api` (ASP.NET Core)
- `db` (Postgres)
- optional `redis`
- `frontend-web` (Flutter web dev)

Use `docker-compose.yml` for API/database integration; run Flutter tooling locally in parallel.

## 9) 30-day implementation plan (updated)

1. Create ADRs for backend and frontend decisions.
2. Scaffold backend modular monolith (ASP.NET Core + Postgres + migrations).
3. Scaffold Flutter app with shared theme/layout for player and developer views.
4. Define provider abstraction interfaces (payments + content hosts).
5. Ship first vertical slice:
   - developer registers content host config
   - player browses catalog
6. Add CI: backend tests + Flutter tests + lint + build checks.
7. Produce web deployment + Android debug/release pipeline artifacts.

## 10) Alternative if team strongly prefers C# end-to-end UI

- Consider **.NET MAUI** for native client + Blazor Hybrid scenarios.
- Trade-off: web story and ecosystem maturity are generally less straightforward than Flutter for this use case.

## 11) Decision summary

Given uncertainty around Board webview support and desire to avoid duplicate UI work:

- **Backend:** ASP.NET Core + Postgres (modular monolith)
- **Frontend:** Flutter single codebase for web + native Android/Board targets
- **Ops:** Docker for local backend stack, GitHub Actions CI/CD, free-tier managed hosting until traction
