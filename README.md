# board-third-party-lib

A solution for third party developers for the Board ecosystem to use to register and share their games with the public.

## Table of Contents

- [Getting started in this repository](#getting-started-in-this-repository)
- [Docs](#docs)
- [Developer Automation](#developer-automation)

## Getting started in this repository

This repository currently tracks backend and frontend as git submodules.

Quick start (backend API + local Postgres via automation):

```bash
pwsh ./scripts/dev.ps1 bootstrap
pwsh ./scripts/dev.ps1 up
```

Initialize them after clone:

```bash
git submodule update --init --recursive
```

Check that submodules are initialized (no leading `-` in status output):

```bash
git submodule status
```

## Docs

- Project-wide docs:
  - Technology recommendation: [`docs/technology-fit-recommendation.md`](docs/technology-fit-recommendation.md)
- Backend-specific docs (in backend submodule):
  - Backend phase 1 (PostgreSQL local setup): [`backend/docs/backend-phase-1-postgres-setup.md`](backend/docs/backend-phase-1-postgres-setup.md)
  - New developer setup / quick start (current backend MVP): [`backend/docs/new-developer-setup.md`](backend/docs/new-developer-setup.md)

## Developer Automation

Root script entry point:

- [`scripts/dev.ps1`](scripts/dev.ps1)

Examples:

```bash
pwsh ./scripts/dev.ps1 doctor
pwsh ./scripts/dev.ps1 bootstrap
pwsh ./scripts/dev.ps1 up
pwsh ./scripts/dev.ps1 test
pwsh ./scripts/dev.ps1 down
```
