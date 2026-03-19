# Home Assistant Addons

Custom Home Assistant addons and integrations for music visualization and task management.

## Addons

| Addon | Version | Description |
|-------|---------|-------------|
| [Lyric Scroll](lyric-scroll/) | v0.5.16 | Synchronized, scrolling karaoke-style lyrics for Music Assistant. Supports casting to Chromecast/Nest Hub. |
| [Ground Control](ground-control/) | v0.1.6 | Task and project management Kanban board, synced with `.tasks/` markdown files. |
| [Lumberjacker](lumberjacker/) | v0.1.0 | HA log watcher that triages and prioritizes log issues for action. |

## Custom Integration

| Integration | Description |
|-------------|-------------|
| [Ground Control](custom_components/ground_control/) | HA sensors and services for Ground Control task management. Exposes task counts, project progress, and services to create/move/complete tasks. |

## Installation

### Addons

Add this repository to Home Assistant:

1. Go to **Settings > Add-ons > Add-on Store**
2. Click the three dots menu (top right) > **Repositories**
3. Add: `https://github.com/loydmilligan/ha-addons`
4. Find and install the addon you want

### Ground Control Integration (HACS)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=loydmilligan&repository=ha-addons&category=integration)

Or manually:

1. Open HACS in Home Assistant
2. Click the three dots menu > **Custom repositories**
3. Add `https://github.com/loydmilligan/ha-addons` as **Integration**
4. Search for "Ground Control" and install
5. Restart Home Assistant
6. Go to **Settings > Integrations > Add Integration > Ground Control**

## Development

This repo uses a Claude Code agent (**GCA**) that coordinates with **Major Tom** (running in Home Assistant) via MQTT messaging. See `.claude/sync/README.md` for protocol details.

## License

MIT
