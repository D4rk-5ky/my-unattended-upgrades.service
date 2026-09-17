#!/usr/bin/env python3
"""MQTT/mail notification and optional power action for my-unattended-upgrades."""

import argparse
import configparser
import json
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

PROJECT_VERSION = "0.0.2"
STATUS_JOB_NAME = "my-unattended-upgrades"
STATUS_STDERR_LIMIT = 4000
DEPRECATED_MQTT_OPTIONS = (
    "message",
    "qos",
    "retain",
    "json_status_enabled",
    "json_status_topic",
    "json_status_title",
)

try:
    import paho.mqtt.client as mqtt
except ImportError:
    mqtt = None


def config_error(message: str):
    """Print a configuration error and terminate with exit code 2."""
    print(f"CONFIG ERROR: {message}")
    sys.exit(2)


def get_str(config, section, option, default=None, required=False):
    """Read a stripped string option, honoring defaults and required values."""
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
    """Read an integer option and turn invalid values into a config error."""
    value = get_str(config, section, option, default=None, required=required)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        config_error(f"Option '{option}' in section [{section}] must be an integer")


def get_float(config, section, option, default=None, required=False):
    """Read a floating-point option and turn invalid values into a config error."""
    value = get_str(config, section, option, default=None, required=required)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        config_error(f"Option '{option}' in section [{section}] must be a number")


def get_bool(config, section, option, default=False):
    """Read a configparser boolean option."""
    if not config.has_section(section) or not config.has_option(section, option):
        return default
    try:
        return config.getboolean(section, option)
    except ValueError:
        config_error(
            f"Option '{option}' in section [{section}] must be true/false, yes/no, or 1/0"
        )


def get_password(value: str | None, env_var: str | None) -> str | None:
    """Resolve a password from the direct value first, then from an environment variable."""
    if value:
        return value
    if env_var:
        return os.environ.get(env_var)
    return None


def get_config_hostname(config) -> str:
    """Return configured friendly hostname, falling back to the OS hostname."""
    configured_hostname = get_str(config, "server", "hostname", default="")
    return configured_hostname or socket.gethostname()


def make_safe_id(value: str) -> str:
    """Make text safe for generated MQTT client IDs and topic path components."""
    safe = ""
    for char in value.strip().lower():
        safe += char if (char.isalnum() or char in ["-", "_"]) else "-"
    safe = safe.strip("-_")
    return safe or "unknown-host"


def render_template(value: str, config) -> str:
    """Render supported placeholders in MQTT topics/titles, client IDs, and mail subjects."""
    hostname = get_config_hostname(config)
    safe_hostname = make_safe_id(hostname)
    action = get_str(config, "power", "action", required=True)

    try:
        return value.format(
            hostname=hostname,
            safe_hostname=safe_hostname,
            action=action,
        )
    except KeyError as exc:
        config_error(f"Unknown placeholder in config value: {{{exc.args[0]}}}")
    except Exception as exc:
        config_error(f"Failed to render config template '{value}': {exc}")


def is_dry_run(config) -> bool:
    """Return the helper dry-run setting used by power and notification delivery gates."""
    return get_bool(config, "power", "dry_run", default=False)


def mqtt_enabled(config) -> bool:
    """Return whether the single Syncerate-style MQTT JSON status channel is enabled."""
    return get_bool(config, "mqtt", "enabled", default=True)


def get_mqtt_client_id(config) -> str:
    """Build the configured or automatic MQTT client ID."""
    hostname = get_config_hostname(config)
    safe_hostname = make_safe_id(hostname)
    configured_client_id = get_str(config, "mqtt", "client_id", default="auto")

    if configured_client_id.lower() == "auto" or configured_client_id.strip() == "":
        return f"mqtt-power-action-{safe_hostname}"
    return render_template(configured_client_id, config)


