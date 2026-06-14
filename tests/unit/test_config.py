from __future__ import annotations

from pathlib import Path

import pytest

from miniagent.config import Config, load_config


def test_loads_minimal_user_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        "[llm]\n"
        'api_key = "sk-ant-test"\n'
        'base_url = "https://api.anthropic.com"\n'
        'model = "claude-sonnet-4-6"\n'
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr("miniagent.config.DEFAULT_USER_CONFIG", cfg_file)
    monkeypatch.setattr(
        "miniagent.config.DEFAULT_PROJECT_CONFIG", tmp_path / "missing-project.toml"
    )

    cfg = load_config()

    assert isinstance(cfg, Config)
    assert cfg.llm.api_key == "sk-ant-test"
    assert cfg.llm.model == "claude-sonnet-4-6"
    assert cfg.llm.base_url == "https://api.anthropic.com"


def test_missing_api_key_exits(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('[llm]\nbase_url = "https://x"\nmodel = "m"\n')
    with pytest.raises(SystemExit) as exc:
        load_config(user_path=cfg_file, project_path=tmp_path / "missing")
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert "api_key" in captured.err
    assert "sk-ant-" in captured.err  # hint printed


def test_cli_override_wins(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('[llm]\napi_key = "k1"\nmodel = "m1"\n')
    cfg = load_config(
        user_path=cfg_file,
        project_path=tmp_path / "missing",
        cli_overrides={"llm": {"model": "m2"}},
    )
    assert cfg.llm.api_key == "k1"
    assert cfg.llm.model == "m2"


def test_agent_config_system_prompt_default() -> None:
    from miniagent.config import AgentConfig

    cfg = AgentConfig()
    assert cfg.system_prompt == ""


def test_agent_config_system_prompt_custom() -> None:
    from miniagent.config import AgentConfig

    cfg = AgentConfig(system_prompt="Be helpful")
    assert cfg.system_prompt == "Be helpful"
