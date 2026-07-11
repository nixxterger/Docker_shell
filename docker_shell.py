#!/usr/bin/env python3
"""Docker-Shell — lightweight Docker management from your file manager.

Right-click a folder -> configure how a running compose container may
access it: network isolation, RAM limit, read-only or masked mounts.
Masking bind-mounts an empty "sacrificial" folder over the real one, so
data stays physically present but invisible to the container (protects
against rm -rf and AI-agent hallucinations).

Changes are written to <compose>.override.yml via PyYAML; only
network_mode is edited in the main compose file (with automatic backup).
"""

import argparse
import json
import locale
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

__version__ = "1.0.0"

APP_TITLE = "Docker Konfig"

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger("docker-shell")


# ════════════════════════════════════════════════════════════════
#  i18n — English default, German via system locale
# ════════════════════════════════════════════════════════════════

def _detect_lang():
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        val = os.environ.get(var)
        if val:
            return val[:2].lower()
    try:
        return (locale.getlocale()[0] or "en")[:2].lower()
    except Exception:
        return "en"


_DE = {
    "customtkinter is not installed. Install it with: pip install customtkinter":
        "customtkinter ist nicht installiert. Installation: pip install customtkinter",
    "PyYAML is not installed. Install it with: pip install PyYAML":
        "PyYAML ist nicht installiert. Installation: pip install PyYAML",
    "Docker is not installed or not in PATH.":
        "Docker ist nicht installiert oder nicht im PATH.",
    "Cannot talk to the Docker daemon. Is it running and are you in the 'docker' group?":
        "Keine Verbindung zum Docker-Daemon. Läuft er, und bist du in der Gruppe 'docker'?",
    "Docker Compose v2 ('docker compose') is required but was not found.":
        "Docker Compose v2 ('docker compose') wird benötigt, wurde aber nicht gefunden.",
    "Usage: docker_shell.py <folder>":
        "Verwendung: docker_shell.py <ordner>",
    "'{}' is not a valid folder.":
        "'{}' ist kein gültiger Ordner.",
    "Cannot create the mask folder '{}': {}":
        "Kann den Maskierungs-Ordner '{}' nicht erstellen: {}",
    "No compose file found in {}":
        "Keine Compose-Datei gefunden in {}",
    "folder to configure":
        "zu konfigurierender Ordner",
    # Panel 1
    "No running containers found.":
        "Keine laufenden Container gefunden.",
    "No compose project found":
        "Kein Compose-Projekt gefunden",
    "Folder not mounted here yet — selecting will add it":
        "Ordner hier noch nicht eingebunden — Auswahl nimmt ihn neu auf",
    "Close": "Schließen",
    # Panel 2
    "Back": "Zurück",
    "Status could not be read.":
        "Status konnte nicht gelesen werden.",
    "This folder is not mounted in the container yet.\n\"OK\" adds it with the selected mount mode.":
        "Dieser Ordner ist im Container noch nicht eingebunden.\n„OK“ nimmt ihn mit dem gewählten Mount-Modus neu auf.",
    "Web / Network": "Web / Netzwerk",
    "Memory limit (RAM)": "Speicherschutz (RAM-Limit)",
    "Mount mode": "Mount-Modus",
    "Read-Write": "Read-Write",
    "Read-Only": "Read-Only",
    "Hidden (masked)": "Temp versteckt",
    "Main folder only": "Nur Hauptordner",
    "Unmask": "Demaskieren",
    # Status header
    "Network": "Netzwerk",
    "Web": "Web",
    "Isolated": "Isoliert",
    "RAM limit": "RAM-Limit",
    "No limit": "Kein Limit",
    "Mount": "Mount",
    "Not mounted": "Nicht eingebunden",
    "Applied — container is restarting, use 'Back' to reload the status.":
        "Angewendet — Container startet neu, Status bitte über „Zurück“ neu laden.",
    # Errors
    "Error": "Fehler",
    "docker compose up failed (rc={}):\n{}":
        "docker compose up fehlgeschlagen (rc={}):\n{}",
    "Apply failed:\n{}":
        "Anwendung fehlgeschlagen:\n{}",
    "Unmask failed:\n{}":
        "Demaskieren fehlgeschlagen:\n{}",
    "Reset failed: {}":
        "Reset fehlgeschlagen: {}",
    "Timeout after {}s":
        "Timeout nach {}s",
    "Docker command not found. Is Docker installed?":
        "Docker-Befehl nicht gefunden. Ist Docker installiert?",
}

_LANG = _detect_lang()


def tr(text):
    """Translate a UI string (English key -> system language)."""
    if _LANG == "de":
        return _DE.get(text, text)
    return text


def _notify(msg):
    """Best-effort desktop notification (visible even without a terminal)."""
    try:
        subprocess.run(["notify-send", APP_TITLE, msg], timeout=5)
    except Exception:
        pass


try:
    import yaml
except ImportError:
    _msg = tr("PyYAML is not installed. Install it with: pip install PyYAML")
    print(_msg)
    _notify(_msg)
    sys.exit(1)

