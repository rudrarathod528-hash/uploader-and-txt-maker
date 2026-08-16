# Uploader and TXT Maker

This repository runs the Telegram uploader bot and a FastAPI authentication service in the same Railway container. It does not need PostgreSQL, Redis, migrations, or any other external data service.

## Runtime architecture

Railway builds the root `Dockerfile`, which installs `xxx-main/requirements.txt` and copies the application into `/app`. The container entrypoint starts Uvicorn directly on Railway's `PORT`.

FastAPI provides:

- `POST /api/v1/auth/token` — Argon2id password verification and JWT access-token issuance
- `GET /health/live` — Railway liveness check
- `GET /health/ready` — application readiness check
- `GET /docs` — interactive API documentation

When `BOT_ENABLED=true`, FastAPI's lifespan starts the Pyrogram Telegram bot. The bot implements `/start`, `/txt`, `/STOP`, `/shell`, and the admin-only `/cookie` command. Telegram bot access is controlled separately by the comma-separated `AUTH_USERS` Telegram ID list; `/cookie` additionally requires an exact `ADMIN_USER_ID` match.

## Authentication endpoint

`POST /api/v1/auth/token`

```bash
curl -X POST https://YOUR-SERVICE.up.railway.app/api/v1/auth/token \
  -H 'Content-Type: application/json' \
  -d '{"identifier":"person@example.com","password":"your-password"}'
```

Successful response:

```json
{
  "success": true,
  "tokenType": "Bearer",
  "accessToken": "<JWT_ACCESS_TOKEN>",
  "refreshToken": "<OPAQUE_REFRESH_TOKEN>",
  "expiresIn": 3600
}
```

The successful response also sends `access_token` and `refresh_token` through separate `Set-Cookie` headers. Both cookies are `Secure`, `HttpOnly`, `SameSite=Strict`, and have explicit lifetimes. This allows `requests.Session` or a browser context to retain authenticated state automatically.

Invalid, unknown, and disabled accounts all receive the same `401` body:

```json
{
  "success": false,
  "error": {
    "code": "INVALID_CREDENTIALS",
    "message": "Invalid identifier or password"
  }
}
```

Passwords are stored only as Argon2id hashes in the `AUTH_API_USERS` environment variable. Users are normalized and indexed in memory by email, E.164 phone number, and/or case-insensitive username. JWT access tokens contain `sub`, `iat`, `exp`, `iss`, `aud`, `jti`, and `type` claims.

Login throttling is process-local and covers both normalized identifier and client IP. Unknown users still run Argon2 verification against a dummy hash to reduce timing-based account discovery. A concurrency limiter bounds Argon2 memory use during request bursts.

The response retains the existing opaque `refreshToken` field for API compatibility. This project currently has no refresh-token exchange endpoint.

## Configure API users

`AUTH_API_USERS` must be a JSON array. An empty array is valid and safely rejects every login.

`JWT_SECRET` and `REFRESH_TOKEN_PEPPER` are private random values generated specifically for your deployment; they do not come from Telegram or Railway. Generate both with:

```bash
cd xxx-main
python -m auth_api.cli generate-secrets
```

Copy each printed value into the matching Railway variable. Never commit these values to Git.

Generate one account object with the included CLI:

```bash
cd xxx-main
python -m auth_api.cli generate-user \
  --email person@example.com \
  --phone +919876543210 \
  --username person
```

The CLI prompts for the password twice without echoing it. For automation, it also supports `--password-env VARIABLE_NAME`; unset that temporary variable immediately after use.

The command prints an object like this (the values below are abbreviated placeholders):

```json
{"id":"a-stable-uuid","email":"person@example.com","phone":"+919876543210","username":"person","password_hash":"$argon2id$...","is_active":true}
```

Wrap one or more generated objects in a JSON array and save the complete minified value as Railway's `AUTH_API_USERS` variable:

```json
[{"id":"...","email":"person@example.com","phone":null,"username":"person","password_hash":"$argon2id$...","is_active":true}]
```

Do not place the plain password in Railway after generating the hash. Keep each generated `id` stable across configuration updates because it becomes the JWT `sub` claim. A configuration change takes effect after a redeploy/restart.

## Admin cookie-session command

The bot owns one process-local `requests.Session`. On the first authorized `/cookie` command it posts configured credentials to an authentication endpoint, captures `Set-Cookie` headers, and keeps the session active in memory. Later `/cookie` calls reuse the active cookie jar; `/cookie refresh` forces a new login.

Configure the feature with Railway variables:

