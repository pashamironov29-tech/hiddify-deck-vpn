"""Locks install/docs behavior that the runtime tests cannot see."""

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_install_stops_the_unit_before_replacing_files():
    text = (ROOT / "install.sh").read_text(encoding="utf-8")
    stop = text.index("systemctl stop hiddify-tun")
    kill = text.index("pkill -f HiddifyCli")
    copy = text.index("hiddify-tun/config.json")
    assert stop < kill < copy
    assert "systemctl reset-failed hiddify-tun" in text
    assert "plugin/dist/index.js" in text
    assert "/home/deck" in text


def test_run_sh_keeps_the_hiddify_library_path():
    text = (ROOT / "run.sh").read_text(encoding="utf-8")
    assert "LD_LIBRARY_PATH=" in text
    assert "HiddifyCli" in text
    assert "config.json" in text


def test_plugin_json_requests_root():
    meta = json.loads((ROOT / "plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert meta["name"] == "Hiddify"
    assert "root" in meta["flags"]


def test_readme_documents_tests_uninstall_and_ci():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "actions/workflows/ci.yml/badge.svg" in readme
    assert "python -m pip install -r requirements-dev.txt" in readme
    assert "ruff check plugin tests" in readme
    assert "pytest" in readme
    assert "node --test tests/frontend.test.mjs" in readme
    assert "daemon-reload" in readme
    assert "~/.local/share/hiddify-tun" in readme
    assert "deck" in readme


def test_shell_scripts_are_valid_bash():
    subprocess.run(["bash", "-n", str(ROOT / "install.sh")], check=True)
    subprocess.run(["bash", "-n", str(ROOT / "run.sh")], check=True)


def test_frontend_bundle_stays_a_legacy_iife():
    src = (ROOT / "plugin" / "dist" / "index.js").read_text(encoding="utf-8")
    assert src.startswith("(function (DFL, React) {")
    assert src.rstrip().endswith("})(DFL, SP_REACT);")
    assert "export " not in src
    assert "import " not in src
    assert "hiddify_status" in src
    assert "hiddify_up" in src
    assert "hiddify_down" in src