def build_mqtt_status_payload(
    config,
    *,
    success: bool,
    exit_code: int,
    error_message: str = "",
    stderr_text: str = "",
    warning: bool = False,
) -> str:
    """Build the only MQTT payload format: compact Syncerate-compatible JSON status."""
    title_template = get_str(
        config,
        "mqtt",
        "title",
        default="{hostname} unattended-upgrades",
    )
    title = render_template(title_template, config)
    bounded_stderr = (stderr_text or "")[-STATUS_STDERR_LIMIT:]
    payload = {
        "status": "success" if success else "failure",
        "success": bool(success),
        "title": title,
        "name": title,
        "job": STATUS_JOB_NAME,
        "exit_code": int(exit_code),
        "error": error_message or "",
        "stderr": bounded_stderr,
        "warning": bool(warning),
        "skipped_datasets": [],
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def load_config(path: str):
    """Load and validate all settings before MQTT, mail, or power actions are attempted."""
    config = configparser.ConfigParser(interpolation=None)
    files_read = config.read(path)
    if not files_read:
        config_error(f"Could not read config file: {path}")

    action = get_str(config, "power", "action", required=True)
    if action not in ["shutdown", "reboot", "none"]:
        config_error("[power] action must be shutdown, reboot, or none")

    # Validate numeric values early even if they will be skipped for action=none/dry-run.
    delay_before_action = get_float(config, "power", "delay_before_action", default=1.0)
    if delay_before_action < 0:
        config_error("[power] delay_before_action cannot be negative")

    if config.has_section("mqtt"):
        for option in DEPRECATED_MQTT_OPTIONS:
            if config.has_option("mqtt", option):
                config_error(
                    f"[mqtt] {option} is obsolete in 0.0.2; only the JSON status format is supported"
                )

    if mqtt_enabled(config):
        get_str(config, "mqtt", "host", required=True)
        render_template(get_str(config, "mqtt", "topic", required=True), config)
        render_template(
            get_str(config, "mqtt", "title", default="{hostname} unattended-upgrades"),
            config,
        )
        get_mqtt_client_id(config)
        port = get_int(config, "mqtt", "port", default=1883)
        if port < 1 or port > 65535:
            config_error("[mqtt] port must be between 1 and 65535")
        if get_float(config, "mqtt", "connect_timeout", default=10.0) <= 0:
            config_error("[mqtt] connect_timeout must be greater than 0")
        if get_float(config, "mqtt", "publish_timeout", default=10.0) <= 0:
            config_error("[mqtt] publish_timeout must be greater than 0")

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
            config_error(
                "[smtp] password or password_env is required when [mail] backend = smtp"
            )
        smtp_port = get_int(config, "smtp", "port", default=587)
        if smtp_port < 1 or smtp_port > 65535:
            config_error("[smtp] port must be between 1 and 65535")
        if get_float(config, "smtp", "timeout", default=20.0) <= 0:
            config_error("[smtp] timeout must be greater than 0")

    return config


def make_mqtt_client(client_id: str | None):
    """Create a paho client compatible with both paho-mqtt v1 and v2."""
    if mqtt is None:
        raise RuntimeError(
            "Missing paho-mqtt. Install with: sudo apt install python3-paho-mqtt"
        )
    try:
        return mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id or "",
        )
    except (AttributeError, TypeError):
        return mqtt.Client(client_id=client_id or "")


def reason_code_to_int(reason_code) -> int:
    """Normalize paho v1/v2 reason-code objects to an integer return code."""
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
    """Wait for publish completion across paho versions with different call signatures."""
    try:
        info.wait_for_publish(timeout=timeout)
    except TypeError:
        info.wait_for_publish()


