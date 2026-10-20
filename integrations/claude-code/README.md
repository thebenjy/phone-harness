# phone-harness for Claude Code

Lets Claude Code drive a phone from any repo that holds a phone app: an Android over adb, an
iPhone through macOS iPhone Mirroring (macOS 15+), or a Phone Harness Cloud phone.

Three layers, each installed once in the place it belongs:

| Layer | Where | Installed by |
| --- | --- | --- |
| `phone-harness` CLI (editable, from this checkout) | `~/.local/bin/phone-harness` | `setup-host.sh` |
| MCP launcher (stdio server, `mcp_server.py`) | `~/.local/bin/phone-harness-mcp` | `setup-host.sh` |
| Skill: helper reference, `phone-harness skill` | `~/.claude/skills/phone-harness/` | `setup-host.sh` |
| MCP config + app profile + CLAUDE.md pointer | each app repo | `add-to-repo.sh` |

The repo files name only `phone-harness-mcp`, with no machine paths, so they can be committed.
Anyone who runs `setup-host.sh` on their own machine gets the same setup.

## Per machine (once)

```bash
integrations/claude-code/setup-host.sh
phone-harness doctor android   # or ios; names the missing step
```

Re-run it after `git pull` in this checkout so the skill matches the code.

## Per app repo

```bash
integrations/claude-code/add-to-repo.sh ~/repos/my-app \
    --name "My App" --android-package com.example.myapp --ios-bundle-id com.example.myapp \
    --platform android
```

This writes the following, merging with any existing files, and is safe to re-run:

- `.mcp.json`: `{"mcpServers": {"phone-harness": {"command": "phone-harness-mcp"}}}`
- `.claude/settings.json`: approves that server and allows `phone_doctor` without a prompt.
  `phone_exec` still asks, because it taps a real phone. To skip that prompt in a repo, add
  `mcp__phone-harness__phone_exec` to `permissions.allow` there.
- `.claude/phone-app.md`: the app profile (ids, build/install commands, test accounts, flows),
  written only if it is missing. Fill in the TODOs; Claude reads it before driving the phone.
- `CLAUDE.md`: a short block between `<!-- phone-harness:begin/end -->` markers.

Restart Claude Code in that repo (or run `/mcp`) to connect.

## Tools

- `phone_exec(code, timeout_s=300, platform=None)`: runs `code` with the helpers pre-imported
  (`ensure_device`, `screen`, `tap`, `type_text`, `open_app`, `screenshot`, ...). It returns stdout
  and stderr; a screenshot printed during the call is attached as an image, downscaled to a
  1568 px long edge. Each call is a fresh interpreter. Only one script drives the phone at a
  time across all sessions (lock file `~/.phone-harness/.mcp-phone.lock`).
- `phone_doctor(platform=None)`: `phone-harness doctor`.

Without the MCP server, the same scripts run from Bash with `phone-harness <<'PY' ... PY`.

## Notes

- The CLI is installed editable from this checkout, so agent-written helpers go to this
  checkout's `agent-workspace/` (see `src/phone_harness/workspace.py`). Set `PH_AGENT_WORKSPACE`
  to put them elsewhere.
- Phone Harness collects anonymous telemetry by default: `phone-harness config set telemetry false`.
- The child process gets this environment minus `*_API_KEY`, `*_TOKEN` and `*_SECRET`.
