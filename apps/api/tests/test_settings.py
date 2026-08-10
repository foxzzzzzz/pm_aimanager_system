from pathlib import Path

import yaml

from project_manager_api.settings import AppSettings

ROOT = Path(__file__).resolve().parents[3]


def test_example_config_contains_required_external_parameters() -> None:
    config_path = ROOT / "config" / "app.example.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    assert config["app"]["timezone"] == "Asia/Shanghai"
    assert config["imports"]["allowed_extensions"] == [".xlsx"]
    assert config["imports"]["max_uncompressed_size_mb"] > config["imports"]["max_file_size_mb"]
    assert config["imports"]["max_archive_entries"] > 0
    assert config["imports"]["timeout_seconds"] > 0
    assert config["imports"]["template_id"] == "lyra_project_spec"
    assert config["imports"]["template_version"] == "1.0"
    assert config["imports"]["manifest_paths"] == ["config/templates/lyra_project_spec-v1.0.yaml"]
    assert config["object_storage"]["backend"] == "s3"
    assert config["object_storage"]["bucket"] == "project-manager"
    assert config["notifications"]["due_soon_days"] == 3
    assert config["llm"]["base_url"]
    assert config["llm"]["model"]
    assert config["llm"]["max_retries"] == 2
    assert config["llm"]["retry_base_delay_seconds"] > 0
    assert config["llm"]["retry_max_delay_seconds"] >= config["llm"]["retry_base_delay_seconds"]
    assert config["llm"]["structured_output_mode"] == "auto"
    assert config["security"]["admin_actor_id"] == "pm-001"
    assert config["security"]["admin_api_token_env"] == "ADMIN_API_TOKEN"
    assert config["security"]["phone_hmac_key_env"] == "PHONE_HMAC_KEY"
    assert config["security"]["phone_encryption_key_env"] == "PHONE_ENCRYPTION_KEY"


def test_example_config_does_not_contain_real_secrets() -> None:
    config_text = (ROOT / "config" / "app.example.yaml").read_text(encoding="utf-8")

    forbidden = ("sk-", "AKID", "BEGIN PRIVATE KEY")
    assert not any(value in config_text for value in forbidden)


def test_production_channel_and_cors_settings_can_be_overridden_by_environment(
    monkeypatch,
) -> None:
    monkeypatch.setenv("PROJECT_MANAGER_CORS_ORIGINS", "https://pm.example.com,https://ops.example.com")
    monkeypatch.setenv("WECHAT_SUBSCRIPTION_TEMPLATE_ID", "wechat-template")
    monkeypatch.setenv("WECHAT_SUBSCRIPTION_TITLE_FIELD", "thing5")
    monkeypatch.setenv("WECHAT_SUBSCRIPTION_BODY_FIELD", "thing8")
    monkeypatch.setenv("TENCENT_SMS_REGION", "ap-shanghai")
    monkeypatch.setenv("TENCENT_SMS_SDK_APP_ID", "1400000000")
    monkeypatch.setenv("TENCENT_SMS_SIGN_NAME", "approved-sign")
    monkeypatch.setenv("TENCENT_SMS_CRITICAL_TEMPLATE_ID", "1234567")

    settings = AppSettings.from_environment()

    assert settings.cors_origins == ["https://pm.example.com", "https://ops.example.com"]
    assert settings.wechat_subscription_template_id == "wechat-template"
    assert settings.wechat_subscription_title_field == "thing5"
    assert settings.wechat_subscription_body_field == "thing8"
    assert settings.sms_region == "ap-shanghai"
    assert settings.sms_sdk_app_id == "1400000000"
    assert settings.sms_sign_name == "approved-sign"
    assert settings.sms_critical_template_id == "1234567"