def publish_mqtt_payload(
    config,
    *,
    topic: str,
    payload: str,
) -> tuple[bool, str]:
    """Connect and publish one non-retained QoS-0 JSON status payload."""
    if mqtt is None:
        return False, (
            "Missing paho-mqtt. Install with: sudo apt install python3-paho-mqtt"
        )

    host = get_str(config, "mqtt", "host", required=True)
    port = get_int(config, "mqtt", "port", default=1883)
    username = get_str(config, "mqtt", "username", default="")
    password = get_str(config, "mqtt", "password", default="")
    password_env = get_str(config, "mqtt", "password_env", default="")
    connect_timeout = get_float(config, "mqtt", "connect_timeout", default=10.0)
    publish_timeout = get_float(config, "mqtt", "publish_timeout", default=10.0)
    client_id = get_mqtt_client_id(config)
    real_password = get_password(password, password_env)

    connected_event = threading.Event()
    connect_result = {"rc": None}
    client = make_mqtt_client(client_id)

    if username:
        client.username_pw_set(username, real_password)

    def on_connect(client, userdata, flags, reason_code, properties=None):
        connect_result["rc"] = reason_code_to_int(reason_code)
        connected_event.set()

    client.on_connect = on_connect

    try:
        client.connect(host, port, keepalive=30)
        client.loop_start()

        if not connected_event.wait(connect_timeout):
            return False, "Timed out waiting for MQTT connection."
        if connect_result["rc"] != 0:
            return False, f"MQTT broker rejected connection. RC={connect_result['rc']}"

        # Run-result events must never be retained; a stale success/failure event could
        # otherwise replay when Home Assistant reconnects and incorrectly advance a chain.
        info = client.publish(topic, payload=payload, qos=0, retain=False)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            return False, f"MQTT publish failed. RC={info.rc}"

        wait_for_publish_compatible(info, publish_timeout)
        if not info.is_published():
            return False, "MQTT publish timed out."
        return True, f"MQTT JSON status published successfully to {topic}."
    except Exception as exc:
        return False, f"MQTT publish failed: {exc}"
    finally:
        try:
            client.disconnect()
            client.loop_stop()
        except Exception:
            pass


def publish_mqtt_status(
    config,
    *,
    success: bool,
    exit_code: int,
    error_message: str = "",
    stderr_text: str = "",
    warning: bool = False,
) -> tuple[bool, str]:
    """Publish the single JSON status channel, respecting enable and dry-run delivery settings."""
    if not mqtt_enabled(config):
        return True, "MQTT JSON status is disabled."

    if is_dry_run(config) and not get_bool(
        config, "mqtt", "send_on_dry_run", default=False
    ):
        return True, "DRY-RUN: MQTT JSON status not sent (send_on_dry_run=false)."

    topic = render_template(get_str(config, "mqtt", "topic", required=True), config)
    payload = build_mqtt_status_payload(
        config,
        success=success,
        exit_code=exit_code,
        error_message=error_message,
        stderr_text=stderr_text,
        warning=warning,
    )
    return publish_mqtt_payload(config, topic=topic, payload=payload)


def find_sendmail(path: str | None) -> str | None:
    """Locate a configured or common sendmail-compatible binary."""
    if path:
        return path
    for possible_path in ["/usr/sbin/sendmail", "/usr/bin/sendmail"]:
        if os.path.exists(possible_path):
            return possible_path
    return shutil.which("sendmail")


def build_mail_message(config, mail_type: str, details: str) -> EmailMessage:
    """Build the plain-text success/failure email for the current JSON-status workflow."""
    hostname = get_config_hostname(config)
    action = get_str(config, "power", "action", required=True)
    backend = get_str(config, "mail", "backend", default="sendmail")
    mail_to = get_str(config, "mail", "to", required=True)
    mail_from = get_str(config, "mail", "from", default="")
    extra_body = get_str(config, "mail", "extra_body", default="")

    if mqtt_enabled(config):
        mqtt_topic = render_template(get_str(config, "mqtt", "topic", required=True), config)
    else:
        mqtt_topic = "(MQTT disabled)"

    if not mail_from and backend == "smtp":
        mail_from = get_str(config, "smtp", "username", default="")
    if not mail_from:
        mail_from = f"root@{hostname}"

    if mail_type == "success":
        subject = get_str(
            config,
            "mail",
            "success_subject",
            default="{hostname}: unattended-upgrades succeeded",
        )
    else:
        subject = get_str(
            config,
            "mail",
            "failure_subject",
            default="{hostname}: unattended-upgrades failed",
        )
    subject = render_template(subject, config)

    body = f"""my-unattended-upgrades status: {mail_type.upper()}

Host: {hostname}
Action: {action}
Dry run: {'yes' if is_dry_run(config) else 'no'}
MQTT status topic: {mqtt_topic}

Details:
{details}
"""
    if extra_body:
        body += f"\nExtra info:\n{extra_body}\n"

    msg = EmailMessage()
    msg["From"] = mail_from
    msg["To"] = mail_to
    msg["Subject"] = subject
    msg.set_content(body)
    return msg


