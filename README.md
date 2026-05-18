# MQTT Power Action for Unattended Upgrades

A small Linux helper project for safely shutting down or rebooting a machine after a controlled update run.

The project is designed for setups where a server runs `unattended-upgrade`, sends an MQTT message to Home Assistant, optionally sends email notifications, and finally performs a shutdown or reboot.

It is useful for homelab systems, Proxmox/Debian/Ubuntu servers, Home Assistant monitoring, and machines where you want a clear notification before the system powers off.

---

## Features

- Run a controlled `unattended-upgrade` from a custom systemd service and timer.
- Disable Ubuntu/Debian default APT daily timers if you want full control.
- Send an MQTT message before shutdown or reboot.
- Use a separate config file instead of many command-line arguments.
- Set one hostname in `[server]` and reuse it automatically in MQTT payloads, MQTT client IDs, topics, and mail subjects.
- Automatically generate MQTT payloads with `message = auto`.
- Automatically generate MQTT client IDs with `client_id = auto`.
- Optional template placeholders in config values:
  - `{hostname}`
  - `{safe_hostname}`
  - `{action}`
  - `{event}`
- Optional email on success.
- Optional email on failure.
- Email body does **not** expose the MQTT broker hostname/IP or port.
- Supports local `sendmail`/Postfix.
- Supports SMTP, including Gmail App Password style login.
- Supports Home Assistant MQTT automations.
- Supports retained MQTT messages and clearing retained messages after Home Assistant receives them.
- Includes a dry-run mode for safer testing.

---

## ⚠️ Disclaimer: Use At Your Own Risk

This project is provided **as-is**, without warranty, support guarantee, or any promise that it will work correctly on your system.

By using this script, service file, configuration, or any part of this project, you accept full responsibility for anything that happens.

The author is **not responsible** for:

- Data loss
- Failed upgrades
- Broken package states
- Failed shutdowns or reboots
- Network lockouts
- Firewall or routing mistakes
- MQTT misconfiguration
- Mail delivery failures
- Home Assistant automation mistakes
- Downtime
- Security issues caused by incorrect configuration
- Any direct or indirect damage caused by running this project

This project may run commands as root and may shut down or reboot your system.

Read everything before using it.

---

## User Responsibility

You are responsible for:

- Understanding the script before running it.
- Testing with `dry_run = true`.
- Using a test MQTT topic first.
- Using a test email address first.
- Checking all configuration files.
- Keeping backups.
- Keeping physical or alternative access to the machine.
- Not locking yourself out.
- Not committing passwords, tokens, or app passwords to GitHub.
- Making sure Home Assistant, MQTT, systemd, mail, and unattended-upgrades are configured correctly.

Do **not** blindly run this on an important system.

---

## Project Layout

Recommended repository layout:

```text
mqtt-power-action/
├── README.md
├── mqtt_power_action.py
├── configs/
│   ├── mqtt-power-action.smtp.example.cfg
│   └── mqtt-power-action.sendmail.example.cfg
├── systemd/
│   ├── my-unattended-upgrades.service
│   └── my-unattended-upgrades.timer
└── scripts/
    └── ua-shutdown-on-success.sh
```

You can also install the files directly under `/usr/local/bin`, `/usr/local/sbin`, and `/etc/systemd/system`.

---

## Requirements

### Required

```bash
sudo apt update
sudo apt install python3-paho-mqtt unattended-upgrades
```

### Optional for local mail with Postfix/sendmail

```bash
sudo apt install postfix
```

### Optional for manual MQTT testing

```bash
sudo apt install mosquitto-clients
```

---

## Important Configuration Concept

The recommended setup is now:

```ini
[server]
hostname = proxmox
```

Then use automatic or templated values:

```ini
[mqtt]
topic = homeassistant/{safe_hostname}/power
message = auto
client_id = auto
```

and:

```ini
[mail]
success_subject = {hostname}: {action} MQTT sent successfully
failure_subject = {hostname}: {action} MQTT or power action failed
```

This avoids editing the hostname in multiple places.

---

## Supported Template Placeholders

These placeholders can be used in supported config values such as `topic`, `client_id`, `message`, `success_subject`, and `failure_subject`.

