# Development

## Requirements

- Python **3.14**, as used by the application image and CI.
- Node.js **24** for the documented setup. The frontend package declares a minimum of 22.12.
- A development PostgreSQL database. The optional Compose service uses PostgreSQL 17.
- Your own Telegram bot token and numeric owner ID for an interactive application.
- A private S3-compatible bucket for the full attachment workflow.

The commands below use Windows PowerShell from the repository root. They preserve an existing `.env` and do not modify the production environment.

## Install

```powershell
if (-not (Test-Path -LiteralPath .venv)) { py -3.14 -m venv .venv }
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
npm.cmd --prefix web ci
npm.cmd --prefix web run build
if (-not (Test-Path -LiteralPath .env)) { Copy-Item -LiteralPath .env.example -Destination .env }
notepad .env
```

Fill in the environment file locally. Never commit tokens, storage keys, database passwords, Telegram `initData`, session tokens or customer data. `VITE_*` values are embedded in the browser bundle and must not contain secrets.

| Variable                                   | Local meaning                                                     |
| ------------------------------------------ | ----------------------------------------------------------------- |
| `BOT_TOKEN`                                | Token for your own bot; server only                               |
| `ADMIN_ID`                                 | Positive numeric Telegram ID of the one owner                     |
| `OWNER_USERNAME`                           | Your contact username, without `@`                                |
| `STUDIO_ENV`                               | `development` for local HTTP; `production` for hosting            |
| `APP_ORIGIN`                               | `http://127.0.0.1:8000` locally; public HTTPS origin for Telegram |
| `DATABASE_URL`                             | Separate development PostgreSQL URL using `postgresql+psycopg://` |
| `S3_ENDPOINT`, `S3_BUCKET`                 | Private object-storage endpoint and actual bucket name            |
| `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` | Credentials scoped to the development bucket                      |
| `S3_REGION`, `S3_ADDRESSING_STYLE`         | Provider-specific region and `virtual` or `path` addressing       |
| `TRUSTED_PROXY`                            | Leave empty unless the immediate proxy/network has been verified  |

The legacy `DB_PATH` setting belongs to `orderbot`, not the current Studio database. SQLite is supported only in development and disposable tests; production requires PostgreSQL.

### Linux and macOS shell

Use the same versions and environment variables. The equivalent installation commands are:

```sh
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
npm --prefix web ci
npm --prefix web run build
if [ ! -e .env ]; then cp .env.example .env; fi
```

After editing `.env` and preparing the development database:

```sh
.venv/bin/python -m dotenv -f .env run --no-override -- .venv/bin/python -m nexcora_studio.cli migrate
.venv/bin/python -m dotenv -f .env run --no-override -- .venv/bin/python -m nexcora_studio.cli check
.venv/bin/python -m nexcora_studio
# Run in a separate terminal:
.venv/bin/python -m nexcora_studio.bot
```

For headless browser tests on Linux, install browser system dependencies with `npm --prefix web exec -- playwright install --with-deps chromium`.

## Start the application

Create the development PostgreSQL database first, then migrate it:

```powershell
.\.venv\Scripts\python.exe -m dotenv -f .env run --no-override -- .\.venv\Scripts\python.exe -m nexcora_studio.cli migrate
.\.venv\Scripts\python.exe -m dotenv -f .env run --no-override -- .\.venv\Scripts\python.exe -m nexcora_studio.cli check
.\.venv\Scripts\python.exe -m nexcora_studio
```

Web and bot load `.env` themselves; the migration CLI reads process environment, which is why the command above explicitly loads the file. Already-set environment variables keep priority. Neither application process runs migrations automatically.

Open `http://127.0.0.1:8000` to inspect the Telegram entry screen. To authenticate through Telegram, use a public HTTPS origin and configure the bot's Mini App URL accordingly. There is no normal-application login bypass or shared demo account.

Run the current bot in a second terminal:

```powershell
.\.venv\Scripts\python.exe -m nexcora_studio.bot
```

Only one poller may run for the same token. Use a different bot for local development if a hosted poller is already active. Stop each process with Ctrl+C.

| Bot command            | Behavior                                                   |
| ---------------------- | ---------------------------------------------------------- |
| `/start`, `/menu`      | Open the client workspace or owner dashboard               |
| `/new`                 | Open a client draft; show the dashboard to the owner       |
| `/myorders`, `/orders` | Open personal projects or the owner's queue                |
| `/owner`               | Open the owner dashboard only for the configured owner     |
| `/myid`                | Show the current Telegram user ID                          |
| `/help`                | Show the app entry and help text                           |
| `/language`            | Choose Russian, English or Kazakh for the bot and Mini App |

## Docker options

The Dockerfile builds the frontend with Node.js 24 and packages it with Python 3.14. The runtime runs as a non-root user. Build it without embedding an environment file:

```powershell
docker build --tag nexcora-studio:local .
```

With an appropriate `.env`, the web process can run as follows:

```powershell
docker run --rm --env-file .env --publish 127.0.0.1:8000:8000 nexcora-studio:local
```

Database and object-storage URLs must be reachable from inside the container; a host's `127.0.0.1` points to the container itself. Migrations and the bot are separate commands described in [Deployment](deployment.md). This is not a one-command production stack.

`compose.yaml` supplies **only a disposable/local PostgreSQL service**, bound to host port 55432. Its sample password is for local development. Start it only if that port is free:

```powershell
docker compose up -d postgres
```

The sample database is named `nexcora_test`; use it for the dedicated test run below. Keep development and test data separate.

## Verification

The offline suite uses temporary SQLite files and local Telegram/storage adapters. It never polls or sends messages to real users.

```powershell
Remove-Item Env:TEST_DATABASE_URL -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
npm.cmd --prefix web run typecheck
npm.cmd --prefix web run build
npm.cmd --prefix web run test:e2e
```

Playwright starts a temporary backend on port 8765 and signs synthetic Telegram identities with a test-only token. It uses a fresh browser profile. On Windows it uses installed Edge when available; otherwise install Chromium:

```powershell
npm.cmd --prefix web exec -- playwright install chromium
```

The PostgreSQL suite requires a dedicated database name ending in `_test` or beginning with `test_`. It creates and deletes random schemas. The restore check also creates a separate temporary database and requires matching `pg_dump`/`pg_restore` binaries, available in `PATH` or the `PG_BIN` directory.

For the local Compose service, use its documented **synthetic local credentials**:

```powershell
$env:TEST_DATABASE_URL = 'postgresql+psycopg://nexcora_local:local_development_only@127.0.0.1:55432/nexcora_test'
# If matching native tools are not in PATH, set the directory that contains them:
# $env:PG_BIN = 'C:\path\to\postgresql-17\bin'
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
Remove-Item Env:TEST_DATABASE_URL
```

Never substitute a production database URL. Without `TEST_DATABASE_URL`, PostgreSQL checks are skipped. Without matching native tools, the restore check is skipped. Skipped checks are not successful checks.

## Repository checks

The GitHub workflow runs isolated offline tests on Linux and Windows; PostgreSQL integration with matching native backup tools; the frontend build and browser flows; and a Docker build with runtime import checks. It needs no production bot, database or storage credentials. Browser failure traces contain synthetic fixtures and are retained briefly for debugging.
