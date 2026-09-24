#!/bin/sh
# Render the receiver URLs into the Alertmanager config, then start it.
# Alertmanager has no environment expansion of its own; the template keeps the
# webhook URLs (which carry tokens) out of the committed file.
set -eu
: "${DEVIN_WEBHOOK_URL:=http://alert-sink:9095/devin}"
: "${SLACK_WEBHOOK_URL:=http://alert-sink:9095/slack}"
sed -e "s|__DEVIN_WEBHOOK_URL__|${DEVIN_WEBHOOK_URL}|g" \
    -e "s|__SLACK_WEBHOOK_URL__|${SLACK_WEBHOOK_URL}|g" \
    /etc/alertmanager/alertmanager.yml.tmpl > /tmp/alertmanager.yml
exec /bin/alertmanager \
  --config.file=/tmp/alertmanager.yml \
  --storage.path=/alertmanager \
  --web.listen-address=:9093 \
  "$@"
