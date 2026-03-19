# CLAUDE.md — Ground Control

## Agent Identity

You are working on the **Ground Control** addon within the ha-addons repo. For agent identity (GCA) and MQTT messaging, see the parent `../CLAUDE.md`.

---

## Project Overview

Ground Control is a task and project management UI for Home Assistant. It displays a Kanban board synced with `.tasks/` markdown files.

### Key Files

| File | Purpose |
|------|---------|
| `ground-control/app/main.py` | Backend API server |
| `ground-control/frontend/` | Web UI |
| `ground-control/config.yaml` | HA addon configuration |

### Features

- Kanban board UI
- Parse/sync `.tasks/` markdown files
- Project progress tracking
- File watching for external changes

### Version

Current: **v0.1.5**

Update version in `ground-control/config.yaml` when making changes.

---

## Development Workflow

1. Make changes to addon code
2. Update version in `config.yaml`
3. Update `CHANGELOG.md` (if it exists)
4. Commit: `"Description (vX.Y.Z)"`
5. Push to trigger HA addon refresh
