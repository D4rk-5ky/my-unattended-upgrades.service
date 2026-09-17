# Commented code map

This file maps the current 0.0.2 code and shipped service commands to their purpose and safety role.

## `mqtt-power-action.py`

The paho-mqtt import is optional at process startup. This lets `--help` and intentionally skipped dry-run MQTT paths run without paho; `publish_mqtt_payload()` returns a clear missing-package failure before any real MQTT publish attempt.

### Constants

- `PROJECT_VERSION` identifies the packaged code release.
- `STATUS_JOB_NAME` supplies the stable JSON `job` value consumed by Home Assistant.
- `STATUS_STDERR_LIMIT` caps the MQTT `stderr` field at the last 4000 characters so a failure report cannot grow without bound.
- `DEPRECATED_MQTT_OPTIONS` is the explicit set of 0.0.1 MQTT keys that now cause a configuration error. Rejecting them prevents silent fallback to removed semantics.

### `config_error(message)`

Prints a consistent `CONFIG ERROR` message and exits with code 2. All invalid configuration is rejected before external MQTT/mail/power work when possible.

### `get_str(config, section, option, default=None, required=False)`

Reads and strips an INI string. It centralizes missing-section, missing-option, and empty-required-value checks so individual features do not implement inconsistent validation.

### `get_int(config, section, option, default=None, required=False)`

Uses `get_str()` and converts the result to an integer. Invalid integers become a controlled configuration error rather than a traceback.

### `get_float(config, section, option, default=None, required=False)`

Uses `get_str()` and converts the result to a float. It is used for delays and timeout settings.

### `get_bool(config, section, option, default=False)`

Reads standard ConfigParser boolean forms such as `true/false`, `yes/no`, and `1/0`. Invalid boolean text is rejected as configuration error.

### `get_password(value, env_var)`

Returns a directly configured password when present; otherwise reads the named environment variable. Direct values intentionally take priority. This supports secret files/environment without duplicating credential lookup for MQTT and SMTP.

### `get_config_hostname(config)`

Returns `[server] hostname`, falling back to the machine's OS hostname. It provides one canonical host label for topics, titles, client IDs, and mail.

### `make_safe_id(value)`

Normalizes arbitrary hostname/text for MQTT identifier/topic use. Unsupported characters become `-`; a non-empty fallback is guaranteed.

### `render_template(value, config)`

Expands the only supported placeholders: `{hostname}`, `{safe_hostname}`, and `{action}`. The removed `{event}` placeholder now fails validation instead of preserving the old event protocol by accident.

### `is_dry_run(config)`

Returns `[power] dry_run`. The value gates the actual power command and also activates the independent MQTT/mail `send_on_dry_run` decisions.

### `mqtt_enabled(config)`

Returns `[mqtt] enabled`, defaulting to true. It replaces the old split between a mandatory event channel and an optional JSON channel: there is now only one MQTT output.

### `get_mqtt_client_id(config)`

Returns the explicitly configured MQTT client ID or generates `mqtt-power-action-<safe hostname>` for `auto`. Custom values pass through `render_template()`.

### `build_mqtt_status_payload(...)`

Builds the only MQTT payload format. It emits compact JSON containing:

- `status`: `success` or `failure`
- `success`: boolean equivalent of status
- `title` and `name`: configured display title
- `job`: `my-unattended-upgrades`
- `exit_code`: numeric result
- `error`: short failure description or empty string
- `stderr`: bounded diagnostic text
- `warning`: non-fatal warning marker
- `skipped_datasets`: empty compatibility list

The shape intentionally mirrors the fields used by Syncerate-style Home Assistant automations.

### `load_config(path)`

Loads and validates the INI before normal external work. It verifies:

- readable config file
- `action` is `shutdown`, `reboot`, or `none`
- non-negative power delay
- removed MQTT options are absent
- required MQTT host/topic when MQTT is enabled
- topic/title/client-ID template validity
- valid MQTT port and positive MQTT timeouts
- mail backend is `sendmail` or `smtp`
- mail recipient exists when mail is enabled
- SMTP username/password source exists when SMTP mail is enabled
- valid SMTP port and positive timeout

