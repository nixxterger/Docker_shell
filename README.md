# Docker-Shell

**Control what a Docker container may do with your folders — straight from the file manager.**

Right-click a folder → *Docker Konfig* → pick a running compose container → configure:

| Feature | What it does |
|---|---|
| **Web / Network** | Toggle full network isolation (`network_mode: none`) per project |
| **Memory limit** | Cap the container's RAM in 1-GB steps |
| **Mount mode** | Read-Write · Read-Only · Hidden (masked) · Main folder only |
| **Add folders** | Folders not mounted yet can be added on the fly (container path = host path) |
| **Unmask** | One click resets all masks back to read-only |

### The masking trick

*Hidden (masked)* bind-mounts an empty **sacrificial folder** over the real
one inside the container. Your data stays physically on disk but becomes
invisible to the container — an effective guard against `rm -rf`, runaway
scripts and AI-agent hallucinations. *Main folder only* keeps the top level
readable while masking every first-level subdirectory individually.

### How changes are applied

```
file manager trigger
  → docker inspect            (scan + live status)
  → PyYAML                    (<compose>.override.yml — regenerated per apply)
  → main compose edit         (network_mode only, with automatic backup)
  → docker compose up -d
```

The main compose file is only ever touched for the network toggle, and the
original is backed up to `.docker_shell_compose_bak` before the first edit.
Everything else lives in the override file, which can be deleted at any time
to return to the original configuration. Safety defaults (UID/GID mapping,
log rotation) are always included.

> **Note:** Docker-Shell rewrites compose YAML with PyYAML — comments and
> custom formatting in the *main* compose file are not preserved when the
> network toggle is used (backup exists). The override file is fully owned
> by the tool.

## Requirements

- Linux, Python ≥ 3.8 with `tkinter` (`sudo apt install python3-tk`)
- Docker with Compose v2, user in the `docker` group
- Supported compose file names: `compose.yaml`, `compose.yml`,
  `docker-compose.yml`, `docker-compose.yaml`

## Install

```bash
git clone https://github.com/nixxterger/Docker_shell.git
cd Docker_shell
bash setup.sh
```

Installs to `~/.local/share/docker-shell` (venv included), adds a
`docker-shell <folder>` CLI launcher and — if Nemo is present — a
right-click action. GUI language follows the system locale (English
default, German).

Optional config in `~/.config/docker-shell/config.yml`:

```yaml
temp_leer: /path/to/custom/sacrificial/folder
```

## Tests

```bash
python3 tests/test_e2e.py   # needs Docker; uses a throwaway alpine container
```

## License

MIT
