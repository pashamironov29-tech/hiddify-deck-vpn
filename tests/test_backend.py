"""Backend tests. systemctl and ip are mocked; nothing here touches a real unit."""

import asyncio
import os
import subprocess

import pytest

import main

UNIT = main.UNIT


def cp(rc=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


def cmd_key(cmd):
    if cmd[0].endswith("/ip"):
        return "ip"
    if cmd[0].endswith("/journalctl"):
        return "journalctl"
    if "is-active" in cmd:
        return "is-active"
    if "start" in cmd:
        return "start"
    if "stop" in cmd:
        return "stop"
    raise AssertionError(cmd)


@pytest.fixture(autouse=True)
def fast_sleep(monkeypatch):
    slept = []

    async def fake_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr(main.asyncio, "sleep", fake_sleep)
    return slept


def install_subprocess(monkeypatch, handler):
    def fake_run(cmd, **kwargs):
        return handler(list(cmd), kwargs)

    monkeypatch.setattr(main.subprocess, "run", fake_run)


def run_plugin(coro):
    return asyncio.run(coro)


class Script:
    """Queue of (cmd key, CompletedProcess or Exception) in call order."""

    def __init__(self, steps):
        self.steps = list(steps)
        self.calls = []
        self.envs = []

    def __call__(self, cmd, kwargs):
        self.calls.append(cmd)
        self.envs.append(kwargs.get("env"))
        if not self.steps:
            raise AssertionError(f"unexpected extra command: {cmd}")
        key, result = self.steps.pop(0)
        assert cmd_key(cmd) == key, cmd
        if isinstance(result, Exception):
            raise result
        return result


def test_poll_budget_is_unchanged():
    assert main.UP_POLLS == 40
    assert main.DOWN_POLLS == 20
    assert main.POLL_SECONDS == 0.25
    assert main.COMMAND_TIMEOUT == 30


def test_sanitized_env_strips_decky_libs_without_mutating_process(monkeypatch):
    monkeypatch.setenv("LD_LIBRARY_PATH", "/home/deck/homebrew/services/PluginLoader/lib")
    monkeypatch.setenv("LD_PRELOAD", "/tmp/libpreload.so")
    monkeypatch.setenv("HOME", "/home/deck")
    monkeypatch.setenv("DBUS_SYSTEM_BUS_ADDRESS", "unix:path=/run/dbus/system_bus_socket")

    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["kwargs"] = kwargs
        return cp(0, "active\n")

    monkeypatch.setattr(main.subprocess, "run", fake_run)
    result = main.run(["/usr/bin/systemctl", "is-active", UNIT])

    env = seen["kwargs"]["env"]
    assert "LD_LIBRARY_PATH" not in env
    assert "LD_PRELOAD" not in env
    assert env["PATH"] == "/usr/bin:/bin:/usr/sbin:/sbin"
    assert env["HOME"] == "/home/deck"
    assert env["DBUS_SYSTEM_BUS_ADDRESS"].endswith("system_bus_socket")
    assert os.environ["LD_LIBRARY_PATH"].endswith("PluginLoader/lib")
    assert os.environ["LD_PRELOAD"] == "/tmp/libpreload.so"
    assert seen["kwargs"]["shell"] is False
    assert seen["kwargs"]["timeout"] == main.COMMAND_TIMEOUT
    assert seen["kwargs"]["stdin"] is subprocess.DEVNULL
    assert seen["cmd"] == ["/usr/bin/systemctl", "is-active", UNIT]
    assert result.returncode == 0


def test_run_timeout_and_missing_binary_become_command_errors(monkeypatch):
    def raise_timeout(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=kwargs.get("timeout", 30))

    monkeypatch.setattr(main.subprocess, "run", raise_timeout)
    with pytest.raises(main.CommandError, match="timeout: /usr/bin/systemctl"):
        main.run(["/usr/bin/systemctl", "is-active", UNIT])

    def raise_oserror(cmd, **kwargs):
        raise FileNotFoundError(2, "No such file or directory", cmd[0])

    monkeypatch.setattr(main.subprocess, "run", raise_oserror)
    with pytest.raises(main.CommandError, match="No such file or directory"):
        main.run(["/usr/sbin/ip", "link", "show", "tun0"])


@pytest.mark.parametrize(
    ("stdout", "rc", "expected"),
    [
        ("active\n", 0, "active"),
        ("  active\r\n", 0, "active"),
        ("inactive\n", 3, "inactive"),
        ("failed\n", 3, "failed"),
        ("unknown\n", 4, "unknown"),
        ("activating\n", 3, "activating"),
        ("deactivating\n", 3, "deactivating"),
        ("reloading\n", 0, "reloading"),
        ("maintenance\n", 3, "maintenance"),
        ("active\nextra warning\n", 0, "active"),
        ("", 1, "unknown"),
        ("   \n", 1, "unknown"),
        ("Failed to connect to bus: No such file or directory\n", 1, "unknown"),
        ("weird-but-clean", 0, "weird-but-clean"),
    ],
)
def test_parse_service_state(stdout, rc, expected):
    assert main.parse_service_state(cp(rc, stdout)) == expected


@pytest.mark.parametrize(
    ("state", "tun_rc", "enabled", "tun"),
    [
        ("active", 0, True, True),
        ("active", 1, False, False),
        ("inactive", 0, False, True),
        ("inactive", 1, False, False),
        ("failed", 0, False, True),
        ("failed", 1, False, False),
        ("unknown", 1, False, False),
        ("activating", 0, False, True),
    ],
)
def test_status_matrix(monkeypatch, state, tun_rc, enabled, tun):
    script = Script([
        ("is-active", cp(0 if state == "active" else 3, f"{state}\n")),
        ("ip", cp(tun_rc, "")),
    ])
    install_subprocess(monkeypatch, script)
    result = run_plugin(main.Plugin().hiddify_status())
    assert result == {"enabled": enabled, "service": state, "tun": tun}
    assert "error" not in result


def test_status_active_strips_ld_library_path(monkeypatch):
    monkeypatch.setenv("LD_LIBRARY_PATH", "/opt/decky/lib")
    script = Script([
        ("is-active", cp(0, "active\n")),
        ("ip", cp(0, "tun0")),
    ])
    install_subprocess(monkeypatch, script)
    result = run_plugin(main.Plugin().hiddify_status())
    assert result["enabled"] is True
    assert script.envs
    assert all(env is not None and "LD_LIBRARY_PATH" not in env for env in script.envs)


def test_status_dbus_error_is_reported_and_not_treated_as_inactive(monkeypatch):
    script = Script([
        ("is-active", cp(1, "", "Failed to connect to bus: No such file or directory")),
        ("ip", cp(1, "", 'Device "tun0" does not exist.')),
    ])
    install_subprocess(monkeypatch, script)
    result = run_plugin(main.Plugin().hiddify_status())
    assert result["enabled"] is False
    assert result["service"] == "unknown"
    assert result["tun"] is False
    assert "Failed to connect to bus" in result["error"]


def test_status_missing_unit_without_stderr_stays_unknown(monkeypatch):
    script = Script([
        ("is-active", cp(4, "unknown\n", "")),
        ("ip", cp(1, "")),
    ])
    install_subprocess(monkeypatch, script)
    result = run_plugin(main.Plugin().hiddify_status())
    assert result == {"enabled": False, "service": "unknown", "tun": False}


def test_status_command_timeout(monkeypatch):
    script = Script([
        ("is-active", subprocess.TimeoutExpired(cmd=["/usr/bin/systemctl"], timeout=30)),
    ])
    install_subprocess(monkeypatch, script)
    result = run_plugin(main.Plugin().hiddify_status())
    assert result["enabled"] is False
    assert result["service"] == "unknown"
    assert result["tun"] is False
    assert result["error"].startswith("timeout:")


def test_up_succeeds_when_tun_and_unit_are_already_active(monkeypatch, fast_sleep):
    script = Script([
        ("start", cp(0, "")),
        ("ip", cp(0, "")),
        ("is-active", cp(0, "active\n")),
    ])
    install_subprocess(monkeypatch, script)
    result = run_plugin(main.Plugin().hiddify_up())
    assert result == {"ok": True, "error": ""}
    assert fast_sleep == []
    assert script.calls[0] == ["/usr/bin/systemctl", "start", UNIT]


def test_up_waits_until_tun_appears(monkeypatch, fast_sleep):
    script = Script([
        ("start", cp(0, "")),
        ("ip", cp(1, "")),
        ("ip", cp(0, "")),
        ("is-active", cp(0, "active\n")),
    ])
    install_subprocess(monkeypatch, script)
    result = run_plugin(main.Plugin().hiddify_up())
    assert result == {"ok": True, "error": ""}
    assert fast_sleep == [0.25]


def test_up_start_failure_prefers_stderr_then_stdout_then_fallback(monkeypatch):
    cases = [
        (cp(1, "stdout-err", "stderr-err"), "stderr-err"),
        (cp(1, "stdout-err", ""), "stdout-err"),
        (cp(1, "  ", "  "), "systemctl start failed"),
    ]
    for result, expected in cases:
        script = Script([("start", result)])
        install_subprocess(monkeypatch, script)
        assert run_plugin(main.Plugin().hiddify_up()) == {"ok": False, "error": expected}


def test_up_reports_last_journal_line_when_tun_never_appears(monkeypatch, fast_sleep):
    steps = [("start", cp(0, ""))]
    steps += [("ip", cp(1, ""))] * main.UP_POLLS
    steps.append(("journalctl", cp(0, "older\nHiddifyCli: connection refused\n")))
    script = Script(steps)
    install_subprocess(monkeypatch, script)
    result = run_plugin(main.Plugin().hiddify_up())
    assert result == {"ok": False, "error": "HiddifyCli: connection refused"}
    assert fast_sleep == [0.25] * main.UP_POLLS
    journal = script.calls[-1]
    assert journal[0] == "/usr/bin/journalctl"
    assert "--no-pager" in journal
    assert UNIT in journal


def test_up_empty_journal_uses_fallback(monkeypatch):
    steps = [("start", cp(0, ""))]
    steps += [("ip", cp(1, ""))] * main.UP_POLLS
    steps.append(("journalctl", cp(0, "-- No entries --\n")))
    script = Script(steps)
    install_subprocess(monkeypatch, script)
    assert run_plugin(main.Plugin().hiddify_up()) == {"ok": False, "error": "tun0 не появился"}


def test_up_clips_a_huge_journal_line(monkeypatch):
    steps = [("start", cp(0, ""))]
    steps += [("ip", cp(1, ""))] * main.UP_POLLS
    steps.append(("journalctl", cp(0, ("y" * 500) + "\n")))
    script = Script(steps)
    install_subprocess(monkeypatch, script)
    err = run_plugin(main.Plugin().hiddify_up())["error"]
    assert err == "y" * main.MAX_ERROR_CHARS


def test_up_exec_error_on_start(monkeypatch):
    script = Script([
        ("start", FileNotFoundError(2, "No such file or directory", "/usr/bin/systemctl")),
    ])
    install_subprocess(monkeypatch, script)
    result = run_plugin(main.Plugin().hiddify_up())
    assert result["ok"] is False
    assert "No such file or directory" in result["error"]


def test_down_succeeds_when_tun_is_gone_and_unit_is_inactive(monkeypatch, fast_sleep):
    script = Script([
        ("stop", cp(0, "")),
        ("ip", cp(1, "")),
        ("is-active", cp(3, "inactive\n")),
    ])
    install_subprocess(monkeypatch, script)
    assert run_plugin(main.Plugin().hiddify_down()) == {"ok": True, "error": ""}
    assert fast_sleep == []
    assert script.calls[0] == ["/usr/bin/systemctl", "stop", UNIT]


def test_down_succeeds_if_tun_is_already_gone_while_deactivating(monkeypatch, fast_sleep):
    script = Script([
        ("stop", cp(0, "")),
        ("ip", cp(1, "")),
        ("is-active", cp(3, "deactivating\n")),
    ])
    install_subprocess(monkeypatch, script)
    assert run_plugin(main.Plugin().hiddify_down()) == {"ok": True, "error": ""}
    assert fast_sleep == []


def test_down_stop_failure(monkeypatch):
    script = Script([("stop", cp(1, "", "Access denied"))])
    install_subprocess(monkeypatch, script)
    assert run_plugin(main.Plugin().hiddify_down()) == {"ok": False, "error": "Access denied"}


def test_down_times_out_while_tun_stays_up(monkeypatch, fast_sleep):
    steps = [("stop", cp(0, ""))]
    steps += [("ip", cp(0, "")), ("is-active", cp(3, "inactive\n"))] * main.DOWN_POLLS
    script = Script(steps)
    install_subprocess(monkeypatch, script)
    assert run_plugin(main.Plugin().hiddify_down()) == {"ok": False, "error": "tun0 всё ещё поднят"}
    assert fast_sleep == [0.25] * main.DOWN_POLLS


def test_down_does_not_succeed_when_tun_is_gone_but_unit_still_active(monkeypatch, fast_sleep):
    steps = [("stop", cp(0, ""))]
    steps += [("ip", cp(1, "")), ("is-active", cp(0, "active\n"))] * main.DOWN_POLLS
    script = Script(steps)
    install_subprocess(monkeypatch, script)
    result = run_plugin(main.Plugin().hiddify_down())
    assert result == {"ok": False, "error": "служба не остановилась (active)"}
    assert fast_sleep == [0.25] * main.DOWN_POLLS


def test_down_dbus_error_is_not_reported_as_success(monkeypatch):
    script = Script([
        ("stop", cp(0, "")),
        ("ip", cp(1, "")),
        ("is-active", cp(1, "", "Failed to connect to bus: No such file or directory")),
    ])
    install_subprocess(monkeypatch, script)
    result = run_plugin(main.Plugin().hiddify_down())
    assert result["ok"] is False
    assert "Failed to connect to bus" in result["error"]


def test_down_ip_timeout_is_not_reported_as_success(monkeypatch):
    script = Script([
        ("stop", cp(0, "")),
        ("ip", subprocess.TimeoutExpired(cmd=["/usr/sbin/ip"], timeout=30)),
    ])
    install_subprocess(monkeypatch, script)
    result = run_plugin(main.Plugin().hiddify_down())
    assert result["ok"] is False
    assert "timeout" in result["error"]
    assert result["error"] != "tun0 всё ещё поднят"
