from __future__ import annotations

import asyncio
import json
from dataclasses import asdict

from constraint_scanner.manual_constraints import seed_example_manual_constraints
from constraint_scanner.runtime import build_service_runtime


def main() -> None:
    runtime = build_service_runtime()
    try:
        result = seed_example_manual_constraints(runtime.session_factory)
        print(json.dumps(asdict(result), indent=2, sort_keys=True, default=str))
    finally:
        asyncio.run(runtime.aclose())


if __name__ == "__main__":
    main()
