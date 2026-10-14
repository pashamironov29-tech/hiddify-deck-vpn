import subprocess
import asyncio
import logging

logging.basicConfig(
    filename="/tmp/hiddify-tun-decky.log",
    format="[Hiddify] %(asctime)s %(levelname)s %(message)s",
    filemode="a",
    force=True,
)
logger = logging.getLogger()
logger.setLevel(logging.INFO)

UNIT = "hiddify-tun.service"


def run(cmd):
    logger.info("RUN: %s", " ".join(cmd))
    import os
    env = {k: v for k, v in os.environ.items() if k not in ('LD_LIBRARY_PATH', 'LD_PRELOAD')}
    env['PATH'] = '/usr/bin:/bin:/usr/sbin:/sbin'
    return subprocess.run(cmd, text=True, capture_output=True, env=env)


def tun_up():
    return run(["/usr/sbin/ip", "link", "show", "tun0"]).returncode == 0


class Plugin:
    async def hiddify_status(self):
        active = run(["/usr/bin/systemctl", "is-active", UNIT])
        state = active.stdout.strip()
        up = tun_up()
        return {"enabled": state == "active" and up, "service": state, "tun": up}

    async def hiddify_up(self):
        started = run(["/usr/bin/systemctl", "start", UNIT])
        if started.returncode != 0:
            err = (started.stderr or started.stdout).strip()
            logger.error("start failed: %s", err)
            return {"ok": False, "error": err or "systemctl start failed"}
        for _ in range(40):
            if tun_up() and run(["/usr/bin/systemctl", "is-active", UNIT]).stdout.strip() == "active":
                return {"ok": True, "error": ""}
            await asyncio.sleep(0.25)
        journal = run(["/usr/bin/journalctl", "-u", UNIT, "-n", "15", "--no-pager"])
        tail = (journal.stdout or "").strip().splitlines()
        err = tail[-1] if tail else "tun0 не появился"
        logger.error("tun missing: %s", err)
        return {"ok": False, "error": err}

    async def hiddify_down(self):
        stopped = run(["/usr/bin/systemctl", "stop", UNIT])
        if stopped.returncode != 0:
            err = (stopped.stderr or stopped.stdout).strip()
            logger.error("stop failed: %s", err)
            return {"ok": False, "error": err or "systemctl stop failed"}
        for _ in range(20):
            if not tun_up():
                return {"ok": True, "error": ""}
            await asyncio.sleep(0.25)
        return {"ok": False, "error": "tun0 всё ещё поднят"}
