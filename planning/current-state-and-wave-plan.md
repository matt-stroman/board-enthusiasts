# Current State And Wave Plan

## Table of Contents

- [Purpose](#purpose)
- [Architecture Decisions Reconfirmed](#architecture-decisions-reconfirmed)
- [Current Implemented State](#current-implemented-state)
- [Wave Realignment](#wave-realignment)
- [Schema And Identity Boundary](#schema-and-identity-boundary)
- [Delivery Rules For Future Waves](#delivery-rules-for-future-waves)

## Purpose

This document records the currently aligned architecture and delivery plan after Wave 6 access-role realignment implementation.

It exists to make one distinction explicit:

- the repository already implements a usable API/authentication foundation
- Wave 1 application-owned identity persistence is implemented
- Wave 2 organizations and memberships are implemented
- Wave 3 titles and versioned metadata are implemented
- Wave 4 media, releases, and APK artifact metadata are implemented
- Wave 5 supported publishers and external acquisition bindings are implemented
- Wave 6 self-service developer access and verified-developer role moderation is implemented
- later commerce, entitlement, and Board install-delivery waves remain planned work

Use this document when deciding whether something belongs in the maintained current contract or in a future wave plan.

## Architecture Decisions Reconfirmed

The project remains aligned to these decisions:

- API-first: externally visible behavior starts in the OpenAPI contract and Postman mock/contract assets before backend implementation.
- TDD for backend work: new implementation starts with failing contract tests and backend tests before production code.
- Automation-first: local bootstrap, dependency startup, backend test runs, and repeatable auth infrastructure should stay scriptable with minimal manual steps.
- UI-agnostic backend: the backend exposes application behavior through API so MAUI, web, Board-native, or other clients can consume the same workflows.
- Keycloak-owned identity lifecycle: self-registration, password reset, email verification, brokered identity linking, and platform-role assignment belong to Keycloak, not PostgreSQL.
- Brokered SSO direction: Google, Facebook, Steam, Epic Games, and similar providers should be integrated through Keycloak identity brokering when enabled, not through application-owned credential tables.

## Current Implemented State

As of March 5, 2026, the maintained implemented surface is:

- health endpoints: `/`, `/health/live`, `/health/ready`
- Keycloak-backed identity endpoints: `/identity/roles`, `/identity/auth/config`, `/identity/auth/login`, `/identity/auth/callback`, `/identity/me`, `GET|POST /identity/me/developer-enrollment`, and `GET|PUT|DELETE /identity/me/board-profile`
- moderation endpoints: `PUT|DELETE /moderation/developers/{developerSubject}/verified-developer`
- organization endpoints: public `GET /organizations`, public `GET /organizations/{slug}`, authenticated `POST|PUT|DELETE /organizations...`, and authenticated membership management endpoints
- catalog endpoints: public `GET /catalog`, public `GET /catalog/{organizationSlug}/{titleSlug}`, authenticated title/metadata management endpoints, authenticated media/release/artifact management endpoints, public `GET /supported-publishers`, and authenticated connection/acquisition-binding management endpoints
- EF Core persistence with migrations for `users`, `user_board_profiles`, `organizations`, `organization_memberships`, `titles`, `title_metadata_versions`, `title_media_assets`, `title_releases`, `release_artifacts`, `supported_publishers`, `integration_connections`, and `title_integration_bindings`
- Postman mock-first contract assets for the above endpoints
- backend endpoint unit tests plus Postgres-backed integration coverage for persistence and constraints
- developer automation for local bootstrap, Docker dependencies, and test execution

Not yet implemented:

- authenticated player library read models and personalization
- private player wishlist management
- Wave 7 unified commerce and entitlements
- Wave 8 Board install-delivery flows
- configured Keycloak brokers for social/game platform SSO in the local realm import

Because those later items are not implemented, they should not remain in the maintained current API contract unless they are being actively delivered in the same wave with tests first.

## Wave Realignment

To avoid contract drift, the project should treat the current backend as a completed foundation plus Waves 1 through 6 baseline and start the next schema work from the Wave 7 boundary.

### Foundation (implemented)

- Keycloak integration and browser login callback flow
- bearer-token validation and current-user projection from claims
- platform role catalog exposure
- health/readiness automation and test coverage

### Wave 1 (implemented)

Application identity projection and optional Board profile persistence:

- EF Core + migrations
- `users` keyed by immutable Keycloak subject
- `user_board_profiles` for optional Board linkage/cache
- `/identity/me/board-profile` endpoints in the maintained contract with backend tests and implementation

### Wave 2 (implemented)

Organizations and memberships.

### Wave 3 (implemented)

Titles and versioned metadata.

### Wave 4 (implemented)

Media slots, semver releases, current-release activation, and APK artifact metadata.

### Wave 5 (implemented)

Publisher-agnostic external acquisition bindings.

### Wave 6 (implemented)

Status: implemented on March 5, 2026.

Implemented Wave 6 behavior includes:

- self-service developer enrollment via `POST /identity/me/developer-enrollment`
- enrollment state read model via `GET /identity/me/developer-enrollment`
- moderator role-mutation endpoints for `verified_developer` assignment/removal on developer accounts
- developer-access checks that tolerate stale bearer role claims by rechecking Keycloak
- removal of deprecated enrollment workflow persistence and API/UI surfaces (request queues, workflow conversations/attachments, and in-app notifications)

### Wave 7 (planned)

Player library foundation, unified commerce, and entitlements.

Planned Wave 7 behavior includes:

- authenticated player-library read models for owned titles
- wishlist persistence and private wishlist retrieval
- room for future player collections and favorites in the same player-owned surface
- purchase state and ownership modeling inside the library rather than relying only on external acquisition links

### Wave 8 (planned)

Board-native download and install delivery.

This wave should make artifact delivery and installation a first-party Board experience after commerce and entitlement rules are defined.

## Schema And Identity Boundary

The schema boundary is:

- Keycloak owns credentials, verification, password reset, account linking, external identity brokers, and global platform roles.
- PostgreSQL owns application data and durable references to Keycloak subjects.
- Cached identity fields in PostgreSQL are snapshots only and must not replace Keycloak as the source of truth.
- Brokered SSO provider metadata may be surfaced via API configuration endpoints, but provider setup remains a Keycloak realm concern.
- Platform roles may still exist in Keycloak and bearer claims, but player-facing surfaces should describe access state in UI terms instead of exposing raw role codes directly.

## Delivery Rules For Future Waves

For every new externally visible capability:

1. Update the OpenAPI contract first.
2. Add or update Postman mock examples and executable contract tests.
3. Add failing backend unit and integration tests.
4. Implement production code and migrations.
5. Run automated backend and contract test suites.
6. Update the maintained docs and agent guidance in the same change set.
