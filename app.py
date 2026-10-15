"""ASGI entry point for local Uvicorn and the Vercel FastAPI runtime."""
from greenhome.hosted import configure_hosted

configure_hosted()

from greenhome.api import app  # noqa: E402,F401
