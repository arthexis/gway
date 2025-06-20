#!/bin/bash

IFACE="wlan1"
CONN="Porsche Centre"
PING_TARGET="8.8.8.8"

if ! ping -c 2 -I $IFACE $PING_TARGET >/dev/null 2>&1; then
    echo "$(date): Network down, restarting WiFi..." >> /var/log/wifi-watchdog.log
    nmcli device disconnect $IFACE
    sleep 5
    nmcli connection up $CONN
fi