| Placeholder | Example | Description |
|---|---:|---|
| `{hostname}` | `ubuntu-zfs-import` | The hostname from `[server] hostname`. |
| `{safe_hostname}` | `ubuntu-zfs-import` | Hostname made safe for MQTT client IDs and topics. Spaces and unusual characters are replaced. |
| `{action}` | `shutdown` or `reboot` | The value from `[power] action`. |
| `{event}` | `server_shutdown` or `server_reboot` | Automatically derived from `[power] action`. |

Example:

```ini
[server]
hostname = Ubuntu ZFS Import

[mqtt]
topic = homeassistant/{safe_hostname}/power
client_id = mqtt-power-action-{safe_hostname}
```

This would create a topic/client ID based on a safer version of the hostname, for example:

```text
homeassistant/ubuntu-zfs-import/power
mqtt-power-action-ubuntu-zfs-import
```

---

## Automatic MQTT Message

When this is configured:

```ini
[mqtt]
message = auto
```

the script automatically creates the MQTT payload.

For:

```ini
[server]
hostname = proxmox

[power]
action = shutdown
```

the generated MQTT message becomes:

```json
{"event":"server_shutdown","host":"proxmox"}
```

For:

```ini
[server]
hostname = ubuntu-zfs-import

[power]
action = reboot
```

the generated MQTT message becomes:

```json
{"event":"server_reboot","host":"ubuntu-zfs-import"}
```

You can still override the message manually if you need to:

```ini
message = {"event":"{event}","host":"{hostname}","source":"unattended-upgrades"}
```

For most setups, `message = auto` is recommended.

---

## Automatic MQTT Client ID

When this is configured:

```ini
[mqtt]
client_id = auto
```

the script automatically creates a client ID like this:

```text
mqtt-power-action-proxmox
```

or:

```text
mqtt-power-action-ubuntu-zfs-import
```

You can still override it manually:

```ini
client_id = mqtt-power-action-{safe_hostname}
```

For most setups, `client_id = auto` is recommended.

---

## Mail Output

The email body includes useful status information:

```text
Power action script status: SUCCESS

Host: ubuntu-zfs-import
Action: reboot

MQTT topic: homeassistant/ubuntu-zfs-import/power
MQTT message: {"event":"server_reboot","host":"ubuntu-zfs-import"}

Details:
MQTT message published successfully.
```

The email body intentionally does **not** include:

```text
MQTT host
MQTT port
```

This keeps broker IP/hostname and port information out of notification emails.

---

## Step 1: Disable the Default APT Daily Jobs

This is optional, but recommended if you want your own systemd timer to control when updates happen.

```bash
sudo systemctl disable --now apt-daily.service apt-daily.timer
sudo systemctl disable --now apt-daily-upgrade.service apt-daily-upgrade.timer

sudo systemctl mask apt-daily.service apt-daily.timer
sudo systemctl mask apt-daily-upgrade.service apt-daily-upgrade.timer
```

Check status:

```bash
systemctl status apt-daily.timer apt-daily-upgrade.timer
```

---

## Step 2: Configure unattended-upgrades

Edit:

```bash
sudo nano /etc/apt/apt.conf.d/50unattended-upgrades
```

Example configuration:

```text
Unattended-Upgrade::Origins-Pattern {
        "o=Ubuntu,a=noble-security";
        "o=Ubuntu,a=noble-updates";

        // WARNING:
        // This allows all origins/repositories.
        // Only use this if you understand the risk.
        "*:*";
};

Unattended-Upgrade::Automatic-Reboot "false";

Unattended-Upgrade::AutofixInterruptedDpkg "true";
Unattended-Upgrade::MinimalSteps "true";

Unattended-Upgrade::Mail "your@email.com";
Unattended-Upgrade::MailReport "always";

Unattended-Upgrade::Remove-Unused-Kernel-Packages "true";
Unattended-Upgrade::Remove-New-Unused-Dependencies "true";
Unattended-Upgrade::Remove-Unused-Dependencies "true";
```

### Important Note About `*:*`

This line:

```text
"*:*";
```

means unattended-upgrades may upgrade packages from all enabled repositories.

That can include third-party repositories and PPAs. This is convenient, but more risky than security-only updates.

Safer example:

```text
Unattended-Upgrade::Origins-Pattern {
        "o=Ubuntu,a=noble-security";
        "o=Ubuntu,a=noble-updates";
};
```

---

## Step 3: Install the MQTT Power Action Script

Copy the script into:

```bash
sudo nano /usr/local/bin/mqtt_power_action.py
```

Make it executable:

```bash
sudo chmod +x /usr/local/bin/mqtt_power_action.py
```

