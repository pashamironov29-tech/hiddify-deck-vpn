"""Decky backend: toggle the hiddify-tun systemd unit from Game Mode.

systemctl, ip, and journalctl are executed with Decky's LD_LIBRARY_PATH
removed. That path points at Decky's OpenSSL and makes those binaries fail
with an OPENSSL_3.4.0 version mismatch. HiddifyCli itself still gets its
libraries from run.sh.
"""

import asyncio
import logging
import os
import subprocess

LOG_PATH = "/tmp/hiddify-tun-decky.log"
UNIT = "hiddify-tun.service"

# Same budgets the toggle already used: 40 * 0.25s = 10s up, 20 * 0.25s = 5s down.
# The subprocess cap sits above the unit's TimeoutStopSec (15s).
POLL_SECONDS = 0.25
UP_POLLS = 40
DOWN_POLLS = 20
COMMAND_TIMEOUT = 30
MAX_ERROR_CHARS = 400

# systemctl is-active prints one of these and exits 0 only for "active".
# inactive/failed are exit 3; a missing unit is often "inactive" or "unknown".
KNOWN_STATES = frozenset({
    "active",
    "reloading",
    "inactive",
    "failed",
    "activating",
    "deactivating",
    "maintenance",
    "unknown",
})
# tun0 already gone, but the unit is still the running VPN.
_STILL_RUNNING = frozenset({"active", "activating", "reloading"})
_STRIP_ENV = ("LD_LIBRARY_PATH", "LD_PRELOAD")


class CommandError(RuntimeError):
    """systemctl/ip/journalctl could not be executed."""


def _configure_logging():
    log = logging.getLogger("hiddify_tun")
    log.setLevel(logging.INFO)
    log.propagate = False
    if log.handlers:
        return log
    try:
        handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    except OSError:
        handler = logging.StreamHandler()
    else:
        try:
            os.chmod(LOG_PATH, 0o600)
        except OSError:
            pass
    handler.setFormatter(logging.Formatter("[Hiddify] %(asctime)s %(levelname)s %(message)s"))
    log.addHandler(handler)
    return log


logger = _configure_logging()


def sanitized_env():
    """Copy the process environment without Decky's library overrides."""
    env = {key: value for key, value in os.environ.items() if key not in _STRIP_ENV}
    env["PATH"] = "/usr/bin:/bin:/usr/sbin:/sbin"
    return env


