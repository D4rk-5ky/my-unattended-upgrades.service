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