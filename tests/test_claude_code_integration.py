import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
INTEGRATION = ROOT / "integrations" / "claude-code"


@pytest.fixture(scope="module")
def server():
    pytest.importorskip("mcp.server.mcpserver")
    spec = importlib.util.spec_from_file_location("ph_mcp_server", INTEGRATION / "mcp_server.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_find_screenshot_takes_last_fresh_path(server, tmp_path):
    old, new = tmp_path / "old.png", tmp_path / "new.png"
    old.write_bytes(b"x")
    new.write_bytes(b"x")
    past = time.time() - 3600
    os.utime(old, (past, past))
    out = f"{new}\n{old}\nrelative.png\n"
    assert server.find_screenshot(out, since=time.time() - 5) == str(new)


def test_find_screenshot_ignores_missing(server, tmp_path):
    assert server.find_screenshot(f"{tmp_path}/nope.png", since=0) is None


def test_child_env_scrubs_secrets(server, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setenv("GITHUB_TOKEN", "x")
    monkeypatch.setenv("PHONE_HARNESS_PLATFORM", "android")
    env = server._child_env()
    assert "OPENAI_API_KEY" not in env and "GITHUB_TOKEN" not in env
    assert env["PHONE_HARNESS_PLATFORM"] == "android"


def test_clamp_timeout(server):
    assert server._clamp_timeout(1) == server.MIN_TIMEOUT_S
    assert server._clamp_timeout(10**6) == server.MAX_TIMEOUT_S
    assert server._clamp_timeout("bad") == server.DEFAULT_TIMEOUT_S


@pytest.mark.skipif(sys.platform == "win32", reason="bash script")
def test_add_to_repo_is_idempotent_and_merges(tmp_path):
    (tmp_path / ".mcp.json").write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}}))
    (tmp_path / "CLAUDE.md").write_text("# Existing\n")
    script = INTEGRATION / "add-to-repo.sh"
    args = ["bash", str(script), str(tmp_path), "--name", "Demo", "--android-package", "com.demo"]
    for _ in range(2):
        subprocess.run(args, check=True, capture_output=True)

    servers = json.loads((tmp_path / ".mcp.json").read_text())["mcpServers"]
    assert set(servers) == {"other", "phone-harness"}
    settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    assert settings["enabledMcpjsonServers"] == ["phone-harness"]
    assert settings["permissions"]["allow"] == ["mcp__phone-harness__phone_doctor"]
    claude_md = (tmp_path / "CLAUDE.md").read_text()
    assert claude_md.startswith("# Existing\n")
    assert claude_md.count("<!-- phone-harness:begin -->") == 1
    profile = (tmp_path / ".claude" / "phone-app.md").read_text()
    assert "com.demo" in profile and "__" not in profile
