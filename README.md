# MQTT Power Action for Unattended Upgrades

A small Linux helper project for safely shutting down or rebooting a machine after a controlled update run.

The project is designed for setups where a server runs `unattended-upgrade`, then sends an MQTT message, optionally sends email notifications, and finally performs a shutdown or reboot.

It is useful for homelab systems, Proxmox/Debian/Ubuntu servers, Home Assistant monitoring, and machines where you want clear notification before the system powers off.

---

## Features

- Run a controlled `unattended-upgrade` from a custom systemd service and timer.
- Disable Ubuntu/Debian default APT daily timers if you want full control.
- Send an MQTT message before shutdown or reboot.
- Use a separate config file instead of many command-line arguments.
- Optional email on success.
- Optional email on failure.
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

- Understanding the script before running it
- Testing with `dry_run = true`
- Using a test MQTT topic first
- Using a test email address first
- Checking all configuration files
- Keeping backups
- Keeping physical or alternative access to the machine
- Not locking yourself out
- Not committing passwords, tokens, or app passwords to GitHub
- Making sure Home Assistant, MQTT, systemd, mail, and unattended-upgrades are configured correctly

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

### Important note about `*:*`

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

## Example Config: SMTP / Gmail Style Mail

```ini
[power]
# shutdown or reboot
action = shutdown

# Wait after MQTT and mail before doing the power action
delay_before_action = 1

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
username = mqttuser

# Avoid storing real passwords in this file when possible
# password = mqttpassword
password_env = MQTT_PASSWORD

topic = homeassistant/server/power
message = {"event":"server_shutdown","host":"proxmox"}

client_id = mqtt-power-action-proxmox
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

success_subject = Proxmox shutdown MQTT sent successfully
failure_subject = Proxmox shutdown MQTT or power action failed

extra_body = This message was sent by mqtt_power_action.py before the power action.


[smtp]
host = smtp.gmail.com
port = 587

username = yourgmail@gmail.com

# Prefer environment variable instead of saving the app password here.
# password = your-gmail-app-password
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
[power]
action = reboot
delay_before_action = 1
dry_run = true
continue_on_mqtt_fail = false
continue_on_mail_fail = false


[mqtt]
host = 10.0.0.10
port = 1883
username =
password =
password_env =
topic = homeassistant/server/power
message = {"event":"server_reboot","host":"proxmox"}
client_id = mqtt-power-action-proxmox
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
success_subject = Reboot MQTT sent successfully
failure_subject = Reboot MQTT or power action failed
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
DRY-RUN: Would run: systemctl poweroff
```

or:

```text
DRY-RUN: Would run: systemctl reboot
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

Listen to your topic:

```text
homeassistant/server/power
```

or to everything:

```text
#
```

Manual test from Linux:

```bash
mosquitto_pub \
  -h 10.0.0.10 \
  -t "homeassistant/server/power" \
  -m '{"event":"server_shutdown","host":"proxmox"}'
```

---

## Home Assistant Automation: Web UI and Phone App Notifications

This automation sends:

- A persistent notification in the Home Assistant web UI
- A push notification to the Home Assistant mobile app
- Optionally clears the retained message after receiving it

Replace:

```yaml
notify.mobile_app_your_phone_name
```

with your real mobile notify service.

Find it in:

```text
Developer Tools → Actions → search for notify.mobile_app
```

Example automation:

```yaml
alias: Server power MQTT router
description: Different HA actions for shutdown and reboot

triggers:
  - trigger: mqtt
    topic: homeassistant/server/power

conditions:
  # Ignore empty payloads.
  # This is needed if you clear a retained MQTT message after receiving it.
  - condition: template
    value_template: "{{ trigger.payload | trim != '' }}"

