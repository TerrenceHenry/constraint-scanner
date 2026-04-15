from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class BaseSection(BaseModel):
    model_config = ConfigDict(extra="ignore")


class AppSettings(BaseSection):
    name: str = "Constraint Scanner v1"
    version: str = "0.1.0"
    environment: str = "local"
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"
    reload: bool = True


class DatabaseSettings(BaseSection):
    host: str = "localhost"
    port: int = 5432
    name: str = "constraint_scanner"
    user: str = "constraint_scanner"
    password: SecretStr | None = None
    url: SecretStr | None = None
    echo: bool = False
    pool_size: int = 5

    def sqlalchemy_url(self) -> str:
        if self.url is not None:
            return self.url.get_secret_value()

        password = self.password.get_secret_value() if self.password is not None else ""
        credentials = self.user
        if password:
            credentials = f"{self.user}:{password}"
        return f"postgresql+psycopg://{credentials}@{self.host}:{self.port}/{self.name}"


class PolymarketSettings(BaseSection):
    rest_base_url: str = "https://clob.polymarket.com"
    websocket_url: str = "wss://ws-subscriptions-clob.polymarket.com/ws"
    funder_address: str | None = None
    signature_type: int | None = 2
    private_key: SecretStr | None = None
    api_key: SecretStr | None = None
    api_secret: SecretStr | None = None
    api_passphrase: SecretStr | None = None


class IngestionSettings(BaseSection):
    enabled: bool = False
    poll_interval_seconds: int = 5
    batch_size: int = 100
    bootstrap_limit: int = 100
    max_depth_levels: int = 10
    archive_raw_messages: bool = True
    stale_after_seconds: int = 30


class GroupingSettings(BaseSection):
    window_seconds: int = 60
    max_group_size: int = 50


class DetectionSettings(BaseSection):
    enabled: bool = False
    confidence_threshold: float = 0.8
    min_edge_bps: float = 0.0
    max_legs: int = 8
    enable_sell_side: bool = False


class SimulationSettings(BaseSection):
    enabled: bool = False
    starting_cash: float = 10_000.0
    slippage_bps: int = 5


class RiskSettings(BaseSection):
    max_notional_usd: float = 1_000.0
    max_position_pct: float = 0.1
    kill_switch: bool = True


class TradingSettings(BaseSection):
    enabled: bool = False
    paper: bool = True
    default_order_size_usd: float = 25.0


class Settings(BaseSection):
    app: AppSettings = Field(default_factory=AppSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    polymarket: PolymarketSettings = Field(default_factory=PolymarketSettings)
    ingestion: IngestionSettings = Field(default_factory=IngestionSettings)
    grouping: GroupingSettings = Field(default_factory=GroupingSettings)
    detection: DetectionSettings = Field(default_factory=DetectionSettings)
    simulation: SimulationSettings = Field(default_factory=SimulationSettings)
    risk: RiskSettings = Field(default_factory=RiskSettings)
    trading: TradingSettings = Field(default_factory=TradingSettings)