Early validation avoids successful updates being followed by a preventable late configuration failure.

### `make_mqtt_client(client_id)`

Constructs a paho client using callback API v2 when available and falls back to the older constructor. This keeps the project compatible with common Debian/Ubuntu paho package generations.

### `reason_code_to_int(reason_code)`

Normalizes paho v1/v2 connection result representations to an integer so broker acceptance is checked consistently.

### `wait_for_publish_compatible(info, timeout)`

Waits for publish completion using the timeout-capable paho API and falls back when an older paho version does not accept the timeout keyword.

### `publish_mqtt_payload(config, topic, payload)`

Owns the actual broker connection/publish/disconnect lifecycle. It reads broker credentials/timeouts, waits for connection acknowledgement, publishes once, waits for completion, and always tears down the client loop in `finally`.

It hard-codes `qos=0` and `retain=false`. Result events must not be retained because replaying an old `success` event could incorrectly advance a Home Assistant job chain.

### `publish_mqtt_status(...)`

High-level MQTT result publisher. It:

1. returns an intentional success when MQTT is disabled;
2. while dry-run, skips broker contact unless `[mqtt] send_on_dry_run=true`;
3. builds the configured topic and JSON payload;
4. calls the single low-level publisher.

An intentional dry-run skip is not treated as a broker failure.

### `find_sendmail(path)`

Uses an explicitly configured sendmail binary when supplied, otherwise checks common absolute paths and then `PATH`. This keeps Postfix/sendmail support portable.

### `build_mail_message(config, mail_type, details)`

Builds a success/failure `EmailMessage` containing host, configured power action, dry-run state, the single MQTT status topic (or MQTT-disabled marker), diagnostic details, and optional extra body text. It contains no old MQTT event/message fields.

### `send_mail_sendmail(config, msg, mail_type)`

Runs the sendmail-compatible binary with `-t`, supplies the complete message on stdin, captures command failure details, and returns a boolean. It never decides whether a power action should continue; that remains in `main()`.

### `send_mail_smtp(config, msg, mail_type)`

Delivers the prepared message through direct SSL or normal SMTP/STARTTLS using the configured credentials and timeout. It returns true/false to the shared policy logic.

### `send_mail(config, mail_type, details)`

Applies mail dry-run delivery policy before selecting `sendmail` or `smtp`.

- normal run: dispatches to the configured backend;
- dry-run + `send_on_dry_run=false`: deliberately skips real delivery and returns success;
- dry-run + `send_on_dry_run=true`: uses the real backend.

### `run_power_action(config)`

Contains the only real system power commands.

- `none`: returns without delay/power command.
- `shutdown`: would run `systemctl poweroff`.
- `reboot`: would run `systemctl reboot`.
- `dry_run=true`: prints the intended command instead of executing it.

Keeping destructive commands in one function makes them easy to audit.

### `systemd_failure_exit_code()`

Translates systemd `EXIT_CODE`/`EXIT_STATUS` into a numeric JSON exit code. A normal process exit uses the real integer; signal/unknown forms safely fall back to 1.

### `handle_systemd_stop_post(config)`

Detects the systemd `ExecStopPost` invocation through `SERVICE_RESULT`.

- `SERVICE_RESULT=success`: returns without duplicating the already-sent success result.
- failure: emits the same MQTT JSON format with systemd result/exit diagnostics and optionally sends failure mail.
- MQTT/mail reporting is best-effort here so notification failure never hides/replaces the original update/service failure.
- this path never performs a power action.
- dry-run notification delivery rules still apply.

### `parse_args(argv=None)`

Defines the CLI. The only application argument is required `-c/--config FILE`; argparse also supplies `-h/--help`.

### `main(argv=None)`

Coordinates the normal post-upgrade path:

