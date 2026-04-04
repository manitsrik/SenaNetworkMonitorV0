# Plugin Development Guide

This document describes the current Plugin System MVP in `NW Monitor`.

## Overview

The current plugin system supports:

- Local plugin loading from the `plugins/` directory
- Monitor plugins with `monitor_type = plugin:<plugin_id>`
- Integration plugins for alert delivery extensions
- Dynamic configuration forms from `config_schema`
- Server-side validation before settings are saved

Current implementation entry points:

- Loader and validator: [plugin_manager.py](/C:/Project/NW%20MonitorV0/plugin_manager.py)
- Sample monitor plugin: [plugins/tcp_banner/manifest.json](/C:/Project/NW%20MonitorV0/plugins/tcp_banner/manifest.json)
- Sample integration plugin: [plugins/jsonl_alert_sink/manifest.json](/C:/Project/NW%20MonitorV0/plugins/jsonl_alert_sink/manifest.json)
- Sample webhook integration plugin: [plugins/generic_webhook/manifest.json](/C:/Project/NW%20MonitorV0/plugins/generic_webhook/manifest.json)

## Folder Layout

Each plugin lives under its own folder inside `plugins/`.

Example:

```text
plugins/
  tcp_banner/
    manifest.json
    plugin.py
  jsonl_alert_sink/
    manifest.json
    plugin.py
  generic_webhook/
    manifest.json
    plugin.py
```

Required files:

- `manifest.json`
- `plugin.py`

## Manifest Contract

Minimum manifest:

```json
{
  "id": "my_plugin",
  "name": "My Plugin",
  "version": "0.1.0",
  "type": "monitor",
  "monitor_type": "plugin:my_plugin",
  "enabled": true,
  "description": "Short description"
}
```

Supported manifest fields right now:

- `id`: unique plugin id
- `name`: display name
- `version`: plugin version string
- `type`: `monitor` or `integration`
- `monitor_type`: value stored on devices, usually `plugin:<id>` for monitor plugins
- `enabled`: whether the plugin can be used
- `description`: human-readable summary
- `ui_hint`: optional UI hint
- `config_schema`: optional array describing runtime config fields

## Python Contract

`plugin.py` must expose a class named `Plugin`.

For monitor plugins:

```python
class Plugin:
    def check(self, device, context):
        return {
            "status": "up",
            "response_time": 12.5,
            "message": "OK"
        }
```

For integration plugins:

```python
class Plugin:
    def send(self, payload, config, context=None):
        return {
            "success": True,
            "message": "Delivered"
        }
```

Useful monitor inputs:

- `device`: device record from database, including `plugin_config`
- `context["db"]`: database instance
- `context["monitor"]`: active `NetworkMonitor`
- `context["config"]`: app config class

Useful integration inputs:

- `payload`: normalized alert payload with subject, message, event type, timestamp, and optional device
- `config`: validated runtime config from the Plugins page
- `context["is_test"]`: whether this was triggered by Send Test

## Config Schema

`config_schema` is used by the Devices UI and Plugins UI to render plugin-specific fields.

Supported field types:

- `text`
- `number`
- `boolean`
- `select`
- `secret`

Supported validation properties:

- `required`
- `min` and `max` for numeric fields
- `pattern` for regex-based text validation
- `format: "url"` for HTTP/HTTPS URLs

Example:

```json
{
  "config_schema": [
    {
      "key": "expected_banner",
      "label": "Expected Banner",
      "type": "text",
      "required": false
    },
    {
      "key": "match_mode",
      "label": "Match Mode",
      "type": "select",
      "default": "contains",
      "options": [
        { "label": "Contains", "value": "contains" },
        { "label": "Exact", "value": "exact" }
      ]
    },
    {
      "key": "read_banner",
      "label": "Read Banner",
      "type": "boolean",
      "default": true
    }
  ]
}
```

## Validation Behavior

Validation happens server-side before a device or integration plugin setting is saved.

Current validation checks:

- required fields must be present
- number fields must parse successfully
- number fields can enforce `min` and `max`
- select fields must match one of the allowed options
- text fields can enforce `pattern`
- URL fields can enforce `format: "url"`

For integration plugins, fields with `type: "secret"` are stored separately from the main JSON config. The UI will show whether a secret is already stored and allows replacing or clearing it without returning the secret value to the browser.

Validation is implemented in [plugin_manager.py](/C:/Project/NW%20MonitorV0/plugin_manager.py).

## How To Add a New Plugin

1. Create a folder under `plugins/`
2. Add `manifest.json`
3. Add `plugin.py` with a `Plugin` class
4. Set `type` to `monitor` or `integration`
5. For monitor plugins, set `monitor_type` to `plugin:<your_id>`
6. Reload plugins from the Plugins page or call `POST /api/plugins/reload`
7. For monitor plugins, choose the plugin in the Devices form
8. For integration plugins, configure runtime settings in the Plugins page

## Example Behavior

The sample monitor plugin `tcp_banner`:

- connects to a TCP port
- optionally reads a banner
- can compare banner text using `contains` or `exact`

The sample integration plugin `jsonl_alert_sink`:

- receives alert payloads from the alerter
- writes each event to a local JSONL file
- supports per-plugin runtime config from the Plugins page

The sample integration plugin `generic_webhook`:

- sends alert payloads to an arbitrary HTTP endpoint
- supports POST and PUT
- supports bearer auth, optional extra header, timeout, retry/backoff, and TLS verification

Reference files:

- [plugins/tcp_banner/manifest.json](/C:/Project/NW%20MonitorV0/plugins/tcp_banner/manifest.json)
- [plugins/tcp_banner/plugin.py](/C:/Project/NW%20MonitorV0/plugins/tcp_banner/plugin.py)
- [plugins/jsonl_alert_sink/manifest.json](/C:/Project/NW%20MonitorV0/plugins/jsonl_alert_sink/manifest.json)
- [plugins/jsonl_alert_sink/plugin.py](/C:/Project/NW%20MonitorV0/plugins/jsonl_alert_sink/plugin.py)
- [plugins/generic_webhook/manifest.json](/C:/Project/NW%20MonitorV0/plugins/generic_webhook/manifest.json)
- [plugins/generic_webhook/plugin.py](/C:/Project/NW%20MonitorV0/plugins/generic_webhook/plugin.py)

## Current Limits

This is still an MVP.

Not implemented yet:

- plugin sandboxing
- dependency isolation
- hot unload safety
- per-plugin permission model
- UI-side validation messages by field

## Recommended Next Steps

- Add UI validation for required and numeric fields
- Add dedicated secret storage separate from plain JSON config
- Add packaging and version compatibility rules
- Add more integration plugin examples
