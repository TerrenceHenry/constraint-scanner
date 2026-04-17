from __future__ import annotations

import uvicorn

from constraint_scanner.api.app import create_app
from constraint_scanner.runtime import build_service_runtime

runtime = build_service_runtime()
app = create_app(
    settings=runtime.settings,
    service_runtime=runtime,
)


def main() -> None:
    settings = runtime.settings
    uvicorn.run(
        "constraint_scanner.main:app",
        host=settings.app.host,
        port=settings.app.port,
        reload=settings.app.reload,
    )