The script should be started like this:

```bash
sudo /usr/local/bin/mqtt_power_action.py -c /etc/mqtt-power-action.cfg
```

All settings are stored in the config file.

---

## Step 4: Create the Config File

Create:

```bash
sudo nano /etc/mqtt-power-action.cfg
```

---

## Full Config Reference

### `[server]`

| Option | Required | Example | Description |
|---|---:|---|---|
| `hostname` | No | `proxmox` | Friendly hostname used in MQTT payloads, client IDs, topics, and mail subjects. If omitted, the OS hostname is used. |

### `[power]`

| Option | Required | Example | Description |
|---|---:|---|---|
| `action` | Yes | `shutdown` | Must be `shutdown` or `reboot`. |
| `delay_before_action` | No | `10` | Seconds to wait after MQTT/mail before shutdown/reboot. |
| `dry_run` | No | `true` | If `true`, only prints the power command instead of running it. |
| `continue_on_mqtt_fail` | No | `false` | If `false`, aborts shutdown/reboot when MQTT publish fails. |
| `continue_on_mail_fail` | No | `false` | If `false`, aborts shutdown/reboot when success mail fails. |

### `[mqtt]`

| Option | Required | Example | Description |
|---|---:|---|---|
| `host` | Yes | `10.0.0.10` | MQTT broker hostname or IP. |
| `port` | No | `1883` | MQTT broker port. |
| `username` | No | `hass` | MQTT username. Leave empty if not used. |
| `password` | No | `secret` | MQTT password. Avoid storing this in Git. |
| `password_env` | No | `MQTT_PASSWORD` | Environment variable containing the MQTT password. Recommended. |
| `topic` | Yes | `homeassistant/{safe_hostname}/power` | MQTT topic. Supports placeholders. |
| `message` | Yes | `auto` | `auto` creates JSON with `event` and `host`. Supports placeholders if manually set. |
| `client_id` | No | `auto` | `auto` creates a safe client ID from the hostname. Supports placeholders if manually set. |
| `qos` | No | `1` | MQTT QoS. Must be `0`, `1`, or `2`. |
| `retain` | No | `false` | Whether the MQTT message should be retained. Usually `false` for trigger topics. |
| `connect_timeout` | No | `10` | Seconds to wait for MQTT connection. |
| `publish_timeout` | No | `10` | Seconds to wait for MQTT publish completion. |

### `[mail]`

| Option | Required | Example | Description |
|---|---:|---|---|
| `on_success` | No | `true` | Send mail after successful MQTT publish. |
| `on_failure` | No | `true` | Send mail when MQTT or power action fails. |
| `backend` | No | `smtp` | `smtp` or `sendmail`. |
| `to` | Required if mail enabled | `receiver@example.com` | Mail recipient. |
| `from` | No | `root@proxmox.local` | Mail sender. If SMTP and empty, the SMTP username is used. |
| `success_subject` | No | `{hostname}: {action} MQTT sent successfully` | Subject for success mail. Supports placeholders. |
| `failure_subject` | No | `{hostname}: {action} MQTT or power action failed` | Subject for failure mail. Supports placeholders. |
| `extra_body` | No | `Sent by mqtt_power_action.py` | Extra text appended to the email body. |

### `[smtp]`

Only used when:

```ini
[mail]
backend = smtp
```

| Option | Required | Example | Description |
|---|---:|---|---|
| `host` | No | `smtp.gmail.com` | SMTP server. |
| `port` | No | `587` | SMTP port. |
| `username` | Yes for SMTP | `yourgmail@gmail.com` | SMTP username. |
| `password` | No | `app-password` | SMTP password. Avoid storing this in Git. |
| `password_env` | No | `GMAIL_APP_PASSWORD` | Environment variable containing the SMTP password. Recommended. |
| `ssl` | No | `false` | Use direct SSL/TLS SMTP. Usually false for Gmail port 587. |
| `starttls` | No | `true` | Use STARTTLS. Usually true for Gmail port 587. |
| `timeout` | No | `20` | SMTP timeout in seconds. |

### `[sendmail]`

Only used when:

```ini
[mail]
backend = sendmail
```

| Option | Required | Example | Description |
|---|---:|---|---|
| `path` | No | `/usr/sbin/sendmail` | Optional sendmail binary path. Leave empty for auto-detect. |

---

## Example Config: SMTP / Gmail Style Mail