```text
ADMIN_USER_ID=<the one Telegram user ID allowed to receive cookies>
COOKIE_AUTH_URL=https://accounts.example.com/login
COOKIE_AUTH_IDENTIFIER=person@example.com
COOKIE_AUTH_PASSWORD=<endpoint password>
COOKIE_AUTH_IDENTIFIER_FIELD=identifier
COOKIE_AUTH_PASSWORD_FIELD=password
COOKIE_AUTH_REQUEST_FORMAT=json
COOKIE_AUTH_TIMEOUT_SECONDS=30
COOKIE_AUTH_EXTRA_FIELDS={}
COOKIE_AUTH_HEADERS={}
```

To authenticate against this project's own endpoint, set `COOKIE_AUTH_URL=https://YOUR-SERVICE.up.railway.app/api/v1/auth/token`, use the API user's identifier/password, set `COOKIE_AUTH_IDENTIFIER_FIELD=identifier`, and keep `COOKIE_AUTH_REQUEST_FORMAT=json`.

Set `COOKIE_AUTH_REQUEST_FORMAT=form` when another endpoint expects form-encoded credentials. `COOKIE_AUTH_EXTRA_FIELDS` and `COOKIE_AUTH_HEADERS` accept JSON objects, for example:

```text
COOKIE_AUTH_EXTRA_FIELDS={"remember":true}
COOKIE_AUTH_HEADERS={"Accept":"application/json"}
```

Only the exact `ADMIN_USER_ID` can execute the command. Cookie JSON is always sent to that user's private Telegram chat, even when the command originates in a group. Large cookie payloads are sent as `cookies.json`. Cookie values are never written to application logs or disk, and restarting the container clears the session.

The endpoint must return at least one cookie through `Set-Cookie`; a token-only JSON response is intentionally rejected as an empty cookie session. Because the existing bot uses Pyrogram, the command is implemented in Pyrogram instead of starting a second `python-telegram-bot` poller with the same bot token.

## Railway deployment

The root `Dockerfile` and `railway.json` deploy the repository without selecting a subdirectory.

1. Create a Railway project from this repository. No PostgreSQL or Redis service is needed.
2. Configure authentication variables:

   ```text
   AUTH_API_USERS=<JSON array generated above, or []>
   JWT_SECRET=<at least 32 random bytes>
   REFRESH_TOKEN_PEPPER=<a different value of at least 32 random bytes>
   ```

3. Configure Telegram variables when the bot is enabled:

   ```text
   BOT_ENABLED=true
   API_ID=<Telegram API ID>
   API_HASH=<Telegram API hash>
   BOT_TOKEN=<BotFather token>
   AUTH_USERS=<comma-separated Telegram user IDs>
   GROUPS=<optional comma-separated Telegram group IDs>
   ```

   To deploy only the API, set `BOT_ENABLED=false`; Telegram variables are then not read by the running process.

4. Generate `JWT_SECRET` and `REFRESH_TOKEN_PEPPER` independently:

   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```

5. Deploy and verify `GET /health/live` and `GET /health/ready`.

Use one replica while `BOT_ENABLED=true`, because multiple replicas would poll the same Telegram bot. Process-local rate-limit counters are independent per replica and reset whenever an instance restarts.

All variables are documented in `xxx-main/.env.example`. For a browser frontend on another origin, set `CORS_ORIGINS` to a comma-separated allowlist; no origin is allowed by default.

## Local development

```bash
cd xxx-main
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Fill JWT_SECRET, REFRESH_TOKEN_PEPPER, and optionally AUTH_API_USERS, then:
BOT_ENABLED=false uvicorn auth_api.app:app --reload --host 0.0.0.0 --port 8080
```

API documentation is available at `/docs`.

## Important security note

The legacy project previously contained Telegram/Classplus credentials in source files. They have been removed from the current tree, but Git history cannot make an exposed credential safe. Rotate every previously committed bot token, API hash, and third-party token before deployment, then store replacements only in Railway variables.

The `/shell` bot command executes operating-system commands. Keep `AUTH_USERS` restricted to Telegram IDs you fully trust, or remove that command before making the bot broadly available.

## Main code locations

- FastAPI lifecycle: `xxx-main/auth_api/app.py`
- Authentication route: `xxx-main/auth_api/routes/auth.py`
- Environment-backed users: `xxx-main/auth_api/users.py`
- JWT and Argon2id logic: `xxx-main/auth_api/security.py`
- Process-local rate limiter: `xxx-main/auth_api/rate_limit.py`
- Persistent HTTP session manager: `xxx-main/cookie_session.py`
- Telegram bot and `/cookie` handler: `xxx-main/main.py`
