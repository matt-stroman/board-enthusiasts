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
python ./scripts/dev.py bootstrap
python ./scripts/dev.py up
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
  - Developer CLI (root automation commands): [`docs/developer-cli.md`](docs/developer-cli.md)
- Backend-specific docs (in backend submodule):
  - Backend phase 1 (PostgreSQL local setup): [`backend/docs/backend-phase-1-postgres-setup.md`](backend/docs/backend-phase-1-postgres-setup.md)
  - New developer setup / quick start (current backend MVP): [`backend/docs/new-developer-setup.md`](backend/docs/new-developer-setup.md)

## Developer Automation

Primary root script entry point:

- [`scripts/dev.py`](scripts/dev.py)

See the dedicated CLI doc for full command coverage and options:

- [`docs/developer-cli.md`](docs/developer-cli.md)

Examples:

```bash
python ./scripts/dev.py doctor
python ./scripts/dev.py bootstrap
python ./scripts/dev.py up
python ./scripts/dev.py test
python ./scripts/dev.py down
```