```ini
[server]
hostname = ubuntu-zfs-import


[power]
# shutdown or reboot
action = reboot

# Wait after MQTT and mail before doing the power action
delay_before_action = 10

# Keep this true until you have tested everything
dry_run = true

# If MQTT fails, default is to abort shutdown/reboot
continue_on_mqtt_fail = false

# If success mail fails, default is to abort shutdown/reboot
continue_on_mail_fail = false


[mqtt]
host = 10.0.0.10
port = 1883

# Optional MQTT login
username = hass

# Avoid storing real passwords in this file when possible
password =
password_env = MQTT_PASSWORD

# Recommended dynamic topic
topic = homeassistant/{safe_hostname}/power

# Recommended automatic JSON payload:
# {"event":"server_reboot","host":"ubuntu-zfs-import"}
message = auto

# Recommended automatic client ID:
# mqtt-power-action-ubuntu-zfs-import
client_id = auto

qos = 1

# Recommended:
# false for trigger topics.
# Use Home Assistant to store the last command on another retained topic if needed.
retain = false

connect_timeout = 10
publish_timeout = 10


[mail]
on_success = true
on_failure = true

# sendmail or smtp
backend = smtp

to = receiver@example.com
from = yourgmail@gmail.com

success_subject = {hostname}: {action} MQTT sent successfully
failure_subject = {hostname}: {action} MQTT or power action failed

extra_body = This message was sent by mqtt_power_action.py before the power action.


[smtp]
host = smtp.gmail.com
port = 587

username = yourgmail@gmail.com

# Prefer environment variable instead of saving the app password here.
password =
password_env = GMAIL_APP_PASSWORD

ssl = false
starttls = true
timeout = 20


[sendmail]
# Only used when [mail] backend = sendmail
path =
```

Run with environment variables:

```bash
export MQTT_PASSWORD='your-mqtt-password'
export GMAIL_APP_PASSWORD='your-gmail-app-password'

sudo --preserve-env=MQTT_PASSWORD,GMAIL_APP_PASSWORD \
  /usr/local/bin/mqtt_power_action.py -c /etc/mqtt-power-action.cfg
```

---

## Example Config: Local Postfix/sendmail

```ini
[server]
hostname = proxmox


[power]
action = reboot
delay_before_action = 10
dry_run = true
continue_on_mqtt_fail = false
continue_on_mail_fail = false


[mqtt]
host = 10.0.0.10
port = 1883
username =
password =
password_env =

topic = homeassistant/{safe_hostname}/power
message = auto
client_id = auto

qos = 1
retain = false
connect_timeout = 10
publish_timeout = 10


[mail]
on_success = true
on_failure = true
backend = sendmail

to = receiver@example.com
from = root@proxmox.local

success_subject = {hostname}: {action} MQTT sent successfully
failure_subject = {hostname}: {action} MQTT or power action failed

extra_body = Sent from local sendmail/Postfix.


[sendmail]
path =
```

---

## Step 5: Test the Script Safely

Make sure the config contains:

```ini
dry_run = true
```

Then run:

```bash
sudo --preserve-env=MQTT_PASSWORD,GMAIL_APP_PASSWORD \
  /usr/local/bin/mqtt_power_action.py -c /etc/mqtt-power-action.cfg
```

Expected behavior in dry-run mode:

```text
MQTT message published successfully.
Success mail sent using SMTP.
DRY-RUN: Would run: systemctl reboot
```

or:

```text
DRY-RUN: Would run: systemctl poweroff
```

Only change this when everything works:

```ini
dry_run = false
```

---

## Step 6: Create a Custom unattended-upgrades Service

Create:

```bash
sudo nano /etc/systemd/system/my-unattended-upgrades.service
```

Example:

```ini
[Unit]
Description=Run unattended-upgrades under custom control
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
Environment=DEBIAN_FRONTEND=noninteractive

# If you use password_env values with systemd, add them here
# or use an EnvironmentFile.
# Environment=MQTT_PASSWORD=change-me
# Environment=GMAIL_APP_PASSWORD=change-me

# Better option:
# EnvironmentFile=/etc/mqtt-power-action.env

# Refresh package cache first
ExecStartPre=/usr/bin/apt-get update -y

# Run unattended-upgrade
ExecStart=/usr/bin/unattended-upgrade --verbose

# Run MQTT/mail/shutdown script after unattended-upgrade exits successfully
ExecStartPost=/usr/local/bin/mqtt_power_action.py -c /etc/mqtt-power-action.cfg

Nice=10
IOSchedulingClass=idle
```

