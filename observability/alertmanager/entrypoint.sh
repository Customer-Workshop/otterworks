#!/bin/sh
# Render the receiver URLs into the Alertmanager config, then start it.
# Alertmanager has no environment expansion of its own; the template keeps the
# webhook URLs and secret (which are credentials) out of the committed file.
#
# The Devin page always goes to the local sink. When DEVIN_WEBHOOK_URL is set
# it is *also* delivered to that URL with X-Webhook-Secret; when it is unset the
# external block is removed so Alertmanager never posts the page twice.
set -eu
: "${DEVIN_WEBHOOK_URL:=}"
: "${DEVIN_WEBHOOK_SECRET:=}"
: "${SLACK_WEBHOOK_URL:=http://alert-sink:9095/slack}"
if [ -n "${DEVIN_WEBHOOK_URL}" ]; then
  sed -e "s|__DEVIN_WEBHOOK_URL__|${DEVIN_WEBHOOK_URL}|g" \
      -e "s|__DEVIN_WEBHOOK_SECRET__|${DEVIN_WEBHOOK_SECRET}|g" \
      -e "s|__SLACK_WEBHOOK_URL__|${SLACK_WEBHOOK_URL}|g" \
      /etc/alertmanager/alertmanager.yml.tmpl > /tmp/alertmanager.yml
else
  sed -e '/# BEGIN devin-external/,/# END devin-external/d' \
      -e "s|__SLACK_WEBHOOK_URL__|${SLACK_WEBHOOK_URL}|g" \
      /etc/alertmanager/alertmanager.yml.tmpl > /tmp/alertmanager.yml
fi
exec /bin/alertmanager \
  --config.file=/tmp/alertmanager.yml \
  --storage.path=/alertmanager \
  --web.listen-address=:9093 \
  "$@"
