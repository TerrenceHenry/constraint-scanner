from __future__ import annotations

from pathlib import Path

from constraint_scanner.config.loader import load_settings


def test_load_settings_from_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "settings.yaml"
    config_path.write_text(
        "\n".join(
            [
                "app:",
                "  port: 8100",
                "database:",
                "  host: db.local",
                "ingestion:",
                "  enabled: true",
            ]
        ),
        encoding="utf-8",
    )

    settings = load_settings(config_path=config_path, environ={})

    assert settings.app.port == 8100
    assert settings.database.host == "db.local"
    assert settings.ingestion.enabled is True


def test_env_overrides_yaml_and_supplies_secrets(tmp_path: Path) -> None:
    config_path = tmp_path / "settings.yaml"
    config_path.write_text(
        "\n".join(
            [
                "app:",
                "  port: 8100",
                "polymarket:",
                "  funder_address: 0xyamlfunder",
                "  api_secret: should-not-load",
            ]
        ),
        encoding="utf-8",
    )

    settings = load_settings(
        config_path=config_path,
        environ={
            "CONSTRAINT_SCANNER_APP_PORT": "8200",
            "CONSTRAINT_SCANNER_POLYMARKET_API_SECRET": "from-env",
            "CONSTRAINT_SCANNER_POLYMARKET_API_KEY": "key-from-env",
        },
    )

    assert settings.app.port == 8200
    assert settings.polymarket.funder_address == "0xyamlfunder"
    assert settings.polymarket.api_key is not None
    assert settings.polymarket.api_key.get_secret_value() == "key-from-env"
    assert settings.polymarket.api_secret is not None
    assert settings.polymarket.api_secret.get_secret_value() == "from-env"


def test_yaml_secret_values_are_ignored(tmp_path: Path) -> None:
    config_path = tmp_path / "settings.yaml"
    config_path.write_text(
        "\n".join(
            [
                "polymarket:",
                '  funder_address: "0xabc"',
                "  signature_type: 2",
                "  private_key: from-yaml",
                "  api_key: from-yaml",
                "  api_secret: from-yaml",
                "  api_passphrase: from-yaml",
            ]
        ),
        encoding="utf-8",
    )

    settings = load_settings(config_path=config_path, environ={})

    assert settings.polymarket.funder_address == "0xabc"
    assert settings.polymarket.signature_type == 2
    assert settings.polymarket.private_key is None
    assert settings.polymarket.api_key is None
    assert settings.polymarket.api_secret is None
    assert settings.polymarket.api_passphrase is None


def test_load_settings_reads_project_dotenv(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "settings.yaml"
    config_path.write_text(
        "\n".join(
            [
                "app:",
                "  port: 8100",
                "database:",
                "  host: db.local",
            ]
        ),
        encoding="utf-8",
    )
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "CONSTRAINT_SCANNER_APP_PORT=8300",
                "CONSTRAINT_SCANNER_DATABASE_PASSWORD=from-dotenv",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr("constraint_scanner.config.loader.DEFAULT_ENV_FILE_PATH", env_path)
    monkeypatch.delenv("CONSTRAINT_SCANNER_APP_PORT", raising=False)
    monkeypatch.delenv("CONSTRAINT_SCANNER_DATABASE_PASSWORD", raising=False)

    settings = load_settings(config_path=config_path)

    assert settings.app.port == 8300
    assert settings.database.host == "db.local"
    assert settings.database.password is not None
    assert settings.database.password.get_secret_value() == "from-dotenv"


def test_legacy_polymarket_websocket_url_is_normalized(tmp_path: Path) -> None:
    config_path = tmp_path / "settings.yaml"
    config_path.write_text(
        "\n".join(
            [
                "polymarket:",
                "  websocket_url: wss://ws-subscriptions-clob.polymarket.com/ws",
            ]
        ),
        encoding="utf-8",
    )

    settings = load_settings(config_path=config_path, environ={})

    assert settings.polymarket.websocket_url == "wss://ws-subscriptions-clob.polymarket.com/ws/market"
