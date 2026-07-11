#!/usr/bin/env python3
"""End-to-end backend tests for Docker-Shell.

Requires a working Docker + Compose v2 installation; spins up a throwaway
alpine container in a temp directory, drives the backend through every
mount mode and tears everything down afterwards. No GUI is started
(customtkinter/tkinter are stubbed out).

Run:  python3 tests/test_e2e.py
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
from pathlib import Path

# ── Import the app headless ──────────────────────────────────────
_stub = types.ModuleType("customtkinter")
_stub.CTk = object
sys.modules["customtkinter"] = _stub
_tk = types.ModuleType("tkinter")
_tk.messagebox = types.ModuleType("tkinter.messagebox")
sys.modules["tkinter"] = _tk
sys.modules["tkinter.messagebox"] = _tk.messagebox

# Isolate the sacrificial folder AND the config into the test sandbox
_SANDBOX = tempfile.mkdtemp(prefix="docker_shell_test_")
os.environ["XDG_DATA_HOME"] = str(Path(_SANDBOX) / "xdg_data")
os.environ["XDG_CONFIG_HOME"] = str(Path(_SANDBOX) / "xdg_config")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import docker_shell as ds  # noqa: E402

PASSED = 0


def ok(label):
    global PASSED
    PASSED += 1
    print(f"  [{PASSED:2d}] {label}: OK")


def sh(cmd, cwd=None):
    return subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)


def main():
    if shutil.which("docker") is None or sh(["docker", "ps", "-q"]).returncode != 0:
        print("SKIP: docker not available")
        return 0

    proj = Path(_SANDBOX) / "proj"
    data = proj / "testdata"
    neu = proj / "newfolder"
    (data / "sub1").mkdir(parents=True)
    (data / "sub2").mkdir()
    neu.mkdir()
    (data / "file.txt").write_text("secret")
    (data / "sub1" / "a.txt").write_text("sub1-content")
    (neu / "new.txt").write_text("new-content")

    # compose.yaml (spec name, exercises the compose-file-variant support);
    # svc2 exists only for the network-scope test
    (proj / "compose.yaml").write_text(
        "services:\n"
        "  testsvc:\n"
        "    image: alpine:latest\n"
        "    command: sleep 3600\n"
        "    volumes:\n"
        f"      - {data}:/data\n"
        "  svc2:\n"
        "    image: alpine:latest\n"
        "    command: sleep 3600\n"
    )

    Path(ds.TEMP_LEER).mkdir(parents=True, exist_ok=True)
    b = ds.DockerBackend()

    r = sh(["docker", "compose", "up", "-d"], cwd=proj)
    assert r.returncode == 0, r.stderr

    def get_ctr(folder, service="testsvc"):
        ctrs = [c for c in b.scan_containers(str(folder))
                if not c["warning"] and c["compose_dir"] == str(proj)
                and c["service_name"] == service]
        assert ctrs, f"container for {folder} ({service}) not found"
        return ctrs[0]

    def apply_mode(folder, mode, ctr, ram=0):
        cfg = {"target_folder": str(folder), "mount_mode": mode,
               "ram_limit_gb": ram,
               "current_volumes": b.get_all_volumes(ctr["id"])}
        b.write_override(ctr["compose_dir"], ctr["service_name"], cfg)
        okup, err = b.apply_compose(ctr["compose_dir"])
        assert okup, f"apply({mode}) failed: {err}"

    def status(folder, ctr):
        return b.get_status(ctr["id"], str(folder),
                            ctr["compose_dir"], ctr["service_name"])

    def exec_in(ctr, cmd):
        r = sh(["docker", "exec", ctr["id"]] + cmd)
        return r.returncode, r.stdout.strip()

    try:
        # compose.yaml variant + dest resolution
        ctr = get_ctr(data)
        assert ds.find_compose_file(proj).name == "compose.yaml"
        assert b.resolve_container_dest(str(proj), "testsvc", str(data)) == "/data"
        ok("compose.yaml found + container dest resolved")

        # initial RW state
        st = status(data, ctr)
        assert st["mounts"] and not st["mounts"][0]["masked"]
        assert exec_in(ctr, ["cat", "/data/file.txt"]) == (0, "secret")
        ok("initial RW state")

        # mask
        apply_mode(data, "masked", ctr)
        ctr = get_ctr(data)  # new ID after recreate; also checks scan filter
        st = status(data, ctr)
        assert st["mounts"][0]["masked"], st
        assert exec_in(ctr, ["ls", "/data"]) == (0, "")
        assert (ds.override_path_for(proj / "compose.yaml")
                == proj / "compose.override.yaml")
        assert (proj / "compose.override.yaml").exists()
        ok("mask (data hidden, status detected, override name matches base)")

        # masked -> RW (the core regression case)
        apply_mode(data, "rw", ctr)
        ctr = get_ctr(data)
        st = status(data, ctr)
        assert not st["mounts"][0]["masked"], st
        assert exec_in(ctr, ["cat", "/data/file.txt"]) == (0, "secret")
        ok("masked -> RW switch")

        # read-only
        apply_mode(data, "ro", ctr)
        ctr = get_ctr(data)
        assert status(data, ctr)["mounts"][0]["mode"] == "ro"
        assert exec_in(ctr, ["touch", "/data/x"])[0] != 0
        ok("read-only blocks writes")

        # main folder only
        apply_mode(data, "main_only", ctr)
        ctr = get_ctr(data)
        st = status(data, ctr)
        main_m = [m for m in st["mounts"] if m["dest"] == "/data"][0]
        subs = [m for m in st["mounts"] if m["masked"]]
        assert main_m["mode"] == "ro" and len(subs) == 2, st
        assert exec_in(ctr, ["ls", "/data/sub1"]) == (0, "")
        assert "file.txt" in exec_in(ctr, ["ls", "/data"])[1]
        ok("main folder only (RO + subdirs masked)")

        # add a brand-new folder (container path = host path)
        ctr_neu = get_ctr(neu)
        assert ctr_neu["new_mount"] is True
        apply_mode(neu, "rw", ctr_neu)
        ctr = get_ctr(neu)
        assert exec_in(ctr, ["cat", f"{neu}/new.txt"]) == (0, "new-content")
        st = status(neu, ctr)
        assert st["mounts"] and not st["mounts"][0]["masked"]
        ok("new folder added at host path")

        # mask/unmask the new folder (host-path mapping stays stable)
        apply_mode(neu, "masked", ctr)
        ctr = get_ctr(neu)
        assert exec_in(ctr, ["ls", str(neu)]) == (0, "")
        apply_mode(neu, "rw", ctr)
        ctr = get_ctr(neu)
        assert exec_in(ctr, ["cat", f"{neu}/new.txt"]) == (0, "new-content")
        ok("new folder mask -> unmask")

        # network isolation on/off (with backup)
        b.edit_network_in_main(str(proj), enable_network=False)
        okup, err = b.apply_compose(str(proj)); assert okup, err
        ctr = get_ctr(data)
        assert status(data, ctr)["is_isolated"]
        b.edit_network_in_main(str(proj), enable_network=True)
        okup, err = b.apply_compose(str(proj)); assert okup, err
        ctr = get_ctr(data)
        assert not status(data, ctr)["is_isolated"]
        assert b._backup_path(str(proj)).exists()
        ok("network isolation on/off + backup")

        # RAM limit
        apply_mode(data, "rw", ctr, ram=2)
        ctr = get_ctr(data)
        assert status(data, ctr)["memory_gb"] == 2
        ok("RAM limit 2 GB")

        # override content: user + logging, no invalid keys
        import yaml
        ov = yaml.safe_load((proj / "compose.override.yaml").read_text())
        svc = ov["services"]["testsvc"]
        assert ":" in svc["user"]
        assert svc["logging"]["driver"] == "json-file"
        assert "log_driver" not in svc
        ok("override content (user, logging)")

        # reset
        okup, err = b.reset_compose(str(proj)); assert okup, err
        assert not (proj / "compose.override.yaml").exists()
        ok("reset (override deleted, main compose restored)")

        # inherited rights: subfolder of a mounted volume has no own mount,
        # but must NOT report "not mounted" (banner bug)
        ctr = get_ctr(data)
        st = status(data / "sub1", ctr)
        assert st["mounts"], "subfolder wrongly reported as not mounted"
        assert st["mounts"][0]["inherited"] is True
        assert st["mounts"][0]["masked"] is False
        ok("inherited rights via parent mount (no false banner)")

        # preset naming for added folders + x-docker-shell mapping keeps the
        # container path resolvable across mask/unmask
        neu2 = proj / "presetfolder"
        neu2.mkdir()
        (neu2 / "p.txt").write_text("preset-content")
        ds._CFG["add_new_mode"] = "preset"
        ds._CFG["add_new_preset"] = "/mnt/{name}"
        try:
            ctr = get_ctr(neu2)
            assert ctr["new_mount"] is True
            apply_mode(neu2, "rw", ctr)
            ctr = get_ctr(neu2)
            assert exec_in(ctr, ["cat", "/mnt/presetfolder/p.txt"]) == (0, "preset-content")
            import yaml as _y
            ov = _y.safe_load((proj / "compose.override.yaml").read_text())
            assert ov["x-docker-shell"]["mounts"][str(neu2)] == "/mnt/presetfolder"
            apply_mode(neu2, "masked", ctr)
            ctr = get_ctr(neu2)  # must still be resolvable while masked
            st = status(neu2, ctr)
            assert st["mounts"] and st["mounts"][0]["masked"], st
            apply_mode(neu2, "rw", ctr)
            ctr = get_ctr(neu2)
            assert exec_in(ctr, ["cat", "/mnt/presetfolder/p.txt"]) == (0, "preset-content")
            okup, err = b.remove_share(str(proj), "testsvc", str(neu2))
            assert okup, err
            ov = _y.safe_load((proj / "compose.override.yaml").read_text())
            assert str(neu2) not in ((ov.get("x-docker-shell") or {}).get("mounts") or {})
        finally:
            ds._CFG["add_new_mode"] = "host_path"
        ok("preset naming + x-docker-shell mapping (mask-stable, cleaned on remove)")

        # network scope: only the selected service is isolated
        ds._CFG["network_scope"] = "service"
        try:
            b.edit_network_in_main(str(proj), enable_network=False,
                                   service_name="testsvc")
            okup, err = b.apply_compose(str(proj)); assert okup, err
            ctr = get_ctr(data)
            assert status(data, ctr)["is_isolated"]
            ctr2 = get_ctr(data, service="svc2")
            st2 = b.get_status(ctr2["id"], str(data), str(proj), "svc2")
            assert not st2["is_isolated"], "svc2 was isolated despite service scope"
            b.edit_network_in_main(str(proj), enable_network=True,
                                   service_name="testsvc")
            okup, err = b.apply_compose(str(proj)); assert okup, err
        finally:
            ds._CFG["network_scope"] = "all"
        ok("network scope 'selected service only'")

        # persist to main: RO for /data written into compose.yaml,
        # then delete override -> RO must survive
        cfg = {"target_folder": str(data), "mount_mode": "ro",
               "ram_limit_gb": 1, "current_volumes": b.get_all_volumes(ctr["id"])}
        b.persist_to_main(str(proj), "testsvc", cfg)
        b.write_override(str(proj), "testsvc", cfg)
        okup, err = b.apply_compose(str(proj)); assert okup, err
        import yaml as _yaml
        main_c = _yaml.safe_load((proj / "compose.yaml").read_text())
        vols = main_c["services"]["testsvc"]["volumes"]
        assert any(v.endswith(":ro") and ":/data:" in v for v in vols), vols
        assert main_c["services"]["testsvc"]["deploy"]["resources"]["limits"]["memory"] == "1G"
        (proj / "compose.override.yaml").unlink()
        okup, err = b.apply_compose(str(proj)); assert okup, err
        ctr = get_ctr(data)
        assert exec_in(ctr, ["touch", "/data/y"])[0] != 0, \
            "persisted RO did not survive override deletion"
        ok("persist to main (RO + RAM survive override deletion)")

        # orphaned masks: main_only creates sub-masks; deleting a subfolder
        # on the host must be detected and cleanly removable
        ctr = get_ctr(data)
        apply_mode(data, "main_only", ctr)
        shutil.rmtree(data / "sub2")
        orphans = b.find_orphaned_masks(str(proj), "testsvc")
        assert len(orphans) == 1 and orphans[0][1] == str(data / "sub2"), orphans
        assert b.remove_orphaned_masks(str(proj), "testsvc") == 1
        assert b.find_orphaned_masks(str(proj), "testsvc") == []
        okup, err = b.apply_compose(str(proj)); assert okup, err
        ctr = get_ctr(data)
        st = status(data, ctr)
        assert len([m for m in st["mounts"] if m["masked"]]) == 1, st  # sub1 bleibt
        apply_mode(data, "rw", ctr)  # aufräumen für die Folgetests
        ctr = get_ctr(data)
        ok("orphaned mask detected + removed (host subfolder deleted)")

        # remove share: /data disappears from main + override, container
        # loses access
        okup, err = b.remove_share(str(proj), "testsvc", str(data))
        assert okup, err
        main_c = _yaml.safe_load((proj / "compose.yaml").read_text())
        vols = main_c["services"]["testsvc"].get("volumes") or []
        assert not any(":/data" in str(v) for v in vols), vols
        ctr = get_ctr(data)  # still listed (new_mount=True now)
        assert ctr["new_mount"] is True
        assert exec_in(ctr, ["ls", "/data"])[0] != 0, "/data still exists!"
        ok("remove share (gone from main+override, access revoked)")

        print(f"\nALL {PASSED} TESTS PASSED")
        return 0

    finally:
        sh(["docker", "compose", "down", "-t", "1"], cwd=proj)
        shutil.rmtree(_SANDBOX, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