1. parse `-c` and validate config;
2. divert systemd `ExecStopPost` invocations to failure-only handling;
3. if configured, send success mail first;
4. if success mail fails, apply `continue_on_mail_fail` and publish MQTT failure when the failure is blocking;
5. publish the single MQTT JSON success result, carrying `warning=true` when a non-fatal mail failure was allowed;
6. apply `continue_on_mqtt_fail` if the MQTT publish itself fails;
7. with `action=none`, finish without delay or power command;
8. otherwise wait `delay_before_action` and call `run_power_action()`;
9. return a meaningful non-zero code if a real power action fails.

Mail intentionally precedes MQTT success because Home Assistant may use MQTT success as permission to start the next job. A blocking mail failure therefore cannot be followed by a misleading success event.

## `systemd/my-unattended-upgrades.service`

### Unit directives

- `Wants=network-online.target` requests network-online support because APT, MQTT, and mail can require networking.
- `After=network-online.target` orders the service after that target.

### Service directives/commands

- `Type=oneshot` means one finite upgrade operation per activation.
- `Environment=DEBIAN_FRONTEND=noninteractive` keeps package work non-interactive.
- `EnvironmentFile=-/etc/mqtt-power-action.env` optionally imports password environment variables; the leading `-` makes a missing file non-fatal.
- `ExecStartPre=/usr/bin/apt-get update` refreshes package metadata. It intentionally has no `-y` flag because update does not require one.
- `ExecStart=/usr/bin/unattended-upgrade --verbose` performs the unattended upgrade and leaves useful output in the journal.
- `ExecStartPost=/usr/local/bin/mqtt-power-action.py -c /etc/mqtt-power-action.cfg` runs only after successful start commands and handles success mail, JSON success, and optional power action.
- `ExecStopPost=/usr/local/bin/mqtt-power-action.py -c /etc/mqtt-power-action.cfg` always receives systemd result environment after the unit stops; the Python code only emits failure notification when the service result is not success.
- `Nice=10` reduces CPU priority.
- `IOSchedulingClass=idle` reduces I/O priority.

## `systemd/my-unattended-upgrades.timer`

- `OnCalendar=03:00` is the shipped example schedule.
- `Persistent=true` causes a missed run to be caught up after the machine boots again.
- `AccuracySec=1min` permits a one-minute timing window.
- `WantedBy=timers.target` is the standard enablement target for a timer.

## `scripts/ua-shutdown-on-success.sh`

This original simple fallback is preserved unchanged:

- `#!/bin/bash` selects Bash.
- `set -euo pipefail` enables strict shell error handling.
- `logger -t ua-post ...` records the intended shutdown in syslog/journal.
- `/usr/bin/systemctl poweroff` immediately powers off.

It does not implement MQTT/mail/JSON logic; the Python helper is the feature-complete path.

## Home Assistant examples

### `ha-automation-blueprint.yaml`

Despite the historical filename, this is now a plain JSON-status automation example only. It parses the single MQTT result topic, branches on `status == success/failure`, creates persistent notifications, and shows where a follow-on MQTT command can be inserted.

### `ha-automation-json-status.yaml`

Pushover-oriented JSON-status example. It reads `status`, `title`/`name`/`job`, `exit_code`, `warning`, `error`, and `stderr`, then shows a commented next-job MQTT action in the success branch.

Neither Home Assistant example consumes the removed `event` field or old MQTT message format.

## Config examples

`configs/example-config-postfix.cfg` and `configs/example-config-smtp.cfg` document every supported current option. Both intentionally default to `dry_run=true` and both `send_on_dry_run=false`, making copied example configs non-destructive and non-sending until the operator explicitly enables the desired test behavior.

## Tests

`tests/test_mqtt_power_action.py` stubs paho at import time and uses mocks/fake clients so the test suite does not need a real broker or mail server. It checks current versioning, exact JSON shape, rejection of old MQTT settings/placeholders, optional MQTT disabling, dry-run MQTT send/skip behavior, forced QoS-0/non-retained publication, dry-run mail send/skip behavior, mail-body cleanup, action-none sequencing, warning propagation, and systemd success/failure handling.
