# Project Name

Short description of what this service/script does.

## ⚠️ Disclaimer / Use At Your Own Risk

This project is provided **as-is**, without any warranty or guarantee.

By using this service, script, configuration, or any part of this project, you accept full responsibility for anything that happens on your system, network, data, hardware, or services.

The author is **not responsible** for:

- Data loss
- Broken systems
- Failed updates
- Failed shutdowns or reboots
- Network lockouts
- Firewall or routing mistakes
- Service downtime
- Misconfigured MQTT, mail, systemd, cron, or other automation
- Security issues caused by incorrect usage
- Any direct or indirect damage caused by running these scripts

These scripts may perform actions such as:

- Shutting down or rebooting a system
- Sending MQTT messages
- Sending email notifications
- Changing routing, firewall, or service behavior
- Running with elevated privileges
- Interacting with system services

You should carefully read and understand the code before running it.

## User Responsibility

You are responsible for:

- Testing the script in a safe environment first
- Making backups before use
- Verifying all configuration files
- Checking commands before running them as root
- Making sure MQTT, mail, systemd, firewall, and network settings are correct
- Understanding what the script does before using it
- Keeping your own system secure

Do **not** run this script blindly on an important system.

If you break something, lose access, lose data, or misconfigure your system, that responsibility is yours.

## Recommended Safety Steps

Before using this project:

1. Read the full script.
2. Test with harmless settings first.
3. Use a test MQTT topic.
4. Use a test email address.
5. Run manually before enabling systemd, cron, or automation.
6. Keep physical or alternative access to the machine.
7. Make sure you have backups.
8. Do not use on production systems unless you fully understand the risks.

## Root / Sudo Warning

Some parts of this project may require root privileges.

Running scripts as root can be dangerous.

A mistake in the script, configuration file, or command-line options can cause serious problems, including system shutdown, network loss, data loss, or broken services.

Only use root privileges when necessary.

## No Support Guarantee

This project is shared for personal use, learning, and experimentation.

There is no guarantee that it will work on your system.

Issues, pull requests, and suggestions are welcome, but support is not guaranteed.

## Final Warning

Use this project only if you understand the risks.

You are fully responsible for your own actions.

----

# Guide starts now

### Step 1.

Start by disabling the normal unattended-upgrades

```bash
# Stop + disable + mask Canonical’s daily APT jobs
sudo systemctl disable --now apt-daily.service apt-daily.timer
sudo systemctl disable --now apt-daily-upgrade.service apt-daily-upgrade.timer
sudo systemctl mask apt-daily.service apt-daily-upgrade.service

# Make sure APT::Periodic is not re-enabling anything
sudo sed -i 's/^\s*APT::Periodic::/#&/g' /etc/apt/apt.conf.d/20auto-upgrades
```

### Step 2

Set settings for unatended upgrades

I live dangerously so i update all package repositories
I dont automatic reboot my script does this
I remove unsued dependecies
Autofix errors
take it in small steps
I Send mail on succes
to remove kernelrelated packages. This is usually done using apt autoremove.
remove unneeded dependancies. Also manually done with apt autoremove.
remove unused packages, also, apt autoremove.

`nano /etc/apt/apt.conf.d/50unattended-upgrades`

```bash
// What to upgrade (Ubuntu + security + updates)
// Add your PPAs and vendor repos via Origins-Pattern (examples below)
Unattended-Upgrade::Origins-Pattern {
        "o=Ubuntu,a=noble-security";
        "o=Ubuntu,a=noble-updates";
        "*:*"
        // Examples for PPAs and vendor repos (adjust to your system):
        // "o=LP-PPA-graphics-drivers, a=noble";
        // "o=Google LLC";
        // "o=MariaDB Foundation";
};

// Don’t let it auto-reboot — you’ll handle shutdown yourself
Unattended-Upgrade::Automatic-Reboot "false";

// Only run our post script when packages were actually upgraded and it succeeded
Unattended-Upgrade::Post-Upgrade-Script "/usr/local/sbin/ua-post-success-shutdown.sh";

// Optional: extra safety knobs
Unattended-Upgrade::AutofixInterruptedDpkg "true";

Unattended-Upgrade::MinimalSteps "true";

Unattended-Upgrade::Mail “your@email.com”;

Unattended-Upgrade::MailReport "allways";

Unattended-Upgrade::Remove-Unused-Kernel-Packages “true”;

Unattended-Upgrade::Remove-New-Unused-Dependencies “true”;

Unattended-Upgrade::Remove-Unused-Dependencies “true”;
```

