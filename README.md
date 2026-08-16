# Uploader and TXT Maker

This repository runs the existing Telegram uploader bot and a production-oriented FastAPI authentication service in the same Railway container.

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

The identifier resolver normalizes and looks up exactly one indexed column:

- email -> `users.email_normalized`
- phone -> `users.phone_e164` (E.164 format)
- username -> `users.username_normalized`

The parameterized SQLAlchemy lookup is in `xxx-main/auth_api/repositories.py`. Passwords use Argon2id. Access tokens are signed HS256 JWTs with `sub`, `iat`, `exp`, `iss`, `aud`, `jti`, and `type` claims. Refresh tokens are random opaque values; only an HMAC-SHA256 digest is saved in PostgreSQL.

Brute-force protection uses atomic Redis counters for both normalized identifier and client IP. Redis failures fail authentication closed with `503` rather than silently disabling rate limiting. Unknown users still run an Argon2 verification against a dummy hash to reduce timing-based account discovery, and a process-local concurrency limiter bounds Argon2 memory use during request bursts.

## Railway deployment

The root `Dockerfile` and `railway.json` allow Railway to deploy the repository without selecting a subdirectory.

1. Create a Railway project from this repository.
2. Add a Railway **PostgreSQL** service and a **Redis** service.
3. Make sure their reference variables expose `DATABASE_URL` and `REDIS_URL` to the application service.
4. Configure these required application variables:

   ```text
   JWT_SECRET=<at least 32 random bytes>
   REFRESH_TOKEN_PEPPER=<a different value of at least 32 random bytes>
   API_ID=<Telegram API ID>
   API_HASH=<Telegram API hash>
   BOT_TOKEN=<BotFather token>
   AUTH_USERS=<comma-separated Telegram user IDs>
   GROUPS=<optional comma-separated Telegram group IDs>
   BOT_ENABLED=true
   ```

   Generate each application secret independently:

   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```

   To deploy only the API, set `BOT_ENABLED=false`; the Telegram variables are then not needed by the running process.

5. Deploy. The container automatically runs `alembic upgrade head`, binds Uvicorn to Railway's `PORT` on `0.0.0.0`, and starts the Telegram bot from the FastAPI lifespan.
6. Verify `GET /health/live` and `GET /health/ready`.

Use one replica while `BOT_ENABLED=true`, because multiple replicas would all poll the same Telegram bot. An API-only deployment can be scaled horizontally because PostgreSQL and Redis hold shared state.

All available variables are documented in `xxx-main/.env.example`. For a browser frontend on another origin, set `CORS_ORIGINS` to a comma-separated allowlist; no origin is allowed by default.

### Create the first user

Run migrations, then use the administration CLI from a Railway shell or locally with the same environment variables:

```bash
cd xxx-main
python -m auth_api.cli create-user \
  --email person@example.com \
  --phone +919876543210 \
  --username person
```

The CLI prompts for the password without echoing it. For a non-interactive one-off task, put the password in a temporary environment variable and use `--password-env VARIABLE_NAME`; remove that variable immediately afterward.

## Local API development

```bash
cd xxx-main
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Fill .env, then:
alembic upgrade head
BOT_ENABLED=false uvicorn auth_api.app:app --reload --host 0.0.0.0 --port 8080
```

API documentation is available at `/docs`.

## Important security note

The legacy project previously contained Telegram/Classplus credentials in source files. They have been removed from the current tree, but Git history cannot make an exposed credential safe. Rotate every previously committed bot token, API hash, and third-party token before deployment, then store replacements only in Railway variables.

## Main code locations

- Route/controller: `xxx-main/auth_api/routes/auth.py`
- Dynamic database query: `xxx-main/auth_api/repositories.py`
- JWT, Argon2id, and refresh token logic: `xxx-main/auth_api/security.py`
- Redis rate limiter: `xxx-main/auth_api/rate_limit.py`
- Database models: `xxx-main/auth_api/models.py`
- Initial migration: `xxx-main/migrations/versions/20260816_0001_create_auth_tables.py`
