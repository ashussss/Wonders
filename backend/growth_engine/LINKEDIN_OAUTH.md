# LinkedIn OAuth 2.0 — Authorization Code flow (Growth Engine)

Implementation: `backend/growth_engine/linkedin.py` (protocol) and
`backend/growth_engine/integrations.py` (HTTP routes, mounted under
`/api/growth/integrations`).

## Required environment variables

```bash
LINKEDIN_CLIENT_ID=your_linkedin_app_client_id
LINKEDIN_CLIENT_SECRET=your_linkedin_app_client_secret
LINKEDIN_REDIRECT_URI=https://<your-backend-host>/api/growth/integrations/linkedin/callback
```

`LINKEDIN_REDIRECT_URI` MUST match the "Authorized redirect URLs" entry in the
LinkedIn Developer Portal **exactly** (scheme, host, path, no trailing slash).
A mismatch fails at the token exchange, not at the consent screen.

## Optional (defaults are the live LinkedIn endpoints)

```bash
LINKEDIN_AUTH_BASE_URL=https://www.linkedin.com/oauth/v2/authorization
LINKEDIN_TOKEN_URL=https://www.linkedin.com/oauth/v2/accessToken
LINKEDIN_USERINFO_URL=https://api.linkedin.com/v2/userinfo
```

## Also required

```bash
# Token encryption at rest. Already used by the main app for settings secrets.
# Generate: python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
FERNET_KEY=...

# Where the OAuth callback redirects the browser on success/failure.
FRONTEND_URL=https://showupai.live
```

If `FERNET_KEY` is absent the engine **refuses** to store an access token rather
than writing it in plaintext. The connect flow reports this to the user.

## Scopes requested

```
openid profile email w_member_social
```

These are member-level permissions. They must be **approved in the Developer
Portal** for the app, otherwise LinkedIn rejects the authorization request and
the connect flow surfaces that error. We do not request `r_organization_social`
or `rw_organization_admin` in this phase, so **organization/company-page posting
is not available** — the data model has `account_type` so it can be added later
with a separately approved app.

LinkedIn does **not** issue a refresh token for this flow. The engine stores the
`expires_at` LinkedIn reports and requires the member to reconnect when it
lapses. There is no invented refresh logic.

## Capability boundaries (also exposed at `GET /api/growth/integrations`)

Available via API with the scopes above:
- read the connected member's own profile (openid/profile/email)
- publish posts as that member (`w_member_social`)

Requires separate LinkedIn approval (not implemented here):
- posting to an Organization page (Community Management API)
- reading member analytics (`r_organization_social`)

Not supported by LinkedIn at all — never attempted:
- searching/reading other members' profiles
- reading another member's activity feed
- connection requests or messaging
- automated likes/follows/comments
- scraping linkedin.com

## Flow

1. `GET /api/growth/integrations/linkedin/connect` (JWT required)
   creates a 256-bit, single-use, 10-minute `state` bound to the authenticated
   `owner_id` and returns/redirects to the LinkedIn authorization URL. Only the
   SHA-256 hash of the state is stored.
2. LinkedIn redirects to `GET /api/growth/integrations/linkedin/callback`
   with `code` + `state`. This endpoint has **no JWT** — the owner is recovered
   from the stored state, never from anything in the URL.
3. The engine exchanges the code, calls `userinfo`, encrypts the access token,
   and upserts `growth_social_connections`.
4. The browser is redirected to `FRONTEND_URL/integrations?li_status=connected`.

## Multi-client

Every connection is keyed by `owner_id`. One ShowUp Developer App serves all
customers; tokens never mix. `get_access_token()` requires `owner_id` — there is
no global-token lookup and no `SOCIAL_ACCOUNT_EMAIL` fallback.

## Collections

- `growth_social_connections` — indexes on (owner_id, platform),
  (owner_id, platform, platform_user_id), (platform, platform_user_id), (id)
- `growth_oauth_states` — indexes on (state_hash unique), (expires_at_ts),
  (owner_id, platform)

## Tests

```bash
# protocol + storage unit tests (real mongod, LinkedIn mocked)
MONGO_URL=mongodb://127.0.0.1:27019 python -m pytest backend/tests/test_growth_linkedin.py -v

# end-to-end through the real FastAPI app (standalone runner)
MONGO_URL=mongodb://127.0.0.1:27019 python backend/tests/verify_growth_linkedin_flow.py
```