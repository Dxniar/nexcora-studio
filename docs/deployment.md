# Deployment and operations

## Runtime topology

The application uses one image and two separately supervised processes:

| Process                                          | Command                                | Public network                    |
| ------------------------------------------------ | -------------------------------------- | --------------------------------- |
| Web and API                                      | `python -m nexcora_studio`             | HTTPS                             |
| Bot, notification worker and file-cleanup worker | `python -m nexcora_studio.bot`         | None required for inbound traffic |
| Database migration                               | `python -m nexcora_studio.cli migrate` | Run as a release/pre-deploy task  |
| Database schema check                            | `python -m nexcora_studio.cli check`   | Administrative task               |

Both processes need access to the same PostgreSQL database and private S3-compatible bucket. They must use the same `APP_ORIGIN`, bot token and owner ID. Outbound Telegram API access is required by the bot. Node.js is used only in the frontend build stage.

The reference demo is hosted on Railway, with web, bot, PostgreSQL and object storage in one project. Provider resource IDs and credentials are deliberately absent from this public guide. The architecture can also run on another provider that supplies these dependencies.

## Configuration

Use the variables documented in [Development](development.md#install) and the `.env.example` template. In hosting, configure secrets directly in the provider's environment settings. Do not copy a local `.env` into an image, repository or frontend build.

Production requires `STUDIO_ENV=production`, a PostgreSQL `DATABASE_URL`, an HTTPS `APP_ORIGIN` and complete private storage configuration. Keep PostgreSQL on the provider's private network and the bucket private. The API serves authorized file downloads; public object URLs are not part of the client workflow.

The web process listens on `0.0.0.0:$PORT`, defaulting to port 8000. Only it needs a public domain. Run a **single bot replica** per token: the poller uses a PostgreSQL advisory lock, and a second poller fails rather than consuming updates concurrently.

## Release sequence

1. Build the image from the reviewed source and locked dependencies. The build context excludes environment files, working databases, backups and test artifacts.
2. Configure the database, private bucket and server-side variables. Verify actual connectivity separately from the presence of variable names.
3. Apply migrations with the same image as the release. Stop the rollout if migration fails; migrations do not run automatically at application startup.
4. Start/update the web process and check its public health endpoints.
5. Stop the previous bot process gracefully, then start the replacement. Do not start a second production poller for a smoke test.
6. Configure the Mini App URL in BotFather, open it from Telegram and verify both client and owner behavior.

`railway.json` contains shared build/replica/restart settings. Configure process-specific start commands, the web pre-deploy migration and the web health path per service. Do not apply an HTTP health check or web start command to the bot service.

## Health and smoke checks

| Check                                | What it establishes                                             |
| ------------------------------------ | --------------------------------------------------------------- |
| `GET /health/live`                   | The HTTP process responds                                       |
| `GET /health/ready`                  | A database query succeeds and the storage adapter is configured |
| `python -m nexcora_studio.cli check` | The configured database and schema are accessible               |
| Worker heartbeat records             | The relevant loop has recently completed an operation           |

Readiness does not verify every stored file, Telegram delivery, external bucket connectivity or a complete client workflow. Use a synthetic request and attachment to verify upload, download permissions, checksum and deletion. Confirm that another client cannot access the project or its attachments.

For every release that changes authentication or workflow, verify real Telegram entry and a client journey through proposal acceptance and delivery. Automated browser tests use a separate synthetic environment and cannot establish provider-side sign-in behavior.

## Delivery and privacy

Business changes and their outbox events commit in one transaction. Telegram delivery uses leases, bounded retries and an owner-visible failure queue. Delivery is at least once: if Telegram sends a message but its response is lost, retrying can repeat the notification. It does not repeat the business action.

Confirmed account-data deletion removes database access immediately and schedules private objects for durable physical cleanup. Cleanup can finish later. Already sent Telegram messages and backups have separate retention and cannot be treated as revoked by deleting the account.

The language stored on the recipient's account is read when preparing a notification. Changing a language does not translate existing user-written project content or rewrite old Telegram messages.

## Backups and recovery

Back up **both** PostgreSQL metadata and private objects. A database dump alone cannot restore missing attachment bytes. Store backups outside the public repository and control their access and retention separately from live application data.

Use compatible PostgreSQL backup tools. Rehearse recovery into a separate database and private test bucket, and verify project relationships, file sizes and checksums before treating a backup procedure as operational. The repository's restore test uses a synthetic database and a controlled object copy; it does not prove that provider backups or real customer-file recovery are configured.

The reference demo has had an isolated initial-database restore exercise. It does not establish scheduled backups, point-in-time recovery or recovery of real customer uploads. These must be set up and verified before the demo becomes a customer-facing service.

## Launch checks that remain operator responsibilities

- Confirm current provider pricing, quotas and expiry conditions in the account.
- Verify the immediate reverse proxy before setting `TRUSTED_PROXY`; never trust arbitrary forwarded headers. With it unset, clients behind one proxy may share a login rate-limit bucket.
- Exercise graceful restarts and inspect failed delivery/cleanup jobs.
- Validate backups and recovery with representative files and document retention.
- Walk through the complete client and owner workflow in live Telegram.

Payments, AI chat and multi-assignee workflows are not implemented in this release. Proposal agreement is not evidence of payment. No production capacity, commercial adoption or continuous-availability guarantee is claimed.
