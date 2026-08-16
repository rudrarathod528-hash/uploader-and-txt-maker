# Uploader and TXT Maker service

The deployment and API documentation is in the repository root [`README.md`](../README.md).

The application entry point is `auth_api.app:app`. `docker-entrypoint.sh` starts Uvicorn directly, and FastAPI's lifespan starts the Telegram bot when `BOT_ENABLED=true`. Authentication users are loaded from `AUTH_API_USERS`; no external data service is required. The admin-only `/cookie` command uses the process-local session manager in `cookie_session.py`.