Reload systemd:

```bash
sudo systemctl daemon-reload
```

Manual test:

```bash
sudo systemctl start my-unattended-upgrades.service
```

Check logs:

```bash
journalctl -u my-unattended-upgrades.service -n 100 --no-pager
```

---

## Optional: Environment File for Secrets

Instead of putting passwords in the config file, create:

```bash
sudo nano /etc/mqtt-power-action.env
```

Example:

```bash
MQTT_PASSWORD='your-mqtt-password'
GMAIL_APP_PASSWORD='your-gmail-app-password'
```

Protect it:

```bash
sudo chown root:root /etc/mqtt-power-action.env
sudo chmod 600 /etc/mqtt-power-action.env
```

Then use it in the systemd service:

```ini
[Service]
EnvironmentFile=/etc/mqtt-power-action.env
```

This is cleaner than putting secrets directly in the config.

---

## Step 7: Create the systemd Timer

Create:

```bash
sudo nano /etc/systemd/system/my-unattended-upgrades.timer
```

Example: run daily at 03:00.

```ini
[Unit]
Description=Schedule custom unattended-upgrades

[Timer]
OnCalendar=03:00
Persistent=true
AccuracySec=1min

[Install]
WantedBy=timers.target
```

Enable it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now my-unattended-upgrades.timer
```

Check it:

```bash
systemctl list-timers --all | grep unattended
```

---

## Alternative: Simple Shutdown Script

If you do not want MQTT or mail, use a simple script instead.

Create:

```bash
sudo nano /usr/local/sbin/ua-shutdown-on-success.sh
```

```bash
#!/bin/bash
set -euo pipefail

logger -t ua-post "Unattended-upgrades finished successfully; shutting down"

/usr/bin/systemctl poweroff
```

Make executable:

```bash
sudo chmod +x /usr/local/sbin/ua-shutdown-on-success.sh
```

Then use this in the service instead:

```ini
ExecStartPost=/usr/local/sbin/ua-shutdown-on-success.sh
```

---

## Home Assistant: Listen for the MQTT Message

In Home Assistant:

```text
Settings → Devices & services → MQTT → Configure → Listen to a topic
```

Listen to your dynamic topic:

```text
homeassistant/ubuntu-zfs-import/power
```

or to all matching server power topics:

```text
homeassistant/+/power
```

or to everything:

```text
#
```

Manual test from Linux:

```bash
mosquitto_pub \
  -h 10.0.0.10 \
  -t "homeassistant/ubuntu-zfs-import/power" \
  -m '{"event":"server_reboot","host":"ubuntu-zfs-import"}'
```

---

## Home Assistant Automation: Web UI and Phone App Notifications

This automation sends:

- A persistent notification in the Home Assistant web UI.
- A push notification to the Home Assistant mobile app.
- Optional handling for multiple servers by using a wildcard topic.
- Optional storing of the last payload on a retained `/last` topic.

Replace:

```yaml
notify.mobile_app_your_phone_name
```

with your real mobile notify service.

Find it in:

```text
Developer Tools → Actions → search for notify.mobile_app
```

Example automation for dynamic topics:

```yaml
alias: Server power MQTT router
description: Different HA actions for shutdown and reboot

triggers:
  - trigger: mqtt
    topic: homeassistant/+/power

conditions:
  # Ignore empty payloads.
  # This is needed if you clear a retained MQTT message after receiving it.
  - condition: template
    value_template: "{{ trigger.payload | trim != '' }}"

