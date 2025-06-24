#!/bin/bash
# file: set_nm_gateway_roles.sh
#
# Enforce device assignment and gateway rules for AP/GATE/LAN connections.
# For GATE, tries each connection on every available wifi interface until one succeeds.
# Now also verifies Raspberry Pi Connect status before and after.

# --- Configuration ---
PING_TARGET="8.8.8.8"
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

# --- Initial ping test ---
if ping -q -c 2 -W 2 "$PING_TARGET" > /dev/null 2>&1; then
    echo "[INFO] Internet is reachable via $PING_TARGET."
    # Doctor check
    echo "[INFO] Running Raspberry Pi Connect doctor..."
    if rpi-connect doctor | tee /tmp/rpi_doctor.txt | grep -q "Peer-to-peer connection candidate via"; then
        echo "[INFO] Pi Connect doctor passed basic checks."
        if [ $FORCE -eq 0 ]; then
            echo "[INFO] No fixes needed. Use --force to override."
            exit 0
        else
            echo "[FORCE] Continuing with fixes as requested."
        fi
    else
        echo "[WARN] Doctor did not pass all checks. Proceeding with battery of fixes."
    fi
else
    echo "[WARN] Internet unreachable, enforcing role/gateway config."
fi

# --- Confirm ---
if [ $YES -eq 0 ]; then
    echo "This will reassign all AP to $AP_DEVICE, all LAN to $LAN_DEVICE,"
    echo "set GATE as default gateway (tries every wifi device for each GATE), others as non-gateway."
    read -p "Proceed? [y/N] " RESP
    [[ "$RESP" =~ ^[Yy] ]] || { echo "Aborted."; exit 1; }
fi

# --- Get all available wifi interfaces (can be up or down) ---
get_wifi_ifs() {
    iw dev 2>/dev/null | awk '$1=="Interface"{print $2}'
}