### Step 3

Create the Service

`/etc/systemd/system/my-unattended-upgrades.service`

```bash
[Unit]
Description=Run unattended-upgrades under my control
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
Environment=DEBIAN_FRONTEND=noninteractive

# Always refresh cache first
ExecStartPre=/usr/bin/apt-get update -y

# Run unattended-upgrade (safe even if nothing to upgrade)
ExecStart=/usr/bin/unattended-upgrade --verbose

# Shutdown only if UA exited 0 (success)
ExecStartPost=/usr/local/sbin/ua-shutdown-on-success.sh

# Optional niceness
Nice=10
IOSchedulingClass=idle
```

----

### Step 4

### Create timer

`/etc/systemd/system/my-unattended-upgrades.timer`

```bash
[Unit]
Description=Schedule my unattended-upgrades

[Timer]
# Example: every day at 03:00
OnCalendar=03:00
#OnCalendar=Wed 16:10

#[Timer]  
#OnBootSec=5min  
#Persistent=true  
#AccuracySec=1min

# If machine was off at 03:00, run once at next boot
Persistent=true

AccuracySec=1min

[Install]
WantedBy=timers.target
```

----

### Step 5

Create the shutdown script, it can be a simple shutdown script or the more advanced MQTT with shutdown/reboot script

Simple script

`nano /usr/local/sbin/ua-shutdown-on-success.sh`

```bash
#!/bin/bash
set -euo pipefail
logger -t ua-post "Unattended-upgrades finished successfully; shutting down"
/usr/bin/systemctl poweroff
```

----

### Step 5.1

Advanced script

