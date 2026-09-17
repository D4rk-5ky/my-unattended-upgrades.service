import configparser
import importlib.util
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock


# The runtime depends on paho-mqtt. These tests exercise application logic without a real
# broker, so provide the minimum import-time module stub and mock network work explicitly.
paho = types.ModuleType("paho")
paho_mqtt = types.ModuleType("paho.mqtt")
paho_client = types.ModuleType("paho.mqtt.client")
paho_client.MQTT_ERR_SUCCESS = 0
paho_mqtt.client = paho_client
paho.mqtt = paho_mqtt
sys.modules.setdefault("paho", paho)
sys.modules.setdefault("paho.mqtt", paho_mqtt)
sys.modules.setdefault("paho.mqtt.client", paho_client)

SCRIPT = Path(__file__).resolve().parents[1] / "mqtt-power-action.py"
spec = importlib.util.spec_from_file_location("mqtt_power_action", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


def config_from_text(text: str):
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read_string(text)
    return cfg


BASE_CONFIG = """
[server]
hostname = proxmox

[power]
action = none
delay_before_action = 10
dry_run = true
continue_on_mqtt_fail = false
continue_on_mail_fail = false

[mqtt]
enabled = true
send_on_dry_run = false
host = 127.0.0.1
port = 1883
username =
password =
password_env =
topic = homeassistant/my-unattended-upgrades/{safe_hostname}/status
title = {hostname} unattended-upgrades
client_id = auto
connect_timeout = 1
publish_timeout = 1

[mail]
on_success = false
on_failure = false
send_on_dry_run = false
backend = sendmail
to = receiver@example.com
from =
success_subject = {hostname}: success
failure_subject = {hostname}: failure
extra_body =

[sendmail]
path =
"""


class ConfigAndPayloadTests(unittest.TestCase):
    def write_config(self, text=BASE_CONFIG):
        handle = tempfile.NamedTemporaryFile("w", delete=False)
        handle.write(text)
        handle.close()
        self.addCleanup(lambda: os.path.exists(handle.name) and os.unlink(handle.name))
        return handle.name

    def test_project_version_is_0_0_2(self):
        self.assertEqual(module.PROJECT_VERSION, "0.0.2")

    def test_json_status_payload_matches_syncerate_shape(self):
        cfg = config_from_text(BASE_CONFIG)
        raw = module.build_mqtt_status_payload(
            cfg,
            success=False,
            exit_code=7,
            error_message="upgrade failed",
            stderr_text="x" * 5000,
            warning=False,
        )
        payload = json.loads(raw)
        self.assertEqual(
            set(payload),
            {
                "status",
                "success",
                "title",
                "name",
                "job",
                "exit_code",
                "error",
                "stderr",
                "warning",
                "skipped_datasets",
            },
        )
        self.assertEqual(payload["status"], "failure")
        self.assertFalse(payload["success"])
        self.assertEqual(payload["title"], "proxmox unattended-upgrades")
        self.assertEqual(payload["name"], payload["title"])
        self.assertEqual(payload["job"], "my-unattended-upgrades")
        self.assertEqual(payload["exit_code"], 7)
        self.assertEqual(payload["error"], "upgrade failed")
        self.assertEqual(len(payload["stderr"]), 4000)
        self.assertFalse(payload["warning"])
        self.assertEqual(payload["skipped_datasets"], [])

    def test_shipped_style_config_loads(self):
        cfg = module.load_config(self.write_config())
        self.assertEqual(module.get_str(cfg, "power", "action"), "none")
        self.assertTrue(module.mqtt_enabled(cfg))

    def test_deprecated_legacy_mqtt_message_option_is_rejected(self):
        bad = BASE_CONFIG.replace(
            "client_id = auto",
            "message = auto\nclient_id = auto",
        )
        with self.assertRaises(SystemExit) as caught:
            module.load_config(self.write_config(bad))
        self.assertEqual(caught.exception.code, 2)

    def test_deprecated_json_status_option_is_rejected(self):
        bad = BASE_CONFIG.replace(
            "title = {hostname} unattended-upgrades",
            "json_status_topic = old/topic\ntitle = {hostname} unattended-upgrades",
        )
        with self.assertRaises(SystemExit) as caught:
            module.load_config(self.write_config(bad))
        self.assertEqual(caught.exception.code, 2)

    def test_old_event_placeholder_is_rejected(self):
        bad = BASE_CONFIG.replace(
            "title = {hostname} unattended-upgrades",
            "title = {event}",
        )
        with self.assertRaises(SystemExit) as caught:
            module.load_config(self.write_config(bad))
        self.assertEqual(caught.exception.code, 2)

    def test_mqtt_can_be_disabled_without_broker_settings(self):
        text = BASE_CONFIG.replace("enabled = true", "enabled = false")
        text = text.replace("host = 127.0.0.1", "host =")
        cfg = module.load_config(self.write_config(text))
        self.assertFalse(module.mqtt_enabled(cfg))


class MqttTests(unittest.TestCase):
    def test_dry_run_skips_mqtt_by_default(self):
        cfg = config_from_text(BASE_CONFIG)
        with mock.patch.object(module, "publish_mqtt_payload") as publish:
            ok, details = module.publish_mqtt_status(cfg, success=True, exit_code=0)
        self.assertTrue(ok)
        self.assertIn("send_on_dry_run=false", details)
        publish.assert_not_called()

    def test_dry_run_can_really_send_mqtt_when_enabled(self):
        cfg = config_from_text(BASE_CONFIG.replace("send_on_dry_run = false", "send_on_dry_run = true", 1))
        with mock.patch.object(
            module, "publish_mqtt_payload", return_value=(True, "ok")
        ) as publish:
            ok, _ = module.publish_mqtt_status(cfg, success=True, exit_code=0)
        self.assertTrue(ok)
        kwargs = publish.call_args.kwargs
        self.assertEqual(kwargs["topic"], "homeassistant/my-unattended-upgrades/proxmox/status")
        payload = json.loads(kwargs["payload"])
        self.assertEqual(payload["status"], "success")

    def test_low_level_mqtt_is_forced_qos_zero_and_nonretained(self):
        cfg = config_from_text(BASE_CONFIG)

        class FakeInfo:
            rc = 0

            def wait_for_publish(self, timeout=None):
                return None

            def is_published(self):
                return True

        class FakeClient:
            def __init__(self):
                self.on_connect = None
                self.publish_call = None

            def username_pw_set(self, username, password):
                return None

            def connect(self, host, port, keepalive=30):
                self.on_connect(self, None, None, 0, None)

            def loop_start(self):
                return None

            def publish(self, topic, payload, qos, retain):
                self.publish_call = (topic, payload, qos, retain)
                return FakeInfo()

            def disconnect(self):
                return None

            def loop_stop(self):
                return None

        client = FakeClient()
        with mock.patch.object(module, "make_mqtt_client", return_value=client):
            ok, _ = module.publish_mqtt_payload(
                cfg,
                topic="homeassistant/test/status",
                payload='{"status":"success"}',
            )
        self.assertTrue(ok)
        self.assertEqual(client.publish_call[2], 0)
        self.assertFalse(client.publish_call[3])


class MailDryRunTests(unittest.TestCase):
    def test_dry_run_skips_mail_by_default(self):
        cfg = config_from_text(BASE_CONFIG.replace("on_success = false", "on_success = true"))
        with mock.patch.object(module, "send_mail_sendmail") as backend:
            ok = module.send_mail(cfg, "success", "done")
        self.assertTrue(ok)
        backend.assert_not_called()

    def test_dry_run_can_really_send_mail_when_enabled(self):
        text = BASE_CONFIG.replace("on_success = false", "on_success = true")
        # Replace the second send_on_dry_run occurrence, which belongs to [mail].
        parts = text.split("send_on_dry_run = false")
        text = "send_on_dry_run = false".join(parts[:2]) + "send_on_dry_run = true" + "send_on_dry_run = false".join(parts[2:])
        cfg = config_from_text(text)
        with mock.patch.object(module, "send_mail_sendmail", return_value=True) as backend:
            ok = module.send_mail(cfg, "success", "done")
        self.assertTrue(ok)
        backend.assert_called_once()

    def test_mail_body_contains_only_new_status_topic_reference(self):
        text = BASE_CONFIG.replace("on_success = false", "on_success = true")
        cfg = config_from_text(text)
        msg = module.build_mail_message(cfg, "success", "done")
        body = msg.get_content()
        self.assertIn("MQTT status topic: homeassistant/my-unattended-upgrades/proxmox/status", body)
        self.assertNotIn("MQTT message:", body)
        self.assertNotIn("server_shutdown", body)


class ControlFlowTests(unittest.TestCase):
    def write_config(self, text=BASE_CONFIG):
        handle = tempfile.NamedTemporaryFile("w", delete=False)
        handle.write(text)
        handle.close()
        self.addCleanup(lambda: os.path.exists(handle.name) and os.unlink(handle.name))
        return handle.name

    def test_action_none_main_uses_only_json_status_and_skips_sleep(self):
        path = self.write_config()
        with (
            mock.patch.object(
                module, "publish_mqtt_status", return_value=(True, "status ok")
            ) as status,
            mock.patch.object(module, "run_power_action") as power,
            mock.patch.object(module.time, "sleep") as sleep,
            mock.patch.dict(os.environ, {}, clear=True),
        ):
            rc = module.main(["-c", path])
        self.assertEqual(rc, 0)
        status.assert_called_once_with(
            mock.ANY,
            success=True,
            exit_code=0,
            warning=False,
        )
        power.assert_called_once()
        sleep.assert_not_called()
        self.assertFalse(hasattr(module, "publish_mqtt"))
        self.assertFalse(hasattr(module, "build_mqtt_message"))

    def test_mail_nonfatal_failure_marks_json_success_warning(self):
        text = BASE_CONFIG.replace("on_success = false", "on_success = true")
        text = text.replace("continue_on_mail_fail = false", "continue_on_mail_fail = true")
        path = self.write_config(text)
        with (
            mock.patch.object(module, "send_mail", return_value=False),
            mock.patch.object(
                module, "publish_mqtt_status", return_value=(True, "status ok")
            ) as status,
            mock.patch.object(module, "run_power_action"),
            mock.patch.dict(os.environ, {}, clear=True),
        ):
            rc = module.main(["-c", path])
        self.assertEqual(rc, 0)
        self.assertTrue(status.call_args.kwargs["warning"])

    def test_systemd_failure_reports_json_failure_only(self):
        path = self.write_config()
        env = {
            "SERVICE_RESULT": "exit-code",
            "EXIT_CODE": "exited",
            "EXIT_STATUS": "42",
        }
        with (
            mock.patch.object(
                module, "publish_mqtt_status", return_value=(True, "failure status ok")
            ) as status,
            mock.patch.object(module, "run_power_action") as power,
            mock.patch.dict(os.environ, env, clear=True),
        ):
            rc = module.main(["-c", path])
        self.assertEqual(rc, 0)
        power.assert_not_called()
        kwargs = status.call_args.kwargs
        self.assertFalse(kwargs["success"])
        self.assertEqual(kwargs["exit_code"], 42)
        self.assertIn("SERVICE_RESULT=exit-code", kwargs["error_message"])
        self.assertIn("EXIT_STATUS=42", kwargs["stderr_text"])

    def test_systemd_success_stop_post_does_not_duplicate_success(self):
        path = self.write_config()
        with (
            mock.patch.object(module, "publish_mqtt_status") as status,
            mock.patch.dict(
                os.environ,
                {"SERVICE_RESULT": "success", "EXIT_CODE": "exited", "EXIT_STATUS": "0"},
                clear=True,
            ),
        ):
            rc = module.main(["-c", path])
        self.assertEqual(rc, 0)
        status.assert_not_called()


if __name__ == "__main__":
    unittest.main()