def run(cmd):
    logger.info("RUN: %s", " ".join(cmd))
    try:
        return subprocess.run(
            cmd,
            text=True,
            capture_output=True,
            env=sanitized_env(),
            timeout=COMMAND_TIMEOUT,
            stdin=subprocess.DEVNULL,
            shell=False,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired as exc:
        logger.error("timeout after %ss: %s", COMMAND_TIMEOUT, cmd)
        raise CommandError(f"timeout: {' '.join(cmd)}") from exc
    except OSError as exc:
        logger.error("exec failed: %s", exc)
        raise CommandError(str(exc)) from exc


async def arun(cmd):
    # systemctl stop can block for TimeoutStopSec; don't freeze the plugin loop.
    return await asyncio.to_thread(run, cmd)


def parse_service_state(result):
    """Map `systemctl is-active` output to a single state token.

    A non-zero exit is normal for inactive/failed/unknown. Only empty output
    or a non-state error message becomes "unknown". When a known token is
    followed by an extra line, the token still wins.
    """
    stdout = result.stdout or ""
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    if lines and lines[0] in KNOWN_STATES:
        return lines[0]
    state = stdout.strip()
    if state in KNOWN_STATES:
        return state
    if not state or result.returncode != 0:
        return "unknown"
    return state


def _clip(text):
    text = (text or "").strip()
    if len(text) > MAX_ERROR_CHARS:
        return text[:MAX_ERROR_CHARS]
    return text


def _failure_text(result, fallback):
    err = _clip(result.stderr) or _clip(result.stdout)
    return err or fallback


def _status_error(result, state):
    """Diagnostic for a failed is-active command, not for inactive/failed units."""
    if state != "unknown":
        return ""
    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    if stdout in {"", "unknown"} and not stderr:
        return ""
    if result.returncode == 0 and not stderr:
        return ""
    err = stderr or (stdout if stdout not in KNOWN_STATES else "")
    if err and err != "unknown":
        return _clip(err)
    return ""


def _journal_error(result):
    lines = [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]
    if not lines or lines[-1] == "-- No entries --":
        return "tun0 не появился"
    return _clip(lines[-1])


async def tun_up():
    # Exit 0 means the tun0 link exists (the check this plugin already used).
    result = await arun(["/usr/sbin/ip", "link", "show", "tun0"])
    return result.returncode == 0


class Plugin:
    async def hiddify_status(self):
        try:
            active = await arun(["/usr/bin/systemctl", "is-active", UNIT])
            state = parse_service_state(active)
            up = await tun_up()
        except CommandError as exc:
            logger.error("status failed: %s", exc)
            return {"enabled": False, "service": "unknown", "tun": False, "error": str(exc)}
        result = {"enabled": bool(state == "active" and up), "service": state, "tun": up}
        err = _status_error(active, state)
        if err:
            result["error"] = err
        return result

    async def hiddify_up(self):
        try:
            started = await arun(["/usr/bin/systemctl", "start", UNIT])
        except CommandError as exc:
            logger.error("start failed: %s", exc)
            return {"ok": False, "error": str(exc)}
        if started.returncode != 0:
            err = _failure_text(started, "systemctl start failed")
            logger.error("start failed: %s", err)
            return {"ok": False, "error": err}
        try:
            for _ in range(UP_POLLS):
                if await tun_up():
                    state = parse_service_state(
                        await arun(["/usr/bin/systemctl", "is-active", UNIT])
                    )
                    if state == "active":
                        return {"ok": True, "error": ""}
                await asyncio.sleep(POLL_SECONDS)
            journal = await arun(["/usr/bin/journalctl", "-u", UNIT, "-n", "15", "--no-pager"])
        except CommandError as exc:
            logger.error("tun missing: %s", exc)
            return {"ok": False, "error": str(exc)}
        err = _journal_error(journal)
        logger.error("tun missing: %s", err)
        return {"ok": False, "error": err}

    async def hiddify_down(self):
        try:
            stopped = await arun(["/usr/bin/systemctl", "stop", UNIT])
        except CommandError as exc:
            logger.error("stop failed: %s", exc)
            return {"ok": False, "error": str(exc)}
        if stopped.returncode != 0:
            err = _failure_text(stopped, "systemctl stop failed")
            logger.error("stop failed: %s", err)
            return {"ok": False, "error": err}
        last_up = True
        last_state = "unknown"
        try:
            for _ in range(DOWN_POLLS):
                last_up = await tun_up()
                active = await arun(["/usr/bin/systemctl", "is-active", UNIT])
                last_state = parse_service_state(active)
                # A dbus failure is not "tun is down". inactive/failed have no stderr.
                err = _status_error(active, last_state)
                if err:
                    logger.error("stop check failed: %s", err)
                    return {"ok": False, "error": err}
                # A clean stop deletes tun0 and leaves the unit inactive/failed.
                # deactivating + tun already gone matches the previous success path.
                if not last_up and last_state not in _STILL_RUNNING:
                    return {"ok": True, "error": ""}
                await asyncio.sleep(POLL_SECONDS)
        except CommandError as exc:
            logger.error("stop check failed: %s", exc)
            return {"ok": False, "error": str(exc)}
        if last_up:
            return {"ok": False, "error": "tun0 всё ещё поднят"}
        return {"ok": False, "error": f"служба не остановилась ({last_state})"}
