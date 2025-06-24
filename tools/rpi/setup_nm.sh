#!/bin/bash
# file: tools/rpi/setup_nm.sh
# Enforce: AP always on wlan0 (exclusive), only one GATE up at a time (never on wlan0), LAN to eth0.

# --- Configuration ---
PING_TARGET="8.8.8.8"
AP_DEVICE="wlan0"
LAN_DEVICE="eth0"

YES=0
FORCE=0
for arg in "$@"; do
    case "$arg" in
        --yes|-y)   YES=1 ;;
        --force|-f) FORCE=1 ;;
        *) ;;
    esac
done

# --- Initial ping test and Pi Connect precheck ---
if ping -q -c 2 -W 2 "$PING_TARGET" > /dev/null 2>&1; then
    echo "[INFO] Internet is reachable via $PING_TARGET."
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
    echo "This will enforce AP only on $AP_DEVICE (exclusive), only one GATE at a time (never on $AP_DEVICE), and LAN on $LAN_DEVICE."
    read -p "Proceed? [y/N] " RESP
    [[ "$RESP" =~ ^[Yy] ]] || { echo "Aborted."; exit 1; }
fi

# --- Get wifi interfaces (can be up or down) ---
get_wifi_ifs() {
    iw dev 2>/dev/null | awk '$1=="Interface"{print $2}'
}
WIFI_IFS=($(get_wifi_ifs))
if [[ ${#WIFI_IFS[@]} -eq 0 ]]; then
    echo "[ERROR] No wifi interfaces found (check 'iw dev')"
    exit 1
fi

# --- Main: Enforce roles ---
GATE_STARTED=0
GATE_USED_IF=""

while IFS= read -r line; do
    conn_name=$(echo "$line" | awk '{$NF=""; print $0}' | sed 's/ *$//')
    uuid=$(echo "$line" | awk '{print $(NF-2)}')
    type=$(echo "$line" | awk '{print $(NF-1)}')
    device=$(echo "$line" | awk '{print $NF}')

    # Skip loopback
    if [[ "$type" == "loopback" ]]; then
        continue
    fi

    # Handle AP (must be on wlan0, exclusive)
    if [[ "$conn_name" == *AP* ]]; then
        echo "[AP] $conn_name ($uuid): enforce ONLY on $AP_DEVICE"
        nmcli connection modify "$uuid" connection.interface-name "$AP_DEVICE"
        nmcli connection modify "$uuid" ipv4.never-default yes
        nmcli connection modify "$uuid" connection.autoconnect yes
        nmcli connection modify "$uuid" 802-11-wireless.mac-address ""
        # Reactivate AP (bring up, other connections will be kept off)
        nmcli connection down "$uuid" 2>/dev/null || true
        nmcli connection up "$uuid" ifname "$AP_DEVICE"
        continue
    fi

    # Handle LAN
    if [[ "$conn_name" == *LAN* ]]; then
        echo "[LAN] $conn_name ($uuid): assign to $LAN_DEVICE"
        nmcli connection modify "$uuid" connection.interface-name "$LAN_DEVICE"
        nmcli connection modify "$uuid" ipv4.never-default yes
        nmcli connection modify "$uuid" connection.autoconnect yes
        nmcli connection modify "$uuid" 802-11-wireless.mac-address "" 2>/dev/null || true
        nmcli connection down "$uuid" 2>/dev/null || true
        nmcli connection up "$uuid" ifname "$LAN_DEVICE"
        continue
    fi

    # Handle GATE
    if [[ "$conn_name" == *GATE* ]]; then
        # GATE: never allowed on wlan0; only activate one GATE at a time
        nmcli connection modify "$uuid" connection.interface-name ""
        nmcli connection modify "$uuid" ipv4.never-default no
        nmcli connection modify "$uuid" connection.autoconnect no  # avoid race
        nmcli connection modify "$uuid" 802-11-wireless.mac-address ""

        nmcli connection down "$uuid" 2>/dev/null || true

        if [ $GATE_STARTED -eq 0 ]; then
            # Try to bring up GATE on any wifi interface but wlan0 (AP)
            for wifi_if in "${WIFI_IFS[@]}"; do
                if [[ "$wifi_if" == "$AP_DEVICE" ]]; then
                    continue  # skip AP interface
                fi
                echo "[GATE] Trying to activate $conn_name ($uuid) on $wifi_if ..."
                if nmcli connection up "$uuid" ifname "$wifi_if"; then
                    echo "[GATE] SUCCESS: $conn_name is active on $wifi_if"
                    GATE_STARTED=1
                    GATE_USED_IF="$wifi_if"
                    nmcli connection modify "$uuid" connection.autoconnect yes
                    break
                else
                    echo "[GATE] Failed to activate $conn_name on $wifi_if"
                fi
            done
            if [ $GATE_STARTED -eq 0 ]; then
                echo "[GATE] Could not activate $conn_name on any non-AP wifi interface."
            fi
        else
            echo "[GATE] $conn_name ($uuid): left DOWN (only one GATE allowed)"
            nmcli connection down "$uuid" 2>/dev/null || true
            nmcli connection modify "$uuid" connection.autoconnect no
        fi
        continue
    fi

    # All others: ensure not autoconnect, down
    nmcli connection modify "$uuid" connection.autoconnect no
    nmcli connection down "$uuid" 2>/dev/null || true
    echo "[SKIP] $conn_name ($uuid) – not AP/GATE/LAN, set autoconnect off"
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

echo "[DONE] All connections processed. Only one GATE is up (never on $AP_DEVICE), AP is exclusive on $AP_DEVICE."