try:
    import customtkinter as ctk
    from tkinter import messagebox
except ImportError:
    _msg = tr("customtkinter is not installed. Install it with: pip install customtkinter")
    print(_msg)
    _notify(_msg)
    sys.exit(1)


# ════════════════════════════════════════════════════════════════
#  Configuration — XDG paths, optional config file
# ════════════════════════════════════════════════════════════════

def _xdg(env_var, fallback):
    base = os.environ.get(env_var)
    return Path(base) if base else Path.home() / fallback


DATA_DIR = _xdg("XDG_DATA_HOME", ".local/share") / "docker-shell"
CONFIG_FILE = _xdg("XDG_CONFIG_HOME", ".config") / "docker-shell" / "config.yml"


def _load_config():
    try:
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError) as e:
        log.warning("Cannot read config %s: %s", CONFIG_FILE, e)
    return {}


_CFG = _load_config()

# The empty "sacrificial" folder that gets bind-mounted over masked paths.
TEMP_LEER = str(Path(os.path.expanduser(
    str(_CFG.get("temp_leer", DATA_DIR / "temp_leer")))))

# Compose file names, in lookup order (compose spec first, legacy second)
COMPOSE_NAMES = ("compose.yaml", "compose.yml",
                 "docker-compose.yml", "docker-compose.yaml")


def find_compose_file(compose_dir):
    """Locate the main compose file in a project directory."""
    for name in COMPOSE_NAMES:
        p = Path(compose_dir) / name
        if p.is_file():
            return p
    return None


def override_path_for(compose_file):
    """Matching override file name (compose.yaml -> compose.override.yaml)."""
    base = Path(compose_file)
    return base.with_name(f"{base.stem}.override{base.suffix}")


# ════════════════════════════════════════════════════════════════
#  Backend — all Docker operations via CLI (subprocess)
# ════════════════════════════════════════════════════════════════

