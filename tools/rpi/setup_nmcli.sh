#!/bin/bash
# file: set_nm_gateway_roles.sh
#
# Enforce device assignment and gateway rules for AP/GATE/LAN connections.

# --- Configuration ---
PING_TARGET="8.8.8.8"
GATE_DEVICE="wlan1"
AP_DEVICE="wlan0"
LAN_DEVICE="eth0"

# --- CLI Args ---
YES=0
FORCE=0
for arg in "$@"; do
    case "$arg" in
        --yes|-y)   YES=1 ;;
        --force|-f) FORCE=1 ;;
        *) ;;
    esac
done

# --- Early Exit if Internet OK (unless --force) ---
if [ $FORCE -eq 0 ]; then
    if ping -q -c 2 -W 2 "$PING_TARGET" > /dev/null 2>&1; then
        echo "[INFO] Internet already reachable. Skipping changes. Use --force to override."
        exit 0
    fi
fi

echo "[INFO] Continuing: Internet not reachable or --force given."

# --- Confirm ---
if [ $YES -eq 0 ]; then
    echo "This will reassign all AP to $AP_DEVICE, all GATE to $GATE_DEVICE, all LAN to $LAN_DEVICE,"
    echo "and will set GATE as default gateway, others as non-gateway."
    read -p "Proceed? [y/N] " RESP
    [[ "$RESP" =~ ^[Yy] ]] || { echo "Aborted."; exit 1; }
fi

# --- Main Logic ---
while IFS= read -r line; do
    # Parse
    conn_name=$(echo "$line" | awk '{$NF=""; print $0}' | sed 's/ *$//')
    uuid=$(echo "$line" | awk '{print $(NF-2)}')
    type=$(echo "$line" | awk '{print $(NF-1)}')
    device=$(echo "$line" | awk '{print $NF}')

    # Skip loopback
    if [[ "$type" == "loopback" ]]; then
        continue
    fi

    # Default: don't touch unless rule applies
    apply=0

    # Assign device and gateway based on role in connection name
    if [[ "$conn_name" == *GATE* ]]; then
        # GATE: assign to wlan1, set as gateway
        TARGET_DEV="$GATE_DEVICE"
        echo "[GATE] $conn_name ($uuid) → device: $TARGET_DEV, gateway: ENABLE"
        if [ $YES -eq 1 ]; then echo "  (auto)"; fi
        apply=1
        nmcli connection modify "$uuid" connection.interface-name "$TARGET_DEV"
        nmcli connection modify "$uuid" ipv4.never-default no
        nmcli connection modify "$uuid" connection.autoconnect yes
    elif [[ "$conn_name" == *AP* ]]; then
        # AP: assign to wlan0, gateway: DISABLE
        TARGET_DEV="$AP_DEVICE"
        echo "[AP] $conn_name ($uuid) → device: $TARGET_DEV, gateway: DISABLE"
        apply=1
        nmcli connection modify "$uuid" connection.interface-name "$TARGET_DEV"
        nmcli connection modify "$uuid" ipv4.never-default yes
        nmcli connection modify "$uuid" connection.autoconnect yes
    elif [[ "$conn_name" == *LAN* ]]; then
        # LAN: assign to eth0, gateway: DISABLE
        TARGET_DEV="$LAN_DEVICE"
        echo "[LAN] $conn_name ($uuid) → device: $TARGET_DEV, gateway: DISABLE"
        apply=1
        nmcli connection modify "$uuid" connection.interface-name "$TARGET_DEV"
        nmcli connection modify "$uuid" ipv4.never-default yes
        nmcli connection.modify "$uuid" connection.autoconnect yes
    fi

    # Optionally, show summary for untouched connections
    if [ $apply -eq 0 ]; then
        echo "[SKIP] $conn_name ($uuid) – no AP/GATE/LAN tag found"
    fi

done < <(nmcli --fields NAME,UUID,TYPE,DEVICE connection show | tail -n +2)

echo "Done. You may need to reconnect interfaces or reboot for changes to take effect."
