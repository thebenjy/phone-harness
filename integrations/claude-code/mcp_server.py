# /// script
# requires-python = ">=3.10"
# dependencies = ["mcp>=2.3,<3"]
# ///
"""phone-harness as an MCP server for Claude Code (or any MCP client).

Two tools:

- ``phone_exec(code)`` pipes a Python script to the ``phone-harness`` CLI, which runs it with
  the phone helpers pre-imported. stdout comes back as text; a screenshot printed during the
  call comes back as an image, so the model sees the phone without a separate file read.
- ``phone_doctor(platform)`` runs ``phone-harness doctor``.

The server holds no phone state. Each call is a fresh interpreter; the phone, the config in
``~/.phone-harness`` and the agent workspace persist. One script drives the phone at a time,
across every Claude session on this machine (a file lock, not a thread lock).

The child environment is this process's env minus ``*_API_KEY`` / ``*_TOKEN`` / ``*_SECRET``,
the same scrub the Hermes integration uses.

Run: ``uv run --script mcp_server.py`` (the inline metadata above pulls the MCP SDK), or the
``phone-harness-mcp`` launcher that ``setup-host.sh`` installs.
"""
from __future__ import annotations

import asyncio
import contextlib
import fcntl
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from mcp.server.mcpserver import Image, MCPServer

DEFAULT_TIMEOUT_S, MIN_TIMEOUT_S, MAX_TIMEOUT_S = 300, 5, 1800
LOCK_WAIT_S = 120
OUTPUT_CAP, STDERR_CAP = 50_000, 4_000
IMAGE_MAX_PX = 1568  # long edge; larger images cost tokens without adding detail
_SECRET_SUFFIXES = ("_API_KEY", "_TOKEN", "_SECRET")
_LOCK_PATH = Path.home() / ".phone-harness" / ".mcp-phone.lock"

# Absolute PNG / JPEG / WebP paths, as screenshot() prints them.
_IMAGE_PATH = re.compile(r"(?<![\w.])(/[^\s\"']+?\.(?:png|jpe?g|webp))(?![\w.])", re.IGNORECASE)

INSTRUCTIONS = """\
Drives the user's real phone (Android over adb, iPhone through macOS iPhone Mirroring, or a
Phone Harness Cloud phone). The full helper reference is the phone-harness skill, or
`phone-harness skill` in a shell; read it before the first phone_exec of a session.

Working loop: ensure_device() -> screen() to read text with tap coordinates -> tap / type_text /
swipe -> screen() or screenshot() to verify. Each phone_exec is a fresh interpreter.

If the repo has a .claude/phone-app.md, read it first: it names the app under test, its bundle
id / package, and how to build and install it.

Ask the user before anything outward-facing or hard to undo (sending, posting, buying,
deleting, changing settings). Never type passwords, PINs or 2FA codes. Connecting the phone is
the user's job: relay phone_doctor's message and wait, do not retry-loop."""

mcp = MCPServer("phone-harness", instructions=INSTRUCTIONS)


def _cli() -> list[str] | None:
    """argv for the phone-harness CLI. PHONE_HARNESS_CLI overrides PATH lookup."""
    override = os.environ.get("PHONE_HARNESS_CLI", "").strip()
    if override:
        return override.split()
    found = shutil.which("phone-harness")
    return [found] if found else None


def _child_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.upper().endswith(_SECRET_SUFFIXES)}
    env.setdefault("PH_CLIENT", "claude-code-mcp")
    env["PHONE_HARNESS_NO_UPDATE_CHECK"] = "1"
    return env


def _clamp_timeout(value: int | None) -> int:
    try:
        return max(MIN_TIMEOUT_S, min(int(value or DEFAULT_TIMEOUT_S), MAX_TIMEOUT_S))
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT_S


class PhoneBusy(Exception):
    pass


@contextlib.contextmanager
def _phone_lock(wait_s: float):
    """One script on the phone at a time, across processes. Raises PhoneBusy after wait_s."""
    _LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_LOCK_PATH, "a+") as fh:
        deadline = time.monotonic() + wait_s
        while True:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise PhoneBusy from None
                time.sleep(0.25)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def find_screenshot(stdout: str, since: float) -> str | None:
    """Last absolute image path in stdout that exists and was written during this call."""
    for path in reversed(_IMAGE_PATH.findall(stdout or "")):
        try:
            if os.path.isfile(path) and os.path.getmtime(path) >= since - 1:
                return path
        except OSError:
            continue
    return None


