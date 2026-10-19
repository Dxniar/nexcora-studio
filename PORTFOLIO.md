# Nexcora Studio — portfolio case study

## Problem

A small freelance service needs a consistent way to collect briefs, agree on scope and track work without losing decisions across chat messages. The client needs to understand what happens next, while the owner needs a queue that separates new requests, pending agreements and active delivery.

## Implemented product

Nexcora Studio combines a Telegram bot with a responsive Mini App. A client can create a draft, attach a limited set of private documents or images, review the brief and submit it. The owner then prepares a proposal with scope, deliverables, price, currency, deadline and revision terms. Both parties work against the current proposal version.

After agreement, the owner starts work, adds updates and submits a result. The client accepts it or requests a revision with a comment. Project history records the workflow. Personal and owner views have distinct navigation, with permissions enforced by the API.

Russian, English and Kazakh language selection is shared between the bot and Mini App. User-written briefs and documents retain their original content. Localization is included in the source; its release verification is in progress.

## Technical decisions and their purpose

| Decision                                                | Purpose                                                                                    |
| ------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| Telegram HMAC validation and expiring server sessions   | Authenticate the Telegram account without trusting browser role claims                     |
| PostgreSQL transactions, version checks and idempotency | Keep proposal agreement and project changes consistent under retries or stale edits        |
| Separate notification outbox                            | Preserve a committed project action when Telegram delivery fails                           |
| Leases and bounded retries                              | Recover background jobs after process interruption without running an unbounded retry loop |
| Private S3 objects with authenticated downloads         | Restrict request attachments to the appropriate client and owner                           |
| Durable file-cleanup queue                              | Revoke access immediately while retrying physical deletion separately                      |
| One Docker image with separate process commands         | Package the frontend and API together while isolating polling and workers                  |

The implementation uses Python 3.14, FastAPI, aiogram, SQLAlchemy, Alembic, PostgreSQL, React, TypeScript, Vite and S3-compatible storage. Python and frontend dependencies are locked. The hosted demo runs on Railway.

## Verification evidence

The repository includes tests for signed Telegram authentication, client/owner access boundaries, workflow transitions, version conflicts, duplicate requests, file validation, notification retries and privacy operations. Dedicated PostgreSQL tests exercise transactional behavior, locks, migrations and synthetic dump/restore. Playwright runs browser workflows against a real local API, temporary database and local file-storage fixture.

UI checks cover mobile and desktop layouts, both themes, Telegram safe areas, keyboard use and enlarged text. Test identities, projects and attachment contents are synthetic. They are not customer records.

A full local backend regression, including disposable PostgreSQL 18 checks, passed on October 19, 2026. Run the commands in [Development](docs/development.md#verification) to obtain current results. Local results do not establish that a future GitHub Actions run will pass. Live owner sign-in through Telegram has been user-confirmed; the complete live client journey still requires a separate check.

## Scope and limitations

The current scope is a single-owner service workspace. It does not collect online payments, provide an AI chat, assign multiple developers or match clients with freelancers. A client accepting terms is a workflow action, not a payment receipt.

Operational work remains before a customer launch: routine backups, recovery with actual uploaded objects, provider resource limits, real-IP configuration and a live end-to-end client walkthrough. No commercial customers, revenue, load capacity or client deployment outcomes are claimed.

## Development context

This is a personal learning and portfolio project developed with AI/Codex assistance. The source and repeatable checks demonstrate the implemented behavior and chosen technical approach. They do not, by themselves, verify independent proficiency in every framework used or constitute commercial work experience.

[Open the Telegram demo](https://t.me/nexcora_bot) · [Project overview](README.md) · [Deployment guide](docs/deployment.md)