```python
#!/usr/bin/env python3

import argparse
import configparser
import os
import shutil
import smtplib
import socket
import ssl
import subprocess
import sys
import threading
import time
from email.message import EmailMessage

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("ERROR: Missing paho-mqtt. Install with: sudo apt install python3-paho-mqtt")
    sys.exit(1)


def config_error(message: str):
    print(f"CONFIG ERROR: {message}")
    sys.exit(2)


def get_str(config, section, option, default=None, required=False):
    if not config.has_section(section):
        if required:
            config_error(f"Missing section [{section}]")
        return default

    if not config.has_option(section, option):
        if required:
            config_error(f"Missing option '{option}' in section [{section}]")
        return default

    value = config.get(section, option).strip()

    if required and value == "":
        config_error(f"Option '{option}' in section [{section}] cannot be empty")

    return value


def get_int(config, section, option, default=None, required=False):
    value = get_str(config, section, option, default=None, required=required)

    if value is None:
        return default

    try:
        return int(value)
    except ValueError:
        config_error(f"Option '{option}' in section [{section}] must be an integer")


def get_float(config, section, option, default=None, required=False):
    value = get_str(config, section, option, default=None, required=required)

    if value is None:
        return default

    try:
        return float(value)
    except ValueError:
        config_error(f"Option '{option}' in section [{section}] must be a number")


def get_bool(config, section, option, default=False):
    if not config.has_section(section) or not config.has_option(section, option):
        return default

    try:
        return config.getboolean(section, option)
    except ValueError:
        config_error(f"Option '{option}' in section [{section}] must be true/false, yes/no, or 1/0")


def get_password(value: str | None, env_var: str | None) -> str | None:
    if value:
        return value

    if env_var:
        return os.environ.get(env_var)

    return None


def load_config(path: str):
    config = configparser.ConfigParser(interpolation=None)

    files_read = config.read(path)

    if not files_read:
        config_error(f"Could not read config file: {path}")

    action = get_str(config, "power", "action", required=True)

    if action not in ["shutdown", "reboot"]:
        config_error("[power] action must be either shutdown or reboot")

    qos = get_int(config, "mqtt", "qos", default=1)

    if qos not in [0, 1, 2]:
        config_error("[mqtt] qos must be 0, 1, or 2")

    mail_backend = get_str(config, "mail", "backend", default="sendmail")

    if mail_backend not in ["sendmail", "smtp"]:
        config_error("[mail] backend must be either sendmail or smtp")

    mail_on_success = get_bool(config, "mail", "on_success", default=False)
    mail_on_failure = get_bool(config, "mail", "on_failure", default=False)
    mail_to = get_str(config, "mail", "to", default="")

    if (mail_on_success or mail_on_failure) and not mail_to:
        config_error("[mail] to is required when on_success or on_failure is enabled")

    if (mail_on_success or mail_on_failure) and mail_backend == "smtp":
        smtp_username = get_str(config, "smtp", "username", default="")
        smtp_password = get_str(config, "smtp", "password", default="")
        smtp_password_env = get_str(config, "smtp", "password_env", default="")

        if not smtp_username:
            config_error("[smtp] username is required when [mail] backend = smtp")

        if not smtp_password and not smtp_password_env:
            config_error("[smtp] password or password_env is required when [mail] backend = smtp")

    return config


def make_mqtt_client(client_id: str | None):
    """
    Compatible with paho-mqtt v1 and v2.
    """
    try:
        return mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id or "",
        )
    except (AttributeError, TypeError):
        return mqtt.Client(client_id=client_id or "")


def reason_code_to_int(reason_code) -> int:
    try:
        return int(reason_code)
    except Exception:
        pass

    if hasattr(reason_code, "value"):
        try:
            return int(reason_code.value)
        except Exception:
            pass

    if str(reason_code).lower() in ["success", "0"]:
        return 0

    return 1


def wait_for_publish_compatible(info, timeout: float):
    try:
        info.wait_for_publish(timeout=timeout)
    except TypeError:
        info.wait_for_publish()


def publish_mqtt(config) -> tuple[bool, str]:
    host = get_str(config, "mqtt", "host", required=True)
    port = get_int(config, "mqtt", "port", default=1883)
    username = get_str(config, "mqtt", "username", default="")
    password = get_str(config, "mqtt", "password", default="")
    password_env = get_str(config, "mqtt", "password_env", default="")
    topic = get_str(config, "mqtt", "topic", required=True)
    message = get_str(config, "mqtt", "message", required=True)
    client_id = get_str(config, "mqtt", "client_id", default="mqtt-power-action")
    qos = get_int(config, "mqtt", "qos", default=1)
    retain = get_bool(config, "mqtt", "retain", default=False)
    connect_timeout = get_float(config, "mqtt", "connect_timeout", default=10.0)
    publish_timeout = get_float(config, "mqtt", "publish_timeout", default=10.0)

    real_password = get_password(password, password_env)

    connected_event = threading.Event()
    connect_result = {"rc": None}

    client = make_mqtt_client(client_id)

    if username:
        client.username_pw_set(username, real_password)

    def on_connect(client, userdata, flags, reason_code, properties=None):
        rc = reason_code_to_int(reason_code)
        connect_result["rc"] = rc
        connected_event.set()

    client.on_connect = on_connect

    try:
        client.connect(host, port, keepalive=30)
        client.loop_start()

        if not connected_event.wait(connect_timeout):
            return False, "Timed out waiting for MQTT connection."

        if connect_result["rc"] != 0:
            return False, f"MQTT broker rejected connection. RC={connect_result['rc']}"

        info = client.publish(
            topic,
            payload=message,
            qos=qos,
            retain=retain,
        )

        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            return False, f"MQTT publish failed. RC={info.rc}"

        wait_for_publish_compatible(info, publish_timeout)

        if not info.is_published():
            return False, "MQTT publish timed out."

        return True, "MQTT message published successfully."

    except Exception as e:
        return False, f"MQTT publish failed: {e}"

    finally:
        try:
            client.disconnect()
            client.loop_stop()
        except Exception:
            pass


def find_sendmail(path: str | None) -> str | None:
    if path:
        return path

    for possible_path in ["/usr/sbin/sendmail", "/usr/bin/sendmail"]:
        if os.path.exists(possible_path):
            return possible_path

    return shutil.which("sendmail")


def build_mail_message(config, mail_type: str, details: str) -> EmailMessage:
    hostname = socket.gethostname()

    action = get_str(config, "power", "action", required=True)

    mqtt_host = get_str(config, "mqtt", "host", default="")
    mqtt_port = get_int(config, "mqtt", "port", default=1883)
    mqtt_topic = get_str(config, "mqtt", "topic", default="")
    mqtt_message = get_str(config, "mqtt", "message", default="")

    backend = get_str(config, "mail", "backend", default="sendmail")
    mail_to = get_str(config, "mail", "to", required=True)
    mail_from = get_str(config, "mail", "from", default="")
    extra_body = get_str(config, "mail", "extra_body", default="")

    if not mail_from and backend == "smtp":
        mail_from = get_str(config, "smtp", "username", default="")

    if not mail_from:
        mail_from = f"root@{hostname}"

    if mail_type == "success":
        subject = get_str(
            config,
            "mail",
            "success_subject",
            default=f"SUCCESS: MQTT before {action} on {hostname}",
        )
    else:
        subject = get_str(
            config,
            "mail",
            "failure_subject",
            default=f"FAILURE: MQTT/power action on {hostname}",
        )

    body = f"""Power action script status: {mail_type.upper()}

Host: {hostname}
Action: {action}

MQTT host: {mqtt_host}
MQTT port: {mqtt_port}
MQTT topic: {mqtt_topic}
MQTT message: {mqtt_message}

Details:
{details}
"""

    if extra_body:
        body += f"""

Extra info:
{extra_body}
"""

    msg = EmailMessage()
    msg["From"] = mail_from
    msg["To"] = mail_to
    msg["Subject"] = subject
    msg.set_content(body)

    return msg


def send_mail_sendmail(config, msg: EmailMessage, mail_type: str) -> bool:
    sendmail_path = get_str(config, "sendmail", "path", default="")
    sendmail_bin = find_sendmail(sendmail_path)

    if not sendmail_bin:
        print("ERROR: Could not find sendmail. Install postfix or set [sendmail] path.")
        return False

    try:
        subprocess.run(
            [sendmail_bin, "-t"],
            input=msg.as_bytes(),
            check=True,
            capture_output=True,
        )

        print(f"{mail_type.capitalize()} mail sent using sendmail.")
        return True

    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode(errors="replace") if e.stderr else ""
        print(f"ERROR: Failed to send {mail_type} mail using sendmail. Exit code: {e.returncode}")

        if stderr:
            print(stderr)

        return False

    except Exception as e:
        print(f"ERROR: Failed to send {mail_type} mail using sendmail: {e}")
        return False


def send_mail_smtp(config, msg: EmailMessage, mail_type: str) -> bool:
    host = get_str(config, "smtp", "host", default="smtp.gmail.com")
    port = get_int(config, "smtp", "port", default=587)
    username = get_str(config, "smtp", "username", required=True)
    password = get_str(config, "smtp", "password", default="")
    password_env = get_str(config, "smtp", "password_env", default="")
    use_ssl = get_bool(config, "smtp", "ssl", default=False)
    use_starttls = get_bool(config, "smtp", "starttls", default=True)
    timeout = get_float(config, "smtp", "timeout", default=20.0)

    real_password = get_password(password, password_env)

    if not real_password:
        print("ERROR: SMTP password missing. Set [smtp] password or password_env.")
        return False

    try:
        if use_ssl:
            context = ssl.create_default_context()

            with smtplib.SMTP_SSL(host, port, timeout=timeout, context=context) as server:
                server.login(username, real_password)
                server.send_message(msg)

        else:
            with smtplib.SMTP(host, port, timeout=timeout) as server:
                server.ehlo()

                if use_starttls:
                    context = ssl.create_default_context()
                    server.starttls(context=context)
                    server.ehlo()

                server.login(username, real_password)
                server.send_message(msg)

        print(f"{mail_type.capitalize()} mail sent using SMTP.")
        return True

    except Exception as e:
        print(f"ERROR: Failed to send {mail_type} mail using SMTP: {e}")
        return False


def send_mail(config, mail_type: str, details: str) -> bool:
    backend = get_str(config, "mail", "backend", default="sendmail")
    msg = build_mail_message(config, mail_type, details)

    if backend == "sendmail":
        return send_mail_sendmail(config, msg, mail_type)

    if backend == "smtp":
        return send_mail_smtp(config, msg, mail_type)

    print(f"ERROR: Unknown mail backend: {backend}")
    return False


def run_power_action(config):
    action = get_str(config, "power", "action", required=True)
    dry_run = get_bool(config, "power", "dry_run", default=False)

    if action == "shutdown":
        command = ["systemctl", "poweroff"]
    elif action == "reboot":
        command = ["systemctl", "reboot"]
    else:
        raise ValueError(f"Unknown action: {action}")

    if dry_run:
        print(f"DRY-RUN: Would run: {' '.join(command)}")
        return

    print(f"Running: {' '.join(command)}")
    subprocess.run(command, check=True)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Send MQTT before shutdown/reboot using a config file."
    )

    parser.add_argument(
        "-c",
        "--config",
        required=True,
        help="Path to config file.",
    )

    return parser.parse_args()


def main():
    args = parse_args()
    config = load_config(args.config)

    mail_on_success = get_bool(config, "mail", "on_success", default=False)
    mail_on_failure = get_bool(config, "mail", "on_failure", default=False)

    continue_on_mqtt_fail = get_bool(config, "power", "continue_on_mqtt_fail", default=False)
    continue_on_mail_fail = get_bool(config, "power", "continue_on_mail_fail", default=False)

    delay_before_action = get_float(config, "power", "delay_before_action", default=1.0)

    mqtt_ok, mqtt_details = publish_mqtt(config)

    print(mqtt_details)

    if mqtt_ok:
        if mail_on_success:
            mail_ok = send_mail(config, "success", mqtt_details)

            if not mail_ok:
                if mail_on_failure:
                    send_mail(config, "failure", "Success mail failed after MQTT succeeded.")

                if not continue_on_mail_fail:
                    print("Aborting power action because success mail failed.")
                    sys.exit(1)

    else:
        if mail_on_failure:
            send_mail(config, "failure", mqtt_details)

        if not continue_on_mqtt_fail:
            print("Aborting power action because MQTT publish failed.")
            sys.exit(1)

    if delay_before_action > 0:
        time.sleep(delay_before_action)

    try:
        run_power_action(config)

    except subprocess.CalledProcessError as e:
        details = f"Power action failed with exit code {e.returncode}"
        print(f"ERROR: {details}")

        if mail_on_failure:
            send_mail(config, "failure", details)

        sys.exit(e.returncode)

    except Exception as e:
        details = f"Power action failed: {e}"
        print(f"ERROR: {details}")

        if mail_on_failure:
            send_mail(config, "failure", details)

        sys.exit(1)


if __name__ == "__main__":
    main()
```