def send_mail_sendmail(config, msg: EmailMessage, mail_type: str) -> bool:
    """Send an EmailMessage through local sendmail/Postfix."""
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
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode(errors="replace").strip() if exc.stderr else ""
        print(
            f"ERROR: Failed to send {mail_type} mail using sendmail. "
            f"Exit code: {exc.returncode}"
        )
        if stderr:
            print(stderr)
        return False
    except Exception as exc:
        print(f"ERROR: Failed to send {mail_type} mail using sendmail: {exc}")
        return False


def send_mail_smtp(config, msg: EmailMessage, mail_type: str) -> bool:
    """Send an EmailMessage directly through SMTP with SSL or STARTTLS."""
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
    except Exception as exc:
        print(f"ERROR: Failed to send {mail_type} mail using SMTP: {exc}")
        return False


def send_mail(config, mail_type: str, details: str) -> bool:
    """Send configured mail, or intentionally skip it in dry-run mode."""
    if is_dry_run(config) and not get_bool(
        config, "mail", "send_on_dry_run", default=False
    ):
        print(f"DRY-RUN: {mail_type.capitalize()} mail not sent (send_on_dry_run=false).")
        return True

    backend = get_str(config, "mail", "backend", default="sendmail")
    msg = build_mail_message(config, mail_type, details)
    if backend == "sendmail":
        return send_mail_sendmail(config, msg, mail_type)
    if backend == "smtp":
        return send_mail_smtp(config, msg, mail_type)
    print(f"ERROR: Unknown mail backend: {backend}")
    return False


def run_power_action(config):
    """Run shutdown/reboot, or explicitly do nothing for action=none."""
    action = get_str(config, "power", "action", required=True)

    if action == "none":
        print("Power action is 'none'; skipping shutdown/reboot.")
        return
    if action == "shutdown":
        command = ["systemctl", "poweroff"]
    elif action == "reboot":
        command = ["systemctl", "reboot"]
    else:
        raise ValueError(f"Unknown action: {action}")

    if is_dry_run(config):
        print(f"DRY-RUN: Would run: {' '.join(command)}")
        return

    print(f"Running: {' '.join(command)}")
    subprocess.run(command, check=True)


def systemd_failure_exit_code() -> int:
    """Translate systemd ExecStopPost EXIT_CODE/EXIT_STATUS into a useful numeric JSON code."""
    exit_code_kind = os.environ.get("EXIT_CODE", "")
    exit_status = os.environ.get("EXIT_STATUS", "")
    if exit_code_kind == "exited":
        try:
            return int(exit_status)
        except (TypeError, ValueError):
            pass
    return 1


def handle_systemd_stop_post(config) -> bool:
    """Best-effort failure reporting when invoked by systemd as ExecStopPost.

    systemd supplies SERVICE_RESULT/EXIT_CODE/EXIT_STATUS only to stop/post-stop commands.
    Returning True tells main() that this invocation is status-only and must never run a
    normal success path, delay, or power action.
    """
    if "SERVICE_RESULT" not in os.environ:
        return False

    service_result = os.environ.get("SERVICE_RESULT", "unknown")
    if service_result == "success":
        print("ExecStopPost: service completed successfully; no failure status needed.")
        return True

    exit_code_kind = os.environ.get("EXIT_CODE", "unknown")
    exit_status = os.environ.get("EXIT_STATUS", "unknown")
    code = systemd_failure_exit_code()
    error_message = (
        f"my-unattended-upgrades.service failed: SERVICE_RESULT={service_result}"
    )
    stderr_text = (
        f"SERVICE_RESULT={service_result}; EXIT_CODE={exit_code_kind}; "
        f"EXIT_STATUS={exit_status}. Check journalctl -u my-unattended-upgrades.service "
        "for the full apt/unattended-upgrade output."
    )

    status_ok, status_details = publish_mqtt_status(
        config,
        success=False,
        exit_code=code,
        error_message=error_message,
        stderr_text=stderr_text,
    )
    print(status_details)
    if not status_ok:
        # ExecStopPost reporting is intentionally best-effort so it never replaces the
        # original service failure with an MQTT reporting failure.
        print("ERROR: Could not publish MQTT JSON failure status; preserving original service failure.")

    if get_bool(config, "mail", "on_failure", default=False):
        mail_ok = send_mail(config, "failure", f"{error_message}\n{stderr_text}")
        if not mail_ok:
            print("ERROR: Could not send failure mail; preserving original service failure.")
    return True


