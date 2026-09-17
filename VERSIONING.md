# VERSIONING

The project uses semantic-style incremental versions where each created release increments by exactly `0.0.1`. Rollover is `0.0.99 -> 0.1.0`, never `0.0.100`.

## 0.0.2

- Removed the old MQTT power/event payload format completely.
- Removed runtime functions that built or published `{"event": ...}` messages.
- Removed the `{event}` template placeholder.
- Replaced the two-channel MQTT model with one Syncerate-style JSON result channel.
- Renamed the active JSON settings to the normal single-channel names: `[mqtt] enabled`, `topic`, and `title`.
- Kept one shared MQTT connection/publish implementation and hard-coded result events to QoS 0 and `retain=false`.
- Made the paho-mqtt import non-fatal until an actual MQTT publish is attempted, so `--help` and dry-run paths that intentionally skip MQTT still work on systems where paho is not installed. Real MQTT publishing still reports the required `python3-paho-mqtt` package.
- Added explicit config rejection for obsolete 0.0.1 MQTT keys: `message`, `qos`, `retain`, `json_status_enabled`, `json_status_topic`, and `json_status_title`.
- Added `[mqtt] send_on_dry_run`.
  - Default `false`: no broker contact while `[power] dry_run=true`.
  - `true`: really sends JSON MQTT status while shutdown/reboot remains blocked.
- Added `[mail] send_on_dry_run` with equivalent behavior for sendmail/SMTP.
- Kept dry-run notification skips non-fatal because they are intentional operator choices.
- Added `[mqtt] enabled` so deployments can use mail/power handling without MQTT if desired.
- Updated success sequencing so configured success mail is handled before MQTT success. This ensures a blocking mail failure can produce MQTT `failure` instead of sending a premature MQTT `success` that might advance a Home Assistant sequence.
- When `continue_on_mail_fail=true`, MQTT success includes `warning=true` after a success-mail failure.
- Kept systemd `ExecStopPost` failure reporting best-effort and power-action-free.
- Updated mail bodies so they reference only the single JSON status topic and no removed event/message format.
- Added validation for negative power delay, MQTT/SMTP port range, and positive MQTT/SMTP timeout values.
- Reworked both Home Assistant examples to consume only Syncerate-style JSON status.
- Updated both config examples to document every supported option and both dry-run delivery controls.
- Updated `README.md` for current 0.0.2 behavior only.
- Updated `commented_code_map.md` to match every current function and shipped command/file behavior.
- Expanded unit coverage for removed legacy functions/options, JSON payload shape, forced non-retained QoS-0 MQTT, MQTT dry-run send/skip behavior, mail dry-run send/skip behavior, mail warning propagation, and systemd failure/success paths.

## 0.0.1

- Established the first explicit project version.
- Added a separate Syncerate-style JSON status MQTT channel alongside the original event MQTT channel.
- Added systemd `ExecStopPost` handling so failed `apt-get update`/`unattended-upgrade` executions could report JSON failure.
- Restored `action = none` as a no-power sequencing mode.
- Added `README.md`, `VERSIONING.md`, `commented_code_map.md`, updated config examples, a JSON Home Assistant example, and unit tests.
- Preserved the original MQTT event channel in this release; it was subsequently removed in 0.0.2.
