from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]


def test_example_config_contains_required_external_parameters() -> None:
    config_path = ROOT / "config" / "app.example.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    assert config["app"]["timezone"] == "Asia/Shanghai"
    assert config["imports"]["allowed_extensions"] == [".xlsx"]
    assert config["imports"]["template_id"] == "lyra_project_spec"
    assert config["imports"]["template_version"] == "1.0"
    assert config["imports"]["manifest_paths"] == ["config/templates/lyra_project_spec-v1.0.yaml"]
    assert config["object_storage"]["backend"] == "s3"
    assert config["object_storage"]["bucket"] == "project-manager"
    assert config["notifications"]["due_soon_days"] == 3
    assert config["llm"]["base_url"]
    assert config["llm"]["model"]


def test_example_config_does_not_contain_real_secrets() -> None:
    config_text = (ROOT / "config" / "app.example.yaml").read_text(encoding="utf-8")

    forbidden = ("sk-", "AKID", "BEGIN PRIVATE KEY")
    assert not any(value in config_text for value in forbidden)