def parse_args(argv=None):
    """Parse the only application option: the required config-file path."""
    parser = argparse.ArgumentParser(
        description=(
            "Publish Syncerate-style MQTT JSON status after unattended-upgrades, "
            "optionally send mail, and optionally shut down or reboot."
        )
    )
    parser.add_argument(
        "-c",
        "--config",
        required=True,
        help="Path to the INI configuration file.",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    """Run normal post-upgrade handling or systemd ExecStopPost failure reporting."""
    args = parse_args(argv)
    config = load_config(args.config)

    if handle_systemd_stop_post(config):
        return 0

    mail_on_success = get_bool(config, "mail", "on_success", default=False)
    mail_on_failure = get_bool(config, "mail", "on_failure", default=False)
    continue_on_mqtt_fail = get_bool(
        config, "power", "continue_on_mqtt_fail", default=False
    )
    continue_on_mail_fail = get_bool(
        config, "power", "continue_on_mail_fail", default=False
    )
    delay_before_action = get_float(
        config, "power", "delay_before_action", default=1.0
    )
    action = get_str(config, "power", "action", required=True)

    # Mail runs before the success MQTT event so Home Assistant receives success only after
    # all configured blocking notification work has passed its failure policy.
    mail_warning = False
    if mail_on_success:
        mail_ok = send_mail(
            config,
            "success",
            "apt-get update and unattended-upgrade completed successfully.",
        )
        if not mail_ok:
            mail_warning = True
            details = "Success mail failed after unattended-upgrades completed."
            if mail_on_failure:
                send_mail(config, "failure", details)
            if not continue_on_mail_fail:
                status_ok, status_details = publish_mqtt_status(
                    config,
                    success=False,
                    exit_code=1,
                    error_message=details,
                    stderr_text=details,
                )
                print(status_details)
                print("Aborting power action because success mail failed.")
                return 1
            print("WARNING: Continuing because continue_on_mail_fail=true.")

    status_ok, status_details = publish_mqtt_status(
        config,
        success=True,
        exit_code=0,
        warning=mail_warning,
    )
    print(status_details)
    if not status_ok:
        if mail_on_failure:
            send_mail(config, "failure", status_details)
        if not continue_on_mqtt_fail:
            print("Aborting power action because MQTT JSON status publish failed.")
            return 1
        print("WARNING: Continuing because continue_on_mqtt_fail=true.")

    # action=none is the sequencing mode: notifications are handled, but no delay or
    # systemctl power operation is performed.
    if action == "none":
        run_power_action(config)
        return 0

    if delay_before_action > 0:
        time.sleep(delay_before_action)

    try:
        run_power_action(config)
    except subprocess.CalledProcessError as exc:
        details = f"Power action failed with exit code {exc.returncode}"
        print(f"ERROR: {details}")
        if mail_on_failure:
            send_mail(config, "failure", details)
        # Under systemd, ExecStopPost will publish the final failure JSON using the real
        # service result. A manual invocation still returns the non-zero power-action code.
        return exc.returncode or 1
    except Exception as exc:
        details = f"Power action failed: {exc}"
        print(f"ERROR: {details}")
        if mail_on_failure:
            send_mail(config, "failure", details)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