WIFI_IFS=($(get_wifi_ifs))
if [[ ${#WIFI_IFS[@]} -eq 0 ]]; then
    echo "[ERROR] No wifi interfaces found (check 'iw dev')"
    exit 1
fi

# --- Main Logic: configure all connections by role ---
while IFS= read -r line; do
    conn_name=$(echo "$line" | awk '{$NF=""; print $0}' | sed 's/ *$//')
    uuid=$(echo "$line" | awk '{print $(NF-2)}')
    type=$(echo "$line" | awk '{print $(NF-1)}')
    device=$(echo "$line" | awk '{print $NF}')

    # Skip loopback
    if [[ "$type" == "loopback" ]]; then
        continue
    fi

    apply=0

    if [[ "$conn_name" == *GATE* ]]; then
        # GATE: allow NM to pick interface, set as gateway, remove mac lock
        echo "[GATE] $conn_name ($uuid): will try all wifi interfaces, gateway: ENABLE"
        nmcli connection modify "$uuid" connection.interface-name ""
        nmcli connection modify "$uuid" ipv4.never-default no
        nmcli connection modify "$uuid" connection.autoconnect yes
        nmcli connection modify "$uuid" 802-11-wireless.mac-address ""
        apply=1
    elif [[ "$conn_name" == *AP* ]]; then
        # AP: assign to wlan0, gateway: DISABLE
        echo "[AP] $conn_name ($uuid): assign to $AP_DEVICE, gateway: DISABLE"
        nmcli connection modify "$uuid" connection.interface-name "$AP_DEVICE"
        nmcli connection modify "$uuid" ipv4.never-default yes
        nmcli connection modify "$uuid" connection.autoconnect yes
        nmcli connection modify "$uuid" 802-11-wireless.mac-address ""
        apply=1
    elif [[ "$conn_name" == *LAN* ]]; then
        # LAN: assign to eth0, gateway: DISABLE
        echo "[LAN] $conn_name ($uuid): assign to $LAN_DEVICE, gateway: DISABLE"
        nmcli connection modify "$uuid" connection.interface-name "$LAN_DEVICE"
        nmcli connection modify "$uuid" ipv4.never-default yes
        nmcli connection modify "$uuid" connection.autoconnect yes
        # (no mac-address for ethernet, but harmless to clear)
        nmcli connection modify "$uuid" 802-11-wireless.mac-address "" 2>/dev/null || true
        apply=1
    fi

    if [ $apply -eq 0 ]; then
        echo "[SKIP] $conn_name ($uuid) – no AP/GATE/LAN tag found"
    fi

done < <(nmcli --fields NAME,UUID,TYPE,DEVICE connection show | tail -n +2)

echo "[INFO] Reactivating AP and LAN connections..."

# --- Reactivate AP and LAN connections on their devices ---
while IFS= read -r line; do
    conn_name=$(echo "$line" | awk '{$NF=""; print $0}' | sed 's/ *$//')
    uuid=$(echo "$line" | awk '{print $(NF-2)}')
    type=$(echo "$line" | awk '{print $(NF-1)}')

    # Skip loopback
    if [[ "$type" == "loopback" ]]; then
        continue
    fi

    tgt_dev=""
    if [[ "$conn_name" == *AP* ]]; then
        tgt_dev="$AP_DEVICE"
    elif [[ "$conn_name" == *LAN* ]]; then
        tgt_dev="$LAN_DEVICE"
    fi

    if [[ -n "$tgt_dev" ]]; then
        echo "[INFO] Deactivating $conn_name ($uuid) on all devices (ignore errors)..."
        nmcli connection down "$uuid" 2>/dev/null || true
        echo "[INFO] Activating $conn_name ($uuid) on $tgt_dev ..."
        nmcli connection up "$uuid" ifname "$tgt_dev"
    fi

done < <(nmcli --fields NAME,UUID,TYPE,DEVICE connection show | tail -n +2)

echo "[INFO] Attempting each GATE connection on every wifi interface..."

# --- For each GATE connection, try every wifi interface, activate first that succeeds ---
while IFS= read -r line; do
    conn_name=$(echo "$line" | awk '{$NF=""; print $0}' | sed 's/ *$//')
    uuid=$(echo "$line" | awk '{print $(NF-2)}')
    type=$(echo "$line" | awk '{print $(NF-1)}')

    # Only process GATE
    if [[ "$conn_name" == *GATE* ]]; then
        # Deactivate everywhere first
        nmcli connection down "$uuid" 2>/dev/null || true
        success=0
        for wifi_if in "${WIFI_IFS[@]}"; do
            echo "[GATE] Trying to activate $conn_name ($uuid) on $wifi_if ..."
            if nmcli connection up "$uuid" ifname "$wifi_if"; then
                echo "[GATE] SUCCESS: $conn_name is active on $wifi_if"
                success=1
                break
            else
                echo "[GATE] Failed to activate $conn_name on $wifi_if"
            fi
        done
        if [ $success -eq 0 ]; then
            echo "[GATE] Could not activate $conn_name on any wifi interface."
        fi
    fi
done < <(nmcli --fields NAME,UUID,TYPE,DEVICE connection show | tail -n +2)

# --- Final: Restart and check rpi-connect ---
echo "[INFO] Restarting Raspberry Pi Connect..."
rpi-connect restart
sleep 5

echo "[INFO] Checking Raspberry Pi Connect status:"
rpi-connect status

echo "[INFO] Running Raspberry Pi Connect doctor for final check:"
rpi-connect doctor | tee /tmp/rpi_doctor_after.txt

if rpi-connect status | grep -q 'Signed in: yes' && rpi-connect status | grep -q 'Subscribed to events: yes'; then
    echo "[SUCCESS] Raspberry Pi Connect is running and signed in."
else
    echo "[FAIL] Raspberry Pi Connect is NOT fully connected. Check status above."
fi

echo "[DONE] All connections processed. Check with 'nmcli connection show --active' and 'nmcli device status'."