actions:
  - variables:
      server_host: "{{ trigger.payload_json.host | default('unknown-host') }}"
      server_event: "{{ trigger.payload_json.event | default('unknown-event') }}"

  - choose:
      - conditions:
          - condition: template
            value_template: "{{ server_event == 'server_shutdown' }}"
        sequence:
          - action: persistent_notification.create
            data:
              title: Server shutting down
              message: "{{ server_host }} is shutting down."
              notification_id: "server_power_{{ server_host }}"

          - action: notify.mobile_app_your_phone_name
            data:
              title: Server shutting down
              message: "{{ server_host }} is shutting down."

      - conditions:
          - condition: template
            value_template: "{{ server_event == 'server_reboot' }}"
        sequence:
          - action: persistent_notification.create
            data:
              title: Server rebooting
              message: "{{ server_host }} is rebooting."
              notification_id: "server_power_{{ server_host }}"

          - action: notify.mobile_app_your_phone_name
            data:
              title: Server rebooting
              message: "{{ server_host }} is rebooting."

    default:
      - action: persistent_notification.create
        data:
          title: Unknown server MQTT event
          message: "{{ trigger.payload }}"
          notification_id: "server_power_unknown"

      - action: notify.mobile_app_your_phone_name
        data:
          title: Unknown server MQTT event
          message: "{{ trigger.payload }}"

  # Optional:
  # Store last message on a separate retained topic.
  # This does not re-trigger the automation because it uses /last.
  - action: mqtt.publish
    data:
      topic: "homeassistant/{{ server_host }}/power/last"
      payload: "{{ trigger.payload }}"
      retain: true
      qos: 0
```

---

## Notify All Phones in Home Assistant

If you want to notify all Home Assistant mobile apps, create a notify group in Home Assistant.

Example:

```yaml
notify:
  - platform: group
    name: all_phones
    services:
      - service: mobile_app_phone_1
      - service: mobile_app_phone_2
```

Then use:

```yaml
- action: notify.all_phones
  data:
    title: Server rebooting
    message: "{{ server_host }} is rebooting."
```

You can still keep `persistent_notification.create` for the Home Assistant web UI.

---

## Recommended MQTT Retain Setup

For shutdown/reboot commands, the safest setup is usually:

```text
homeassistant/<server>/power       = trigger topic, not retained
homeassistant/<server>/power/last  = last known command, retained
```

Example:

```text
homeassistant/proxmox/power
homeassistant/proxmox/power/last
```

Why?

If the trigger topic is retained, Home Assistant may receive an old shutdown/reboot command again after restart.

Then your script should usually use:

```ini
retain = false
```

on the actual trigger topic.

---

## Clearing a Retained MQTT Message

If you need to clear a retained message manually:

```bash
mosquitto_pub \
  -h 10.0.0.10 \
  -t "homeassistant/proxmox/power" \
  -r \
  -n
```

Meaning:

```text
-r = publish as retained
-n = empty/null payload
```

---

## Security Notes

### Do Not Commit Secrets

Never commit real values like this to GitHub:

```ini
password = real-password
password = real-gmail-app-password
```

Use environment variables instead:

```ini
password_env = MQTT_PASSWORD
password_env = GMAIL_APP_PASSWORD
```

### Rotate Exposed App Passwords

If you accidentally pasted or committed a Gmail App Password, MQTT password, token, or other secret, consider it compromised.

Delete/rotate it before continuing.

### Protect Config Files

If you store secrets in the config file anyway, restrict permissions:

```bash
sudo chown root:root /etc/mqtt-power-action.cfg
sudo chmod 600 /etc/mqtt-power-action.cfg
```

If you use an environment file:

```bash
sudo chown root:root /etc/mqtt-power-action.env
sudo chmod 600 /etc/mqtt-power-action.env
```

### Test Before Enabling Shutdown/Reboot

Always test with:

```ini
dry_run = true
```

Then change to:

```ini
dry_run = false
```

only after MQTT, mail, and Home Assistant notifications work.

---

## Troubleshooting

### MQTT Message Is Not Seen in Home Assistant

Check:

- Is Home Assistant connected to the same MQTT broker?
- Is the topic exactly the same?
- If using dynamic topics, are you listening to `homeassistant/+/power`?
- Is the MQTT username/password correct?
- Is the broker IP correct?
- Is `retain = false` or `retain = true` doing what you expect?

Test with:

```bash
mosquitto_sub -h 10.0.0.10 -t 'homeassistant/+/power' -v
```

Then publish:

```bash
mosquitto_pub \
  -h 10.0.0.10 \
  -t 'homeassistant/test-server/power' \
  -m '{"event":"server_shutdown","host":"test-server"}'
```

---

### Home Assistant Automation Does Not Fire

Check the automation trigger:

```yaml
triggers:
  - trigger: mqtt
    topic: homeassistant/+/power
