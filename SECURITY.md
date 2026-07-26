# Security policy

## Secrets

- Never commit `.env`, `.env.local`, provider cookies, database files, access
  tokens, or real credentials.
- Browser-delivered `VITE_*` values are public. Restrict the AMap Web JS key to
  the exact allowed domains in the AMap console; never put an operator token or
  server API secret in a `VITE_*` variable.
- Generate `BOOKING_API_TOKEN` locally with a cryptographically random command
  such as `openssl rand -hex 32`. Send it only in the
  `X-G3TA-Booking-Token` header over HTTPS.
- Run `python scripts/check_secrets.py` before committing.

If a key ever enters a public commit, revoke or rotate it at the provider first.
Deleting the file or rewriting Git history does not make a copied credential
safe again.

## Sensitive features

Booking automation is disabled by default. The public frontend performs
comparison and provider handoff only; it does not collect Ctrip cookies,
passport/ID numbers, phone numbers, or payment details.

Operator-only browser automation requires both
`BOOKING_AUTOMATION_ENABLED=1` and `BOOKING_API_TOKEN`. A tokenless localhost
demo additionally requires the explicit
`ALLOW_LOCAL_BOOKING_WITHOUT_TOKEN=1` override.

Saved plans are private to the browser that created them through an HttpOnly,
SameSite cookie. Set `COOKIE_SECURE=1` for every HTTPS deployment.

## Reporting

Report a suspected vulnerability privately to the repository owner. Do not put
live credentials, personal information, or exploit details in a public issue.