### Step 5.2

The config that uses python mail

sudo nano /etc/mqtt-power-action.cfg

```config
[power]
# shutdown or reboot
action = shutdown

# Seconds to wait after MQTT/mail before shutdown/reboot
delay_before_action = 1

# Set true while testing
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
password = mqttpassword

# Better alternative:
# password_env = MQTT_PASSWORD

topic = homeassistant/server/power
message = {"event":"server_shutdown","host":"proxmox"}

client_id = mqtt-power-action-proxmox
qos = 1
retain = false

connect_timeout = 10
publish_timeout = 10


[mail]
# Enable/disable mails
on_success = true
on_failure = true

# sendmail or smtp
backend = smtp

to = receiver@example.com
from = yourgmail@gmail.com

success_subject = Proxmox shutdown MQTT sent successfully
failure_subject = Proxmox shutdown MQTT or power action failed

extra_body = This message was sent by mqtt_power_action.py before power action.


[smtp]
# Gmail SMTP
host = smtp.gmail.com
port = 587

username = yourgmail@gmail.com

# Use a Gmail App Password here, not your normal Gmail password.
# Direct password:
password = your-gmail-app-password

# Better alternative:
# password_env = GMAIL_APP_PASSWORD

ssl = false
starttls = true
timeout = 20


[sendmail]
# Only used when [mail] backend = sendmail
path =
```

### Step 5.3

The config that uses postfix

```python
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