actions:
  - choose:
      - conditions:
          - condition: template
            value_template: "{{ trigger.payload_json.event == 'server_shutdown' }}"
        sequence:
          - action: persistent_notification.create
            data:
              title: Server shutting down
              message: "{{ trigger.payload_json.host }} is shutting down."
              notification_id: "server_power_{{ trigger.payload_json.host }}"

          - action: notify.mobile_app_your_phone_name
            data:
              title: Server shutting down
              message: "{{ trigger.payload_json.host }} is shutting down."

      - conditions:
          - condition: template
            value_template: "{{ trigger.payload_json.event == 'server_reboot' }}"
        sequence:
          - action: persistent_notification.create
            data:
              title: Server rebooting
              message: "{{ trigger.payload_json.host }} is rebooting."
              notification_id: "server_power_{{ trigger.payload_json.host }}"

          - action: notify.mobile_app_your_phone_name
            data:
              title: Server rebooting
              message: "{{ trigger.payload_json.host }} is rebooting."

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
  # Clear retained message on the trigger topic.
  # Only needed if your script publishes with retain = true.
  - action: mqtt.publish
    data:
      topic: homeassistant/server/power/last
      payload: "{{ trigger.payload }}"
      retain: true
      qos: 0
```

---

## Recommended MQTT Retain Setup

For shutdown/reboot commands, the safest setup is usually:

```text
homeassistant/server/power       = trigger topic, not retained
homeassistant/server/power/last  = last known command, retained
```

Why?

If the trigger topic is retained, Home Assistant may receive an old shutdown/reboot command again after restart.

Then your script should use:

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
  -t "homeassistant/server/power" \
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

### Do not commit secrets

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

### Protect config files

If you store secrets in the config file anyway, restrict permissions:

```bash
sudo chown root:root /etc/mqtt-power-action.cfg
sudo chmod 600 /etc/mqtt-power-action.cfg
```

### Test before enabling shutdown/reboot

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

### MQTT message is not seen in Home Assistant

Check:

- Is Home Assistant connected to the same MQTT broker?
- Is the topic exactly the same?
- Is the MQTT username/password correct?
- Is the broker IP correct?
- Is `retain = false` or `retain = true` doing what you expect?

Test with:

```bash
mosquitto_sub -h 10.0.0.10 -t 'homeassistant/server/power' -v
```

Then publish:

```bash
mosquitto_pub \
  -h 10.0.0.10 \
  -t 'homeassistant/server/power' \
  -m '{"event":"server_shutdown","host":"test"}'
```

---

### Home Assistant automation does not fire

Check the automation trigger:

```yaml
triggers:
  - trigger: mqtt
    topic: homeassistant/server/power
```

The `topic` should be directly under the MQTT trigger.

Also check the automation trace in Home Assistant:

```text
Settings → Automations & scenes → Your automation → Traces
```

---

### Web UI notification works, but phone does not

`persistent_notification.create` only creates a Home Assistant web UI notification.

For phone push notifications, you need your mobile app notify service:

```yaml
action: notify.mobile_app_your_phone_name
```

Find it here:

```text
Developer Tools → Actions → search for notify.mobile_app
```

---

### Gmail SMTP does not work

Check:

- You are using an App Password, not your normal Gmail password.
- 2-Step Verification is enabled on the Google account.
- `host = smtp.gmail.com`
- `port = 587`
- `starttls = true`
- `ssl = false`
- `from` matches the Gmail account or is allowed by Gmail.

---

### Script shuts down even when nothing was upgraded

`ExecStartPost=` runs when the service command exits successfully.

If you only want shutdown/reboot when packages were actually upgraded, handle that logic in a wrapper script or use unattended-upgrades hook behavior carefully.

For many homelab setups, a scheduled update-and-shutdown action is acceptable, but be aware of this behavior.

---

### I want reboot instead of shutdown

Change:

```ini
[power]
action = reboot
```

---

### I want shutdown instead of reboot

Change:

```ini
[power]
action = shutdown
```

---

## Safe Testing Checklist

Before using this for real:

- [ ] Config file exists
- [ ] `dry_run = true`
- [ ] MQTT message appears in Home Assistant MQTT listener
- [ ] Home Assistant automation triggers correctly
- [ ] Web UI persistent notification appears
- [ ] Mobile app notification appears, if enabled
- [ ] Success email works
- [ ] Failure email works
- [ ] `journalctl` logs look correct
- [ ] Physical or alternative access to the machine exists
- [ ] Backups exist
- [ ] No real passwords are committed to GitHub
- [ ] Change `dry_run = false` only when ready

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
DRY-RUN: Would run: systemctl poweroff
```

---

## Final Warning

This project can shut down or reboot a real machine.

Use it carefully.

Test first.

Keep backups.

Do not run it blindly as root.
