# my-unattended-upgrades

Current project version: **0.0.2**

`my-unattended-upgrades` runs Debian/Ubuntu unattended upgrades under a custom systemd service, reports the result as Syncerate-style MQTT JSON, can send email, and can optionally shut down or reboot after a successful run.

Version 0.0.2 uses **one MQTT format only**. The old event/message format is removed. Every MQTT publish from this app is a non-retained QoS-0 JSON result intended for Home Assistant sequencing.

## Safety

The Python helper can run as root and can call `systemctl poweroff` or `systemctl reboot`. Test with `action = none` or `dry_run = true` before enabling a real power action.

`dry_run = true` only prevents the Python helper from executing the shutdown/reboot command. It does **not** make `apt-get update` or `unattended-upgrade` itself a dry-run.

MQTT and mail have separate `send_on_dry_run` settings. Their safe default is `false`, which prevents real network/mail delivery while the helper is in dry-run mode. Set either one to `true` when you intentionally want to test that notification channel while still blocking shutdown/reboot.

Keep MQTT and SMTP passwords out of source control. Prefer `password_env` plus the optional systemd environment file.

## Requirements

Install the core packages:

```bash
sudo apt update
sudo apt install python3-paho-mqtt unattended-upgrades
```

For local Postfix/sendmail delivery:

```bash
sudo apt install postfix
```

For manual MQTT inspection/testing:

```bash
sudo apt install mosquitto-clients
```

## Project files

```text
my-unattended-upgrades.service-0.0.2/
├── README.md
├── VERSIONING.md
├── commented_code_map.md
├── mqtt-power-action.py
├── ha-automation-blueprint.yaml
├── ha-automation-json-status.yaml
├── configs/
│   ├── example-config-postfix.cfg
│   └── example-config-smtp.cfg
├── scripts/
│   └── ua-shutdown-on-success.sh
├── systemd/
│   ├── my-unattended-upgrades.service
│   └── my-unattended-upgrades.timer
└── tests/
    └── test_mqtt_power_action.py
```

## Install the helper

Copy the Python program and make it executable:

```bash
sudo install -m 0755 mqtt-power-action.py /usr/local/bin/mqtt-power-action.py
```

Choose one example config, copy it to `/etc`, edit it, and protect it because it may contain credentials:

```bash
sudo cp configs/example-config-postfix.cfg /etc/mqtt-power-action.cfg
sudo chmod 600 /etc/mqtt-power-action.cfg
sudo nano /etc/mqtt-power-action.cfg
```

For the SMTP example instead:

```bash
sudo cp configs/example-config-smtp.cfg /etc/mqtt-power-action.cfg
sudo chmod 600 /etc/mqtt-power-action.cfg
sudo nano /etc/mqtt-power-action.cfg
```

If `password_env` is used, create the environment file referenced by the service:

```bash
sudo nano /etc/mqtt-power-action.env
sudo chmod 600 /etc/mqtt-power-action.env
```

Example contents:

```text
MQTT_PASSWORD=your-mqtt-password
GMAIL_APP_PASSWORD=your-app-password
```

## CLI

The helper intentionally has only one application option:

```text
-c FILE, --config FILE
    Required. Path to the INI configuration file.
```

Argparse also supplies standard `-h` / `--help`.

Manual config/help check:

```bash
/usr/local/bin/mqtt-power-action.py --help
/usr/local/bin/mqtt-power-action.py -c /etc/mqtt-power-action.cfg
```

A manual run executes the notification/power helper only; it does not run `apt-get update` or `unattended-upgrade` itself.

## Configuration

Both example config files contain every supported setting with comments.

### `[server]`

| Setting | Meaning |
| --- | --- |
| `hostname` | Friendly host name used in MQTT JSON/title/topic/client ID and mail. Empty means the OS hostname. |

### `[power]`

| Setting | Meaning |
| --- | --- |
| `action` | `shutdown`, `reboot`, or `none`. `none` is best for Home Assistant sequencing. |
| `delay_before_action` | Seconds to wait before shutdown/reboot. Ignored for `none`. |
| `dry_run` | When true, never execute `systemctl poweroff/reboot`. Also activates the MQTT/mail dry-run delivery gates. |
| `continue_on_mqtt_fail` | When false, a failed MQTT status publish prevents the configured power action. |
| `continue_on_mail_fail` | When false, failed success mail prevents the configured power action. When true, MQTT success is sent with `warning=true`. |

### `[mqtt]`

| Setting | Meaning |
| --- | --- |
| `enabled` | Enable/disable MQTT status reporting. Default in code is true. |
| `send_on_dry_run` | When `dry_run=true`, true allows a real broker publish; false skips it without treating the skip as failure. |
| `host` | MQTT broker host/IP. Required when MQTT is enabled. |
| `port` | Broker port, normally `1883`. |
| `username` | Optional MQTT username. |
| `password` | Optional direct password. Takes priority over `password_env`. |
| `password_env` | Name of an environment variable containing the MQTT password. |
| `topic` | The app's single result topic. Supports `{hostname}`, `{safe_hostname}`, `{action}`. |
| `title` | Value used for JSON `title` and `name`. Supports the same placeholders. |
| `client_id` | `auto` creates `mqtt-power-action-<safe hostname>`; custom values support normal placeholders. |
| `connect_timeout` | Seconds to wait for the broker connection callback. |
| `publish_timeout` | Seconds to wait for publish confirmation. |

MQTT QoS and retain are deliberately not configurable. Result events are always **QoS 0** and **retain=false** so a stale result cannot replay after Home Assistant reconnects.

The following old 0.0.1 settings are rejected: `message`, `qos`, `retain`, `json_status_enabled`, `json_status_topic`, `json_status_title`. The old `{event}` template placeholder is also removed.

