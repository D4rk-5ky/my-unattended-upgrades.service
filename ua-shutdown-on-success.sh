set -euo pipefail
logger -t ua-post "Unattended-upgrades finished successfully; shutting down"
/usr/bin/systemctl poweroff