class DockerBackend:
    """All Docker operations via CLI. No docker-py needed."""

    def __init__(self):
        self.uid_gid = f"{os.getuid()}:{os.getgid()}"

    # ── Helpers ────────────────────────────────────────────────

    @staticmethod
    def _run(cmd, timeout=30, cwd=None):
        """subprocess.run wrapper -> (stdout_str, stderr_str, returncode)"""
        try:
            r = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=timeout, cwd=cwd,
            )
            return r.stdout.strip(), r.stderr.strip(), r.returncode
        except subprocess.TimeoutExpired:
            return "", tr("Timeout after {}s").format(timeout), -1
        except FileNotFoundError:
            return "", tr("Docker command not found. Is Docker installed?"), -2

    @staticmethod
    def _backup_path(compose_dir):
        """Backup path for the original main compose file."""
        return Path(compose_dir) / ".docker_shell_compose_bak"

    # ── Compose volume resolution ──────────────────────────────

    @staticmethod
    def _compose_volumes(compose_dir, service_name=None):
        """Bind-mount entries (host_src, container_dest) from the original
        compose file. Short and long syntax; named volumes are skipped.
        service_name=None -> all services."""
        path = find_compose_file(compose_dir)
        if not path:
            log.warning("No compose file in %s", compose_dir)
            return []
        try:
            with open(path, encoding="utf-8") as f:
                compose = yaml.safe_load(f) or {}
        except (OSError, yaml.YAMLError) as e:
            log.warning("Cannot read %s: %s", path, e)
            return []

        volumes = []
        for sname, sconf in (compose.get("services") or {}).items():
            if service_name is not None and sname != service_name:
                continue
            for vol in (sconf or {}).get("volumes") or []:
                if isinstance(vol, str):
                    parts = vol.split(":")
                    if len(parts) < 2:
                        continue
                    src, dest = parts[0], parts[1]
                elif isinstance(vol, dict):
                    src, dest = vol.get("source", ""), vol.get("target", "")
                else:
                    continue
                if not src or not dest:
                    continue
                src = os.path.expanduser(src)
                if not os.path.isabs(src):
                    if not src.startswith("."):
                        continue  # named volume, no host path
                    src = str(Path(compose_dir) / src)
                volumes.append((str(Path(src).resolve()), dest))
        return volumes

    def resolve_container_dest(self, compose_dir, service_name, host_folder):
        """Container path of the host folder, derived from the original
        compose file.

        Deliberately NOT from docker inspect: while masked, the live mount
        points to the sacrificial folder and the mapping would be lost. The
        original compose file stays stable. Also supports subpaths of a
        mounted volume."""
        target = Path(str(host_folder)).resolve()
        for src, dest in self._compose_volumes(compose_dir, service_name):
            src_path = Path(src)
            if target == src_path:
                return dest.rstrip("/") or "/"
            try:
                rel = target.relative_to(src_path)
                return f"{dest.rstrip('/')}/{rel.as_posix()}"
            except ValueError:
                continue
        return None

    # ── Container scan ─────────────────────────────────────────

    def scan_containers(self, target_folder=None):
        """Find running containers.

        Returns list of dicts:
            {id, name, service_name, compose_dir | None, warning, new_mount}
        """
        out, err, rc = self._run(["docker", "ps", "--format", "{{.ID}}"])
        if rc != 0:
            log.error("docker ps failed: %s", err)
            return []

        containers = []
        for cid in out.splitlines():
            cid = cid.strip()
            if not cid:
                continue

            out, _, rc = self._run(["docker", "inspect", cid])
            if rc != 0:
                continue

            try:
                data = json.loads(out)[0]
            except (json.JSONDecodeError, IndexError):
                continue

            name = data.get("Name", "").lstrip("/")
            labels = data.get("Config", {}).get("Labels", {})
            compose_dir = labels.get("com.docker.compose.project.working_dir")
            service_name = labels.get("com.docker.compose.service", name)

            if not compose_dir:
                containers.append({
                    "id": cid,
                    "name": name,
                    "service_name": None,
                    "compose_dir": None,
                    "warning": True,
                })
            else:
                # List every compose container and mark whether the target
                # folder is already known there (live mount OR original
                # compose — live mounts alone are not enough: while masked,
                # the mount source is the sacrificial folder). Unknown
                # folders can be added on apply (new_mount=True).
                is_known = bool(target_folder) and (
                    self._folder_mounted_in_container(
                        cid, Path(target_folder).resolve())
                    or self.resolve_container_dest(
                        compose_dir, service_name, target_folder) is not None)
                containers.append({
                    "id": cid,
                    "name": name,
                    "service_name": service_name,
                    "compose_dir": compose_dir,
                    "warning": False,
                    "new_mount": bool(target_folder) and not is_known,
                })

        return containers

    def _folder_mounted_in_container(self, container_id, target_path):
        """Is target_path (or a parent of it) mounted in the container?"""
        out, _, rc = self._run(["docker", "inspect", "--format",
                                '{{range .Mounts}}{{.Source}}{{"\n"}}{{end}}',
                                container_id])
        if rc != 0:
            return False
        for src in out.splitlines():
            try:
                src_path = Path(src.strip()).resolve()
                if target_path == src_path or target_path.is_relative_to(src_path):
                    return True
            except (ValueError, OSError):
                continue
        return False

    # ── Status ─────────────────────────────────────────────────

    def get_status(self, container_id, target_folder, compose_dir=None,
                   service_name=None):
        """Current state of the folder inside the container.

        Returns dict:
            {is_isolated, memory_gb, mounts}
        """
        out, _, rc = self._run(["docker", "inspect", "--format",
                                '{{json .}}', container_id])
        if rc != 0:
            return None

        data = json.loads(out)
        hc = data.get("HostConfig", {})
        mounts = data.get("Mounts", [])

        net_mode = hc.get("NetworkMode", "default")
        is_isolated = (net_mode == "none")

        mem_bytes = hc.get("Memory", 0)
        memory_gb = max(1, round(mem_bytes / (1024 ** 3))) if mem_bytes > 0 else 0

        # Stable container path from the original compose file — the live
        # mount source is useless as a key: while masked it is the
        # sacrificial folder.
        real_target = Path(str(target_folder)).resolve()
        target_dest = None
        if compose_dir and service_name:
            target_dest = self.resolve_container_dest(
                compose_dir, service_name, target_folder)
            if not target_dest:
                # Newly added folders: container path = host path
                target_dest = str(real_target)

        mount_entries = []
        for m in mounts:
            source = m.get("Source", "")
            dest = m.get("Destination", "")
            mode = m.get("Mode", "rw") or "rw"

            if target_dest:
                if dest == target_dest:
                    # Base mount of the target folder — masked if the source
                    # currently is the sacrificial folder
                    mount_entries.append({
                        "source": source,
                        "dest": dest,
                        "mode": mode,
                        "masked": source == TEMP_LEER,
                    })
                elif (source == TEMP_LEER
                        and dest.startswith(target_dest.rstrip("/") + "/")):
                    # Masked subfolder ("main folder only" mode)
                    mount_entries.append({
                        "source": source,
                        "dest": dest,
                        "mode": mode,
                        "masked": True,
                    })
            else:
                # Fallback without compose info: source-based match
                try:
                    if Path(source).resolve() == real_target:
                        mount_entries.append({
                            "source": source,
                            "dest": dest,
                            "mode": mode,
                            "masked": False,
                        })
                except (ValueError, OSError):
                    continue

        return {
            "is_isolated": is_isolated,
            "memory_gb": memory_gb,
            "mounts": mount_entries,
        }

    # ── All volumes of a container ─────────────────────────────

    def get_all_volumes(self, container_id):
        """All volume mounts as strings (docker-compose format)."""
        out, _, rc = self._run(["docker", "inspect", "--format",
                                '{{range .Mounts}}{{.Source}}:{{.Destination}}:{{.Mode}}{{"\n"}}'
                                '{{end}}', container_id])
        if rc != 0 or not out.strip():
            return []
        return [v.strip() for v in out.splitlines() if v.strip()]

    # ── Write override file ────────────────────────────────────

    def write_override(self, compose_dir, service_name, config):
        """Write <compose>.override.yml via PyYAML.

        config dict contains:
            target_folder   (str) — target folder on the host
            mount_mode      (str) — "rw" | "ro" | "masked" | "main_only"
            ram_limit_gb    (int) — 0 = no limit
            current_volumes (list) — all current volume strings
        """
        target_folder = str(config["target_folder"])
        mount_mode = config.get("mount_mode", "rw")
        temp_leer = TEMP_LEER
        current_volumes = config.get("current_volumes", [])

        base = find_compose_file(compose_dir)
        if not base:
            raise FileNotFoundError(
                tr("No compose file found in {}").format(compose_dir))

        # Stable container target path from the original compose file.
        # Live mounts are useless as a key: while masked, the source is the
        # sacrificial folder and the target folder would be unfindable
        # (switching back to RW/RO would go nowhere).
        real_target = Path(target_folder).resolve()
        target_dest = self.resolve_container_dest(
            compose_dir, service_name, target_folder)
        if not target_dest:
            # Folder is not a volume yet -> it gets added; container path =
            # host path (identical view as on the host)
            target_dest = str(real_target)

        # Rebuild volumes — match on the container path (dest), never on
        # the host source
        new_volumes = []
        target_seen = False
        for vol in current_volumes:
            parts = vol.split(":")
            source = parts[0]
            dest = parts[1] if len(parts) > 1 else ""
            mode = parts[2] if len(parts) > 2 else ""

            is_target = (dest == target_dest)
            is_masked_subdir = (source == temp_leer
                                and dest.startswith(target_dest.rstrip("/") + "/"))

            # Drop old sub-masks (regenerated below if needed)
            if is_masked_subdir:
                continue

            if is_target:
                target_seen = True
                if mount_mode == "masked":
                    new_volumes.append(f"{temp_leer}:{dest}")
                elif mount_mode in ("ro", "main_only"):
                    new_volumes.append(f"{target_folder}:{dest}:ro")
                else:  # rw — remount the real folder (lifts any mask)
                    new_volumes.append(f"{target_folder}:{dest}")
            else:
                # Pass through; clean empty mode parts ("src:dest:")
                new_volumes.append(":".join(p for p in (source, dest, mode) if p))

        if not target_seen:
            # Target folder missing from live mounts (e.g. newly added) —
            # create the entry so the mode takes effect
            if mount_mode == "masked":
                new_volumes.append(f"{temp_leer}:{target_dest}")
            elif mount_mode in ("ro", "main_only"):
                new_volumes.append(f"{target_folder}:{target_dest}:ro")
            else:
                new_volumes.append(f"{target_folder}:{target_dest}")

        # "Main folder only": mask every first-level subdirectory
        if mount_mode == "main_only" and real_target.is_dir():
            for entry in sorted(real_target.iterdir()):
                if entry.is_dir():
                    # Derive the container path for the subdir (not host path!)
                    container_subdir = f"{target_dest.rstrip('/')}/{entry.name}"
                    new_volumes.append(f"{temp_leer}:{container_subdir}")

        override = {
            "services": {
                service_name: {
                    "user": self.uid_gid,
                    "logging": {
                        "driver": "json-file",
                        "options": {
                            "max-size": "10m",
                            "max-file": "3",
                        }
                    },
                    "volumes": new_volumes,
                }
            }
        }

        if config.get("ram_limit_gb", 0) > 0:
            override["services"][service_name]["deploy"] = {
                "resources": {
                    "limits": {
                        "memory": f"{config['ram_limit_gb']}G"
                    }
                }
            }

        override_path = override_path_for(base)
        with open(override_path, "w", encoding="utf-8") as f:
            yaml.dump(override, f, default_flow_style=False, sort_keys=False,
                      allow_unicode=True)

        log.info("Override written: %s", override_path)

    # ── Edit network in main compose ───────────────────────────

    def edit_network_in_main(self, compose_dir, enable_network):
        """Edit network_mode directly in the main compose file.

        enable_network=True  -> remove network_mode (default network)
        enable_network=False -> set network_mode: "none" (isolation)
        The first edit creates a backup of the original file.
        """
        path = find_compose_file(compose_dir)
        if not path:
            raise FileNotFoundError(
                tr("No compose file found in {}").format(compose_dir))

        backup = self._backup_path(compose_dir)

        # First edit -> create backup (only if none exists yet)
        if not enable_network and not backup.exists():
            shutil.copy2(path, backup)
            log.info("Backup created: %s", backup)

        with open(path, encoding="utf-8") as f:
            compose = yaml.safe_load(f)

        services = compose.get("services", {})
        modified = False

        for sname, sconf in services.items():
            if enable_network:
                if sconf.get("network_mode") == "none":
                    del sconf["network_mode"]
                    modified = True
            else:
                if sconf.get("network_mode") != "none":
                    sconf["network_mode"] = "none"
                    modified = True

        if modified:
            with open(path, "w", encoding="utf-8") as f:
                yaml.dump(compose, f, default_flow_style=False, sort_keys=False)
            log.info("Main compose edited: %s (network=%s)", path, enable_network)

    # ── Apply ──────────────────────────────────────────────────

    def apply_compose(self, compose_dir):
        """Run docker compose up -d in the project directory.

        Returns (success: bool, error_message: str | None)
        """
        _, err, rc = self._run(
            ["docker", "compose", "up", "-d"],
            timeout=120,
            cwd=str(compose_dir),
        )
        if rc == 0:
            return True, None
        return False, tr("docker compose up failed (rc={}):\n{}").format(rc, err)

    # ── Reset ──────────────────────────────────────────────────

    def reset_compose(self, compose_dir):
        """Full reset: delete override file + restore main compose from backup.

        Returns (success: bool, error_message: str | None)
        """
        try:
            base = find_compose_file(compose_dir)
            if base:
                override = override_path_for(base)
                if override.exists():
                    override.unlink()
                    log.info("Override deleted: %s", override)

            backup = self._backup_path(compose_dir)
            if backup.exists() and base and base.exists():
                shutil.copy2(backup, base)
                log.info("Main compose restored from backup")

            return self.apply_compose(compose_dir)

        except Exception as e:
            return False, tr("Reset failed: {}").format(e)


