# Hosted visitor registration

The public simulator requires name, email and an industry selection before creating a session. Local/offline builds do not collect visitor details. The public recorded research page remains readable without registering.

Legacy name-only receipts no longer authorize new sessions; those visitors must complete the form. Existing records are preserved.

The dialog appears on first arrival and can be dismissed; starting a session brings it back. The Worker also rejects session creation without a valid registration receipt. A Secure, HttpOnly, SameSite=Strict cookie remembers the browser for 30 days; its random value is stored only as a SHA-256 digest in D1. This is an admission receipt, not identity verification: names and emails are self-reported.

## Storage and contact preferences

Cloudflare D1 database: `ot-lab-visitors`; table: `visitors`.

Columns contain the requested fields, an explicit contact-consent flag, notice version, creation timestamp and receipt expiry. Details remain outside simulation containers and model prompts. No email is automatically sent. Registration does not imply permission to contact: use only rows with `contact_consent = 1` for updates, feedback requests or collaboration outreach.

In the authenticated Cloudflare dashboard, open **Storage & databases → D1 → ot-lab-visitors → Console**. A useful private query is:

```sql
SELECT name, email, industry, contact_consent,
       datetime(created_at / 1000, 'unixepoch') AS registered_utc
FROM visitors ORDER BY created_at DESC;
```

There is no public endpoint for listing contacts. Do not commit exports, copy records into model prompts, or publish screenshots of the contact table. Registration records persist until the owner deletes them; the 30-day cookie expiry does not delete contact details. Review retained records periodically and remove those no longer needed.

The form links to Isaac's LinkedIn for access/deletion requests. After verifying a request privately, use bound SQL parameters (or the dashboard's row editor) to delete matching records or set `contact_consent = 0`. Deleting a row also invalidates that browser's admission receipt. Cloudflare recovery backups have their own retention.

## Operations

Apply schema changes before deploying the Worker:

```sh
node deploy/cloudflare-live/node_modules/wrangler/bin/wrangler.js d1 migrations apply ot-lab-visitors --remote --config deploy/cloudflare-live/wrangler.jsonc
```

The submission endpoint rejects cross-origin writes, invalid field values, oversized bodies and non-JSON requests. Cloudflare's per-IP rate limiter permits five attempts per minute; this rate limit is abuse friction, not an identity check. IP addresses are not stored in the visitor table. D1 failures fail closed and keep the form available for retry.

Only the Worker and static assets need updating for registration. Deploy with `--containers-rollout none` to preserve the existing simulation container image.
