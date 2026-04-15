from __future__ import annotations

from decimal import Decimal
from uuid import UUID

APP_NAME = "Constraint Scanner v1"
DEFAULT_VENUE = "polymarket"
DEFAULT_TRADING_MODE = "disabled"
DEFAULT_TIME_IN_FORCE = "GTC"
MIDPOINT_DIAGNOSTIC_NOTE = "Midpoint is diagnostic only and not executable."
DECIMAL_ZERO = Decimal("0")
DEFAULT_MAX_BOOK_LEVELS = 50
ID_NAMESPACE = UUID("6b79ef56-a531-5f5f-9541-2c76a4f1c9e4")
POLYMARKET_GAMMA_BASE_URL = "https://gamma-api.polymarket.com"
POLYMARKET_CLOB_BASE_URL = "https://clob.polymarket.com"
POLYMARKET_MARKET_WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
