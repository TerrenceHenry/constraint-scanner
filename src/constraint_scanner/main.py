from __future__ import annotations

import uvicorn

from constraint_scanner.api.app import create_app
from constraint_scanner.config.loader import get_settings

app = create_app()


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "constraint_scanner.main:app",
        host=settings.app.host,
        port=settings.app.port,
        reload=settings.app.reload,
    )

