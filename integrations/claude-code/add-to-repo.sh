#!/bin/bash
# Per repo: let Claude Code drive the phone app that lives in this repo.
#
# Writes (idempotent, merges with what is there):
#   .mcp.json               phone-harness MCP server -> phone-harness-mcp launcher
#   .claude/settings.json   approves that server; auto-allows phone_doctor (phone_exec still asks)
#   .claude/phone-app.md    app profile: ids, build/install, test accounts (only if missing)
#   CLAUDE.md               a short marked block pointing at the above
#
# Usage:
#   add-to-repo.sh REPO [--name "App Name"] [--ios-bundle-id ID] [--android-package PKG]
#                       [--platform android|ios] [--no-profile]
#
# Run setup-host.sh once per machine first. Bash 3.2 compatible.
set -eu

HERE="$(cd "$(dirname "$0")" && pwd)"

usage() { sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

[ $# -ge 1 ] || usage 1
case "$1" in -h|--help) usage 0 ;; esac
TARGET="$(cd "$1" && pwd)"; shift

APP_NAME="TODO"; IOS_ID="TODO"; ANDROID_PKG="TODO"; PLATFORM="android"; PROFILE=1
while [ $# -gt 0 ]; do
    case "$1" in
        --name) APP_NAME="$2"; shift 2 ;;
        --ios-bundle-id) IOS_ID="$2"; shift 2 ;;
        --android-package) ANDROID_PKG="$2"; shift 2 ;;
        --platform) PLATFORM="$2"; shift 2 ;;
        --no-profile) PROFILE=0; shift ;;
        -h|--help) usage 0 ;;
        *) echo "unknown option: $1" >&2; usage 1 ;;
    esac
done
case "$PLATFORM" in android|ios) ;; *) echo "--platform must be android or ios" >&2; exit 1 ;; esac

command -v phone-harness-mcp >/dev/null 2>&1 || \
    echo "WARNING: phone-harness-mcp not on PATH; run ${HERE}/setup-host.sh first." >&2

mkdir -p "${TARGET}/.claude"

echo "==> ${TARGET}/.mcp.json and .claude/settings.json"
python3 - "${TARGET}" <<'PY'
import json, sys
from pathlib import Path

root = Path(sys.argv[1])

def load(p):
    if p.exists() and p.read_text().strip():
        return json.loads(p.read_text())
    return {}

def save(p, data):
    p.write_text(json.dumps(data, indent=2) + "\n")

mcp_path = root / ".mcp.json"
mcp = load(mcp_path)
mcp.setdefault("mcpServers", {})["phone-harness"] = {"command": "phone-harness-mcp", "args": []}
save(mcp_path, mcp)

settings_path = root / ".claude" / "settings.json"
settings = load(settings_path)
enabled = settings.setdefault("enabledMcpjsonServers", [])
if "phone-harness" not in enabled:
    enabled.append("phone-harness")
allow = settings.setdefault("permissions", {}).setdefault("allow", [])
if "mcp__phone-harness__phone_doctor" not in allow:
    allow.append("mcp__phone-harness__phone_doctor")
save(settings_path, settings)
PY

PROFILE_PATH="${TARGET}/.claude/phone-app.md"
if [ "$PROFILE" -eq 1 ]; then
    if [ -f "${PROFILE_PATH}" ]; then
        echo "==> ${PROFILE_PATH} exists; left as is"
    else
        echo "==> ${PROFILE_PATH}"
        python3 - "${HERE}/templates/phone-app.md" "${PROFILE_PATH}" \
            "${APP_NAME}" "${IOS_ID}" "${ANDROID_PKG}" "${PLATFORM}" <<'PY'
import sys
src, dst, name, ios, pkg, platform = sys.argv[1:]
text = open(src).read()
for key, value in (("__APP_NAME__", name), ("__IOS_BUNDLE_ID__", ios),
                   ("__ANDROID_PACKAGE__", pkg), ("__PLATFORM__", platform)):
    text = text.replace(key, value)
open(dst, "w").write(text)
PY
    fi
fi

CLAUDE_MD="${TARGET}/CLAUDE.md"
MARK_BEGIN="<!-- phone-harness:begin -->"
if [ -f "${CLAUDE_MD}" ] && grep -qF "${MARK_BEGIN}" "${CLAUDE_MD}"; then
    echo "==> ${CLAUDE_MD} already has the phone-harness block"
else
    echo "==> ${CLAUDE_MD} (appending phone-harness block)"
    {
        [ -f "${CLAUDE_MD}" ] && [ -s "${CLAUDE_MD}" ] && echo
        echo "${MARK_BEGIN}"
        echo "## Phone control (phone-harness)"
        echo
        echo "- Drive the real phone with the \`phone-harness\` MCP server: \`phone_exec\` runs a Python"
        echo "  script with the helpers pre-imported, \`phone_doctor\` checks the connection. Helper"
        echo "  reference: the phone-harness skill (\`phone-harness skill\`)."
        if [ "$PROFILE" -eq 1 ]; then
            echo "- The app under test, its ids and how to build/install it: \`.claude/phone-app.md\`."
            echo "  Read it before the first \`phone_exec\`."
        fi
        echo "- Ask before anything outward-facing or hard to undo. Never type passwords, PINs or 2FA codes."
        echo "<!-- phone-harness:end -->"
    } >> "${CLAUDE_MD}"
fi

echo
echo "Done. Restart Claude Code in ${TARGET} (or /mcp) to connect the phone-harness server."
