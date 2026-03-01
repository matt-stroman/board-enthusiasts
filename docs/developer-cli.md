# Developer CLI (`scripts/dev.py`)

Supplemental documentation for the root developer automation CLI.

Primary documentation for commands, arguments, and usage should live in the CLI help output:

```bash
python ./scripts/dev.py --help
python ./scripts/dev.py <command> --help
```

This document provides quick guidance, common workflows, and project-specific notes.

## Table of Contents

- [Purpose](#purpose)
- [Primary Entry Point](#primary-entry-point)
- [Common Workflows](#common-workflows)
- [Database Backup and Restore](#database-backup-and-restore)
- [Configuration Overrides](#configuration-overrides)
- [Notes](#notes)

## Purpose

The developer CLI orchestrates common local development tasks from the repository root:

- bootstrap submodules and restore backend dependencies
- start/stop/reuse local PostgreSQL and Keycloak via Docker Compose
- run the backend API
- run backend tests
- run environment diagnostics
- create/restore local PostgreSQL SQL backups

## Primary Entry Point

Command:

```bash
python ./scripts/dev.py <command> [options]
```

## Common Workflows

### First-time setup + run

```bash
python ./scripts/dev.py bootstrap
python ./scripts/dev.py up
```

### Start only local dependencies (no API)

```bash
python ./scripts/dev.py up --dependencies-only
```

### Stop dependencies

```bash
python ./scripts/dev.py down
```

### Check local tool and environment status

```bash
python ./scripts/dev.py doctor
python ./scripts/dev.py status
```

### Run backend tests

```bash
python ./scripts/dev.py test
python ./scripts/dev.py test --skip-integration
```

## Database Backup and Restore

The CLI includes PostgreSQL helpers that operate against the local Dockerized database container.

### Create a backup (timestamped default path)

```bash
python ./scripts/dev.py db-backup
```

Default output location:

- `./backups/<database>-<utc-timestamp>.sql`

### Create a backup at a specific path

```bash
python ./scripts/dev.py db-backup ./backups/dev-before-migration.sql
```

### Restore a backup

```bash
python ./scripts/dev.py db-restore ./backups/dev-before-migration.sql
```

Notes:

- The PostgreSQL container must already be running (`up` or `up --dependencies-only`).
- `db-backup` creates a plain SQL dump (`pg_dump`) with cleanup statements (`--clean --if-exists`).
- `db-restore` replays the SQL using `psql` against the configured database.

## Configuration Overrides

Most commands accept shared overrides (see `--help` for full details), including:

- `--compose-file`
- `--postgres-container-name`
- `--postgres-user`
- `--postgres-database`
- `--keycloak-container-name`
- `--keycloak-ready-url`
- `--backend-project`
- `--backend-solution`

Example (non-default DB name):

```bash
python ./scripts/dev.py status --postgres-database my_local_db
```

## Notes

- The `up`, `down`, and `status` commands manage the local PostgreSQL and Keycloak containers together.
- The `down` command uses `docker compose down` and does **not** remove named volumes. Your local Postgres data persists unless you explicitly remove volumes.
- VS Code tasks in this repo call the Python CLI directly.
