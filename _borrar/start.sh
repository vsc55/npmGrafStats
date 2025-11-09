#!/bin/bash

echo "npmGrafStats: v2.4.3"
echo "Startup: lets get the logs send them to influx"

NPMGRAF_DIR="/root/.config/NPMGRAF"

REDIRECTION_LOGS="${REDIRECTION_LOGS:-TRUE}"
REDIRECTION_LOGS="${REDIRECTION_LOGS,,}"

case "$REDIRECTION_LOGS" in
  true)
    echo "Redirection and Reverse-Proxy Logs activated"
    bash "${NPMGRAF_DIR}/sendips.sh" &
    bash "${NPMGRAF_DIR}/sendredirectionips.sh" &
    ;;
  only)
    echo "Only Redirection Logs activated"
    bash "${NPMGRAF_DIR}/sendredirectionips.sh" &
    ;;
  *)
    echo "Only Reverse-Proxy Logs activated"
    bash "${NPMGRAF_DIR}/sendips.sh" &
    ;;
esac

sleep 0.5

# Defined tee as the main process for docker and redirect logs to standard output
exec tee "${NPMGRAF_DIR}/nohup.out" > /proc/1/fd/1 2>/proc/1/fd/2