# ════════════════════════════════════════════════════════════════
#  Environment preflight
# ════════════════════════════════════════════════════════════════

def preflight():
    """Check docker/compose availability. Returns an error string or None."""
    if shutil.which("docker") is None:
        return tr("Docker is not installed or not in PATH.")

    r = subprocess.run(["docker", "ps", "-q"], capture_output=True, text=True)
    if r.returncode != 0:
        return (tr("Cannot talk to the Docker daemon. Is it running and are "
                   "you in the 'docker' group?")
                + "\n\n" + r.stderr.strip())

    r = subprocess.run(["docker", "compose", "version"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return tr("Docker Compose v2 ('docker compose') is required but was "
                  "not found.")
    return None


# ════════════════════════════════════════════════════════════════
#  GUI — CustomTkinter app with panel switching
# ════════════════════════════════════════════════════════════════

# Canonical mount modes: (English label used as translation key, internal id)
MOUNT_MODES = [
    ("Read-Write", "rw"),
    ("Read-Only", "ro"),
    ("Hidden (masked)", "masked"),
    ("Main folder only", "main_only"),
]


class DockerShellApp(ctk.CTk):
    """Main app: one window, two panels (container selection / config)."""

    # ── Init ───────────────────────────────────────────────────

    def __init__(self, target_folder):
        self.target_folder = Path(target_folder).resolve()
        self.backend = DockerBackend()

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        super().__init__()
        self.title(APP_TITLE)
        # Open at the mouse position (slightly offset so the cursor lands
        # inside), clamped to the screen edges
        win_w, win_h = 540, 500
        pos_x = max(0, min(self.winfo_pointerx() - 40,
                           self.winfo_screenwidth() - win_w - 10))
        pos_y = max(0, min(self.winfo_pointery() - 30,
                           self.winfo_screenheight() - win_h - 60))
        self.geometry(f"{win_w}x{win_h}+{pos_x}+{pos_y}")
        self.resizable(False, False)

        # State
        self.selected_container = None     # dict from scan_containers()
        self.current_status = None         # dict from get_status()
        self.all_volumes = []              # all volume strings of the container

        self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_frame.pack(fill="both", expand=True, padx=14, pady=12)

        self.panel_selection = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.panel_config = ctk.CTkFrame(self.main_frame, fg_color="transparent")

        self._build_selection_panel()
        self._build_config_panel()

        self.show_selection()

    # ── Panel switching ────────────────────────────────────────

    def show_selection(self):
        """Show panel 1 (container selection)."""
        self.panel_config.pack_forget()
        self.panel_selection.pack(fill="both", expand=True)
        self._refresh_container_list()

    def show_config(self, container):
        """Show panel 2 (configuration)."""
        self.selected_container = container
        self.panel_selection.pack_forget()
        self.panel_config.pack(fill="both", expand=True)
        self._load_status(container)

    # ── Panel 1 — container selection ──────────────────────────

    def _build_selection_panel(self):
        p = self.panel_selection

        ctk.CTkLabel(p, text=APP_TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(
            anchor="w", pady=(0, 4)
        )
        ctk.CTkLabel(p, text=str(self.target_folder), font=ctk.CTkFont(size=12)).pack(anchor="w")

        ctk.CTkFrame(p, height=2, fg_color="#555555").pack(fill="x", pady=(8, 6))

        self.scroll_frame = ctk.CTkScrollableFrame(p)
        self.scroll_frame.pack(fill="both", expand=True)

    def _refresh_container_list(self):
        """Refresh the container list (called on panel show)."""
        for w in self.scroll_frame.winfo_children():
            w.destroy()

        containers = self.backend.scan_containers(str(self.target_folder))

        if not containers:
            ctk.CTkLabel(
                self.scroll_frame, text=tr("No running containers found."),
                font=ctk.CTkFont(size=14), text_color="#aaaaaa",
            ).pack(expand=True)
            return

        for ctr in containers:
            btn = ctk.CTkButton(
                self.scroll_frame,
                text=f"  {ctr['name']}",
                font=ctk.CTkFont(size=13),
                height=40,
                corner_radius=6,
                command=lambda c=ctr: self.on_container_selected(c),
            )
            btn.pack(fill="x", padx=4, pady=2)

            if ctr.get("warning"):
                # No compose project -> grayed out + warning
                btn.configure(state="disabled", fg_color="#333333", text_color="#888888")
                ctk.CTkLabel(
                    self.scroll_frame,
                    text=f"    ⚠ {tr('No compose project found')} ({ctr['name']})",
                    font=ctk.CTkFont(size=10),
                    text_color="#888888",
                ).pack(anchor="w", padx=(24, 0))

            elif ctr.get("compose_dir"):
                ctk.CTkLabel(
                    self.scroll_frame,
                    text=f"    📁 {ctr['compose_dir']}",
                    font=ctk.CTkFont(size=10),
                    text_color="#888888",
                ).pack(anchor="w", padx=(24, 0))
                if ctr.get("new_mount"):
                    ctk.CTkLabel(
                        self.scroll_frame,
                        text="    ➕ " + tr("Folder not mounted here yet — "
                                            "selecting will add it"),
                        font=ctk.CTkFont(size=10, weight="bold"),
                        text_color="#e6a23c",
                    ).pack(anchor="w", padx=(24, 0))

        ctk.CTkButton(
            self.scroll_frame, text=tr("Close"), fg_color="#333333",
            command=self.quit,
        ).pack(pady=(16, 0))

    def on_container_selected(self, container):
        """Container selected -> jump to the config panel."""
        if container.get("warning"):
            # Grayed-out containers are not selectable (F5)
            return
        self.show_config(container)

    def _find_container(self, service_name, compose_dir):
        """Re-resolve a container after compose up (new ID after recreate)."""
        for ctr in self.backend.scan_containers(str(self.target_folder)):
            if (not ctr.get("warning")
                    and ctr.get("service_name") == service_name
                    and ctr.get("compose_dir") == compose_dir):
                return ctr
        return None

    # ── Panel 2 — configuration ────────────────────────────────

    def _build_config_panel(self):
        p = self.panel_config

        ctk.CTkButton(
            p, text="← " + tr("Back"), width=80, height=30, font=ctk.CTkFont(size=12),
            fg_color="#333333", command=self.show_selection,
        ).pack(anchor="nw", pady=(0, 6))

        self.lbl_container_title = ctk.CTkLabel(
            p, text="", font=ctk.CTkFont(size=16, weight="bold"),
        )
        self.lbl_container_title.pack(anchor="w")

        ctk.CTkFrame(p, height=2, fg_color="#555555").pack(fill="x", pady=(8, 4))

        # ── Status header (Q&A1) ────────────────────────────────
        self.lbl_status = ctk.CTkLabel(
            p, text="", font=ctk.CTkFont(size=12),
            wraplength=500, justify="left",
        )
        self.lbl_status.pack(anchor="w", pady=(0, 10))

        # Banner for not-yet-mounted folders (packed on demand)
        self.banner_new_mount = ctk.CTkLabel(
            p, text="➕  " + tr("This folder is not mounted in the container "
                                "yet.\n\"OK\" adds it with the selected mount "
                                "mode."),
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#1a1a1a", fg_color="#e6a23c", corner_radius=6,
            wraplength=480, justify="center", pady=8,
        )

        # ── Web / network toggle ─────────────────────────────────
        frame_net = ctk.CTkFrame(p, fg_color="transparent")
        frame_net.pack(fill="x", pady=(0, 8))
        self.frame_net = frame_net

        ctk.CTkLabel(frame_net, text=tr("Web / Network"), font=ctk.CTkFont(size=13)).pack(
            side="left"
        )
        self.toggle_network = ctk.CTkSwitch(
            frame_net, text="", width=50, command=self._on_network_toggle,
        )
        self.toggle_network.pack(side="right")

        # ── RAM limit toggle + stepper ───────────────────────────
        frame_ram = ctk.CTkFrame(p, fg_color="transparent")
        frame_ram.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(frame_ram, text=tr("Memory limit (RAM)"), font=ctk.CTkFont(size=13)).pack(
            side="left"
        )
        self.toggle_ram = ctk.CTkSwitch(
            frame_ram, text="", width=50, command=self._on_ram_toggle,
        )
        self.toggle_ram.pack(side="right")

        frame_stepper = ctk.CTkFrame(p, fg_color="transparent")
        frame_stepper.pack(fill="x", pady=(0, 8))

        self.btn_ram_minus = ctk.CTkButton(
            frame_stepper, text="−", width=40, height=32, font=ctk.CTkFont(size=16),
            fg_color="#3a3a3a", command=self._ram_decrease, state="disabled",
        )
        self.btn_ram_minus.pack(side="left", padx=(4, 0))

        self.lbl_ram_value = ctk.CTkLabel(
            frame_stepper, text="1 GB", font=ctk.CTkFont(size=16), width=70,
        )
        self.lbl_ram_value.pack(side="left")

        self.btn_ram_plus = ctk.CTkButton(
            frame_stepper, text="+", width=40, height=32, font=ctk.CTkFont(size=16),
            fg_color="#3a3a3a", command=self._ram_increase, state="disabled",
        )
        self.btn_ram_plus.pack(side="left", padx=(0, 4))

        # ── Mount mode dropdown ──────────────────────────────────
        frame_mount = ctk.CTkFrame(p, fg_color="transparent")
        frame_mount.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(frame_mount, text=tr("Mount mode"), font=ctk.CTkFont(size=13)).pack(
            side="left"
        )
        self.dropdown_mount = ctk.CTkComboBox(
            frame_mount,
            values=[tr(label) for label, _ in MOUNT_MODES],
            width=200, command=self._on_mount_change,
        )
        self.dropdown_mount.pack(side="right")

        # ── Action buttons ───────────────────────────────────────
        frame_actions = ctk.CTkFrame(p, fg_color="transparent")
        frame_actions.pack(fill="x", pady=(16, 0))

        self.btn_demask = ctk.CTkButton(
            frame_actions, text=tr("Unmask"), width=130, height=38,
            font=ctk.CTkFont(size=13), fg_color="#4a4a2a", hover_color="#5a5a3a",
            command=self._on_demask,
        )
        self.btn_demask.pack(side="left", padx=(0, 6))

        self.btn_ok = ctk.CTkButton(
            frame_actions, text="OK", width=130, height=38,
            font=ctk.CTkFont(size=14, weight="bold"), fg_color="#2ba640", hover_color="#3cc855",
            command=self._on_apply,
        )
        self.btn_ok.pack(side="right")

    # ── Load status and fill the UI ────────────────────────────

    def _load_status(self, container):
        """Read status from docker inspect + update the UI."""
        cid = container["id"]
        cname = container["name"]
        self.lbl_container_title.configure(text=cname)

        status = self.backend.get_status(
            cid, self.target_folder,
            compose_dir=container.get("compose_dir"),
            service_name=container.get("service_name"),
        )
        if not status:
            self.lbl_status.configure(
                text="⚠ " + tr("Status could not be read."),
                text_color="#ff6b6b",
            )
            return

        self.current_status = status
        self.all_volumes = self.backend.get_all_volumes(cid)

        # Network status
        net_text = tr("Isolated") if status["is_isolated"] else tr("Web")
        self.toggle_network.set(not status["is_isolated"])  # True = web on

        # RAM status
        ram_gb = status["memory_gb"]
        has_ram = ram_gb > 0
        self.toggle_ram.set(has_ram)
        if has_ram:
            self._set_ram_stepper(ram_gb)
        else:
            self._set_ram_stepper(1)

        # Determine mount mode (canonical English label, translated on display)
        mount_label = "Read-Write"
        for m in status["mounts"]:
            if m["masked"]:
                mount_label = "Hidden (masked)"
                break
            if m["mode"] == "ro":
                mount_label = "Read-Only"
        # "Main folder only" = main mount RO + masked subdirs
        has_main_ro = any(
            not m["masked"] and m["mode"] == "ro" for m in status["mounts"]
        )
        has_masked_subdir = any(m["masked"] for m in status["mounts"])
        if has_main_ro and has_masked_subdir:
            mount_label = "Main folder only"

        self.dropdown_mount.set(tr(mount_label))

        # Status header (Q&A1)
        ram_str = f"{ram_gb} GB" if ram_gb > 0 else tr("No limit")
        mount_display = tr(mount_label)
        if not status["mounts"]:
            mount_display = tr("Not mounted")
            # Show the prominent banner above the options
            self.banner_new_mount.pack(
                fill="x", pady=(0, 10), before=self.frame_net)
        else:
            self.banner_new_mount.pack_forget()
        status_line = (
            f"{tr('Network')}: {net_text} | {tr('RAM limit')}: {ram_str} | "
            f"{tr('Mount')}: {mount_display}"
        )
        self.lbl_status.configure(text=status_line, text_color="#aaaaaa")

    # ── RAM stepper logic ──────────────────────────────────────

    def _set_ram_stepper(self, gb):
        """Set the RAM value and update the UI."""
        gb = max(1, min(gb, 64))  # Q&A3: minimum 1 GB, practical cap 64
        self.lbl_ram_value.configure(text=f"{gb} GB")

    def _on_ram_toggle(self):
        enabled = self.toggle_ram.get()
        state = "normal" if enabled else "disabled"
        self.btn_ram_minus.configure(state=state)
        self.btn_ram_plus.configure(state=state)

    def _ram_increase(self):
        current = int(self.lbl_ram_value.cget("text").split()[0])
        self._set_ram_stepper(current + 1)

    def _ram_decrease(self):
        current = int(self.lbl_ram_value.cget("text").split()[0])
        if current > 1:  # Q&A3: minimum 1 GB
            self._set_ram_stepper(current - 1)

    # ── Toggle callbacks (UI state only) ────────────────────────

    def _on_network_toggle(self):
        pass  # evaluated on apply

    def _on_mount_change(self, value):
        pass  # evaluated on apply

    def _selected_mount_mode(self):
        """Map the (translated) dropdown value back to the internal mode id."""
        shown = self.dropdown_mount.get()
        for label, mode in MOUNT_MODES:
            if tr(label) == shown:
                return mode
        return "rw"

    # ── Action: OK (apply) ─────────────────────────────────────

    def _on_apply(self):
        """Apply the configuration -> write override + compose up."""
        container = self.selected_container
        if not container:
            return

        compose_dir = container["compose_dir"]
        service_name = container.get("service_name", container["name"])

        enable_network = bool(self.toggle_network.get())   # True = web on
        ram_limit_gb = int(self.lbl_ram_value.cget("text").split()[0]) if self.toggle_ram.get() else 0
        mount_mode = self._selected_mount_mode()

        config = {
            "target_folder": str(self.target_folder),
            "mount_mode": mount_mode,
            "ram_limit_gb": ram_limit_gb,
            "current_volumes": self.all_volumes,
        }

        try:
            # 1. Edit network in the main compose (F1)
            self.backend.edit_network_in_main(compose_dir, enable_network=enable_network)

            # 2. Write the override file
            self.backend.write_override(compose_dir, service_name, config)

            # 3. Run docker compose up -d
            success, err = self.backend.apply_compose(compose_dir)
            if not success:
                messagebox.showerror(tr("Error"), err, parent=self)
                return

            # Success -> close silently (Q&A3 F10)
            self.quit()

        except Exception as e:
            log.exception("Apply failed")
            messagebox.showerror(
                tr("Error"), tr("Apply failed:\n{}").format(e), parent=self)

    # ── Action: unmask ─────────────────────────────────────────

    def _on_demask(self):
        """Lift all masks -> everything back to read-only (Q&A3 F3)."""
        container = self.selected_container
        if not container:
            return

        compose_dir = container["compose_dir"]
        service_name = container.get("service_name", container["name"])

        config = {
            "target_folder": str(self.target_folder),
            "mount_mode": "ro",  # unmask -> everything RO
            "ram_limit_gb": int(self.lbl_ram_value.cget("text").split()[0]) if self.toggle_ram.get() else 0,
            "current_volumes": self.all_volumes,
        }

        try:
            self.backend.edit_network_in_main(
                compose_dir, enable_network=bool(self.toggle_network.get())
            )
            self.backend.write_override(compose_dir, service_name, config)
            success, err = self.backend.apply_compose(compose_dir)
            if not success:
                messagebox.showerror(tr("Error"), err, parent=self)
                return

            # Update UI state — compose up recreated the container, the old
            # ID is stale -> re-resolve
            self.dropdown_mount.set(tr("Read-Only"))
            refreshed = self._find_container(
                container.get("service_name"), compose_dir)
            if refreshed:
                self.selected_container = refreshed
                self._load_status(refreshed)
            else:
                self.lbl_status.configure(
                    text=tr("Applied — container is restarting, use 'Back' "
                            "to reload the status."),
                    text_color="#aaaaaa",
                )

        except Exception as e:
            log.exception("Unmask failed")
            messagebox.showerror(
                tr("Error"), tr("Unmask failed:\n{}").format(e), parent=self)


# ════════════════════════════════════════════════════════════════
#  Entry point
# ════════════════════════════════════════════════════════════════

def _fatal(msg):
    """Show a fatal error (GUI dialog if possible) and exit."""
    log.error(msg)
    try:
        import tkinter as _tk
        root = _tk.Tk()
        root.withdraw()
        messagebox.showerror(APP_TITLE, msg)
        root.destroy()
    except Exception:
        print(f"ERROR: {msg}", file=sys.stderr)
        _notify(msg)
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        prog="docker-shell",
        description=__doc__.splitlines()[0],
    )
    parser.add_argument("folder", help=tr("folder to configure"))
    parser.add_argument("--version", action="version",
                        version=f"%(prog)s {__version__}")
    args = parser.parse_args()

    target_folder = Path(args.folder).resolve()
    if not target_folder.is_dir():
        _fatal(tr("'{}' is not a valid folder.").format(target_folder))

    err = preflight()
    if err:
        _fatal(err)

    # The sacrificial folder must exist (Q&A3 F6); create it if missing
    if not Path(TEMP_LEER).is_dir():
        try:
            Path(TEMP_LEER).mkdir(parents=True, exist_ok=True)
            log.info("Mask folder created: %s", TEMP_LEER)
        except OSError as e:
            _fatal(tr("Cannot create the mask folder '{}': {}").format(TEMP_LEER, e))

    app = DockerShellApp(str(target_folder))
    app.mainloop()


if __name__ == "__main__":
    main()
