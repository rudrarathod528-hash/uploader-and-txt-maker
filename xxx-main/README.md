# Uploader and TXT Maker service

The deployment and authentication API documentation is in the repository root [`README.md`](../README.md).

The application entry point is `auth_api.app:app`. On startup, `docker-entrypoint.sh` applies Alembic migrations and starts Uvicorn; FastAPI's lifespan also starts the Telegram bot when `BOT_ENABLED=true`.