def _image_for_model(path: str) -> Image:
    """The screenshot, shrunk to IMAGE_MAX_PX as JPEG with macOS sips when available."""
    sips = shutil.which("sips") if sys.platform == "darwin" else None
    if sips:
        fd, out = tempfile.mkstemp(suffix=".jpg")
        os.close(fd)
        try:
            # sips -Z also enlarges, so only pass it for images over the limit.
            dims = subprocess.run([sips, "-g", "pixelWidth", "-g", "pixelHeight", path],
                                  capture_output=True, text=True, timeout=30, check=False)
            sizes = [int(n) for n in re.findall(r"pixel(?:Width|Height):\s*(\d+)", dims.stdout)]
            resize = ["-Z", str(IMAGE_MAX_PX)] if sizes and max(sizes) > IMAGE_MAX_PX else []
            proc = subprocess.run(
                [sips, *resize, "-s", "format", "jpeg", path, "--out", out],
                capture_output=True, timeout=30, check=False,
            )
            if proc.returncode == 0 and os.path.getsize(out) > 0:
                return Image(data=Path(out).read_bytes(), format="jpeg")
        except (OSError, subprocess.SubprocessError):
            pass
        finally:
            with contextlib.suppress(OSError):
                os.unlink(out)
    return Image(path=path)


def _run_cli(args: list[str], stdin: str | None, timeout: int,
             platform: str | None = None) -> tuple[int | None, str, str]:
    """Run the CLI in its own process group; kill the whole group on timeout."""
    cmd = _cli()
    if cmd is None:
        raise FileNotFoundError(
            "phone-harness is not on PATH. Run integrations/claude-code/setup-host.sh in the "
            "phone-harness checkout, or set PHONE_HARNESS_CLI.")
    env = _child_env()
    if platform:
        env["PHONE_HARNESS_PLATFORM"] = platform
    proc = subprocess.Popen(
        cmd + args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace", env=env, start_new_session=True,
    )
    try:
        out, err = proc.communicate(input=stdin, timeout=timeout)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(proc.pid, signal.SIGKILL)
        with contextlib.suppress(subprocess.TimeoutExpired):
            proc.communicate(timeout=10)
        return None, "", ""
    return proc.returncode, out or "", err or ""


def _exec_blocking(code: str, timeout: int, platform: str | None) -> list[str | Image]:
    if not code.strip():
        return ["No code provided. Start with: ensure_device(); print(screen_info())"]
    try:
        with _phone_lock(LOCK_WAIT_S):
            started = time.time()
            rc, out, err = _run_cli([], code, timeout, platform)
    except PhoneBusy:
        return [f"The phone is busy with another phone_exec script (waited {LOCK_WAIT_S}s). "
                "Try again when it finishes."]
    except OSError as e:
        return [f"Failed to launch phone-harness: {e}"]
    if rc is None:
        return [f"phone_exec timed out after {timeout}s. Split the work into smaller scripts "
                f"or raise timeout_s (max {MAX_TIMEOUT_S})."]

    text = f"exit_code: {rc}\n--- stdout ---\n{out[-OUTPUT_CAP:]}"
    if err.strip():
        text += f"\n--- stderr ---\n{err.strip()[-STDERR_CAP:]}"
    result: list[str | Image] = [text]
    shot = find_screenshot(out, started)
    if shot:
        result.append(_image_for_model(shot))
    return result


@mcp.tool()
async def phone_exec(code: str, timeout_s: int = DEFAULT_TIMEOUT_S,
                     platform: str | None = None) -> list[str | Image]:
    """Run a Python script against the user's phone with the phone-harness helpers pre-imported.

    print() whatever you need back. Each call is a fresh interpreter (variables do not persist);
    the phone keeps its state. Start with ensure_device(). screen() returns visible text boxes
    with tap-ready x/y; screenshot() prints the saved image path and that image is attached to
    this result. platform ("ios" or "android") overrides the configured default for this call.
    """
    return await asyncio.to_thread(_exec_blocking, code, _clamp_timeout(timeout_s), platform)


@mcp.tool()
async def phone_doctor(platform: str | None = None) -> str:
    """Check the phone connection chain (permissions, adb, mirroring, device state) and name the
    missing step. platform is "ios" or "android"; omitted checks the configured default."""
    args = ["doctor"] + ([platform] if platform else [])
    try:
        rc, out, err = await asyncio.to_thread(_run_cli, args, None, 120)
    except OSError as e:
        return f"Failed to launch phone-harness: {e}"
    if rc is None:
        return "phone-harness doctor timed out after 120s."
    return f"exit_code: {rc}\n{out}{err}".strip()


def main() -> None:
    mcp.run("stdio")


if __name__ == "__main__":
    main()