```

The `topic` should be directly under the MQTT trigger.

Also check the automation trace in Home Assistant:

```text
Settings → Automations & scenes → Your automation → Traces
```

---

### Web UI Notification Works, but Phone Does Not

`persistent_notification.create` only creates a Home Assistant web UI notification.

For phone push notifications, you need your mobile app notify service:

```yaml
action: notify.mobile_app_your_phone_name
```

Find it here:

```text
Developer Tools → Actions → search for notify.mobile_app
```

Or use a notify group:

```yaml
action: notify.all_phones
```

---

### Gmail SMTP Does Not Work

Check:

- You are using an App Password, not your normal Gmail password.
- 2-Step Verification is enabled on the Google account.
- `host = smtp.gmail.com`
- `port = 587`
- `starttls = true`
- `ssl = false`
- `from` matches the Gmail account or is allowed by Gmail.
- `password_env = GMAIL_APP_PASSWORD` is exported or provided by the systemd service.

Check environment variables when testing manually:

```bash
echo "$GMAIL_APP_PASSWORD"
```

Do not paste the real value into GitHub issues or screenshots.

---

### `password_env` Works Manually but Not from systemd

If this works:

```bash
export GMAIL_APP_PASSWORD='your-password'
sudo --preserve-env=GMAIL_APP_PASSWORD /usr/local/bin/mqtt_power_action.py -c /etc/mqtt-power-action.cfg
```

but fails from systemd, then systemd does not have that environment variable.

Use an environment file:

```ini
[Service]
EnvironmentFile=/etc/mqtt-power-action.env
```

Then reload and test:

```bash
sudo systemctl daemon-reload
sudo systemctl start my-unattended-upgrades.service
journalctl -u my-unattended-upgrades.service -n 100 --no-pager
```

---

### The Mail Subject Does Not Show the Hostname

Use template placeholders:

```ini
success_subject = {hostname}: {action} MQTT sent successfully
failure_subject = {hostname}: {action} MQTT or power action failed
```

Make sure `[server] hostname` is set:

```ini
[server]
hostname = proxmox
```

---

### The MQTT Message Has the Wrong Host

Use:

```ini
[server]
hostname = proxmox

[mqtt]
message = auto
```

Do not hardcode the old hostname in `message`.

---

### The MQTT Client ID Still Shows the Old Host

Use:

```ini
[mqtt]
client_id = auto
```

or:

```ini
client_id = mqtt-power-action-{safe_hostname}
```

---

### Mail Shows MQTT Broker Host/IP or Port

The updated script should not include MQTT broker host/IP or port in the mail body.

The mail body should show only:

```text
MQTT topic
MQTT message
```

If it still shows:

```text
MQTT host
MQTT port
```

then the script file has not been updated yet.

---

### Script Shuts Down Even When Nothing Was Upgraded

`ExecStartPost=` runs when the service command exits successfully.

If you only want shutdown/reboot when packages were actually upgraded, handle that logic in a wrapper script or use unattended-upgrades hook behavior carefully.

For many homelab setups, a scheduled update-and-shutdown action is acceptable, but be aware of this behavior.

---

### I Want Reboot Instead of Shutdown

Change:

```ini
[power]
action = reboot
```

---

### I Want Shutdown Instead of Reboot

Change:

```ini
[power]
action = shutdown
```

---

## Safe Testing Checklist

Before using this for real:

- [ ] Config file exists.
- [ ] `[server] hostname` is correct.
- [ ] `dry_run = true`.
- [ ] `message = auto` creates the expected MQTT payload.
- [ ] `client_id = auto` creates the expected client ID.
- [ ] Mail subjects use the correct hostname.
- [ ] Mail body does not expose MQTT broker host/IP or port.
- [ ] MQTT message appears in Home Assistant MQTT listener.
- [ ] Home Assistant automation triggers correctly.
- [ ] Web UI persistent notification appears.
- [ ] Mobile app notification appears, if enabled.
- [ ] Success email works.
- [ ] Failure email works.
- [ ] `journalctl` logs look correct.
- [ ] Physical or alternative access to the machine exists.
- [ ] Backups exist.
- [ ] No real passwords are committed to GitHub.
- [ ] Change `dry_run = false` only when ready.

---

## Example Run

```bash
sudo --preserve-env=MQTT_PASSWORD,GMAIL_APP_PASSWORD \
  /usr/local/bin/mqtt_power_action.py -c /etc/mqtt-power-action.cfg
```

Expected successful dry-run output:

```text
MQTT message published successfully.
Success mail sent using SMTP.
DRY-RUN: Would run: systemctl reboot
```

---

## Final Warning

This project can shut down or reboot a real machine.

Use it carefully.

Test first.

Keep backups.

Do not run it blindly as root.
