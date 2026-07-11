# Changelog

## 1.3.0 — 2026-07-12

- **Orphaned-mask detection:** opening a container's config panel now warns
  when the project has mask entries whose host folders were deleted, and
  offers to remove them. Such entries previously made the container fail to
  start on its next recreate (Docker cannot create the mount point below a
  read-only parent mount).
- File manager integrations for **Nautilus** (script) and **Dolphin**
  (service menu), auto-installed by `setup.sh`; **Thunar** instructions in
  `integrations/thunar/`.
- `uninstall.sh`, `pyproject.toml`, GitHub Actions CI (syntax + E2E tests).

## 1.2.0 — 2026-07-11

- **⋯ menu** on both panels with a settings dialog and **Reset project**
  (deletes the override, restores the main compose file from backup).
- Settings persisted to `~/.config/docker-shell/config.yml`: window
  position, UI scale, language, add-folder naming (host path / preset /
  ask), default mode for new folders (read-only by default), network
  toggle scope (all services / selected service only).
- Custom languages via `lang/<code>.yml` files.
- `x-docker-shell` mount mapping keeps folders added under a custom
  container path resolvable across masking.
- Esc closes the window.

## 1.1.0 — 2026-07-11

- **Make permanent:** writes a folder's mount config + RAM limit into the
  main compose file so it survives override deletion / reset.
- **Remove share:** deletes a folder's mount (incl. sub-masks) from both
  the main compose file and the override, with confirmation.
- Fix: folders covered by a parent mount no longer show the "not mounted"
  banner; the status reports the inherited mode instead.
- `docs/` is local-only (gitignored).

## 1.0.0 — 2026-07-11

Initial release: Nemo right-click integration, network isolation toggle,
RAM limit, mount modes (read-write / read-only / masked / main folder
only), unmask button, on-the-fly folder adoption, XDG paths, compose file
variant support, preflight checks, English/German UI, installer, E2E test
suite.