### `[mail]`

| Setting | Meaning |
| --- | --- |
| `on_success` | Send success email after successful update commands. |
| `on_failure` | Send failure email on supported failure paths. |
| `send_on_dry_run` | When `dry_run=true`, true allows real email delivery; false skips delivery without treating it as failure. |
| `backend` | `sendmail` or `smtp`. |
| `to` | Recipient; required if success or failure mail is enabled. |
| `from` | Sender address. With sendmail, empty defaults to `root@<hostname>`. With SMTP, empty falls back to SMTP username. |
| `success_subject` | Success subject. Supports `{hostname}`, `{safe_hostname}`, `{action}`. |
| `failure_subject` | Failure subject with the same placeholders. |
| `extra_body` | Optional static text appended to the mail body. |

### `[smtp]`

| Setting | Meaning |
| --- | --- |
| `host` | SMTP server. |
| `port` | SMTP port. |
| `username` | SMTP login; required when SMTP mail is enabled. |
| `password` | Direct SMTP password/app password. |
| `password_env` | Environment variable containing the SMTP password. |
| `ssl` | Use direct SSL, commonly port 465. |
| `starttls` | Upgrade a normal SMTP connection using STARTTLS, commonly port 587. |
| `timeout` | SMTP connection/login/send timeout in seconds. |

### `[sendmail]`

| Setting | Meaning |
| --- | --- |
| `path` | Optional explicit sendmail-compatible binary. Empty auto-detects common paths/PATH. |

## MQTT JSON format

Example success event:

```json
{"status":"success","success":true,"title":"proxmox unattended-upgrades","name":"proxmox unattended-upgrades","job":"my-unattended-upgrades","exit_code":0,"error":"","stderr":"","warning":false,"skipped_datasets":[]}
```

Example failure event:

```json
{"status":"failure","success":false,"title":"proxmox unattended-upgrades","name":"proxmox unattended-upgrades","job":"my-unattended-upgrades","exit_code":1,"error":"my-unattended-upgrades.service failed: SERVICE_RESULT=exit-code","stderr":"SERVICE_RESULT=exit-code; EXIT_CODE=exited; EXIT_STATUS=1...","warning":false,"skipped_datasets":[]}
```

The `stderr` field is limited to the last 4000 characters. `skipped_datasets` remains an empty list for structural compatibility with Syncerate-style Home Assistant parsing.

## Dry-run notification testing

To prevent poweroff/reboot but still send MQTT JSON during a test:

```ini
[power]
dry_run = true

[mqtt]
send_on_dry_run = true
```

To also deliver real email during that same dry run:

```ini
[mail]
send_on_dry_run = true
```

To test only control flow without contacting the MQTT broker or mail backend, leave both `send_on_dry_run` settings false.

## Systemd service and timer

Install the units:

```bash
sudo cp systemd/my-unattended-upgrades.service /etc/systemd/system/
sudo cp systemd/my-unattended-upgrades.timer /etc/systemd/system/
sudo systemctl daemon-reload
```

Enable the timer:

```bash
sudo systemctl enable --now my-unattended-upgrades.timer
```

`enable --now` enables future automatic starts and starts the timer immediately; it does not immediately run the upgrade service unless the timer is due.

Check timer state:

```bash
systemctl status my-unattended-upgrades.timer --no-pager
systemctl list-timers my-unattended-upgrades.timer --all
```

Run one update job manually through systemd:

```bash
sudo systemctl start my-unattended-upgrades.service
```

Follow its journal:

```bash
journalctl -fu my-unattended-upgrades.service
```

Show the last run:

```bash
journalctl -u my-unattended-upgrades.service -n 200 --no-pager
```

The service flow is:

```text
apt-get update
    -> unattended-upgrade --verbose
        -> ExecStartPost on success
            -> optional success mail
            -> single MQTT JSON success
            -> optional shutdown/reboot

Any service/start/post-start failure
    -> ExecStopPost
        -> MQTT JSON failure (best effort)
        -> optional failure mail (best effort)
        -> no power action from ExecStopPost
```

## Optional: let this timer control APT scheduling

If you intentionally want this custom timer to be the only unattended-upgrade schedule, disable/mask the distribution's normal APT timers:

```bash
sudo systemctl disable --now apt-daily.service apt-daily.timer
sudo systemctl disable --now apt-daily-upgrade.service apt-daily-upgrade.timer
sudo systemctl mask apt-daily.service apt-daily.timer
sudo systemctl mask apt-daily-upgrade.service apt-daily-upgrade.timer
```

Check them with:

```bash
systemctl status apt-daily.timer apt-daily-upgrade.timer --no-pager
```

Only do this if you deliberately want the custom timer to own scheduling.

## Home Assistant

Use the MQTT topic configured in `[mqtt] topic`, for example:

```text
homeassistant/my-unattended-upgrades/proxmox/status
```

`ha-automation-blueprint.yaml` is a simple success/failure router. `ha-automation-json-status.yaml` includes a Pushover example and a commented MQTT action showing where to start the next job after `status == "success"`.

The automations use the same fields as the Syncerate-style sequence you supplied: `status`, `title`/`name`/`job`, `exit_code`, `warning`, `error`, and `stderr`.

## Tests

Run the unit tests from the project root:

```bash
python3 -m unittest discover -s tests -v
```

Compile-check the Python file:

```bash
python3 -m py_compile mqtt-power-action.py
```

Check shell syntax:

```bash
bash -n scripts/ua-shutdown-on-success.sh
```

If systemd is available, verify the unit structure:

```bash
systemd-analyze verify systemd/my-unattended-upgrades.service systemd/my-unattended-upgrades.timer
```
