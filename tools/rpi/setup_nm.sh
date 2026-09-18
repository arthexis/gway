#!/bin/bash
# file: tools/rpi/setup_nm.sh
# Enforce: AP always on wlan0 (exclusive), only one GATE up at a time (never on wlan0), LAN to eth0.

PING_TARGET="8.8.8.8"
AP_DEVICE="wlan0"
LAN_DEVICE="eth0"

YES=0
FORCE=0
NEEDS_FIX=0

for arg in "$@"; do
    case "$arg" in
        --yes|-y)   YES=1 ;;
        --force|-f) FORCE=1 ;;
        *) ;;
    esac
done

# --- Detect AP/GATE violations before connectivity checks ---
echo "[CHECK] Scanning for forbidden AP/GATE configuration..."

GATE_ON_AP=0
AP_NOT_ON_APDEV=0
ACTIVE_GATES=0

while IFS= read -r line; do
    # Parse
    name=$(echo "$line" | awk '{$NF=""; print $0}' | sed 's/ *$//')
    uuid=$(echo "$line" | awk '{print $(NF-2)}')
    type=$(echo "$line" | awk '{print $(NF-1)}')
    device=$(echo "$line" | awk '{print $NF}')
    # GATE must never be on wlan0
    if [[ "$name" == *GATE* && "$device" == "$AP_DEVICE" ]]; then
        echo "[ERR] GATE connection '$name' is active on $AP_DEVICE! This is forbidden."
        GATE_ON_AP=1
        NEEDS_FIX=1
    fi
    # AP must always be on wlan0 and up
    if [[ "$name" == *AP* ]]; then
        if [[ "$device" != "$AP_DEVICE" ]]; then
            echo "[ERR] AP connection '$name' is NOT on $AP_DEVICE (device='$device')."
            AP_NOT_ON_APDEV=1
            NEEDS_FIX=1
        fi
    fi
    # Only count GATEs up (not required for early fix, but useful)
    if [[ "$name" == *GATE* && "$device" != "--" && "$device" != "" ]]; then
        ((ACTIVE_GATES++))
    fi
done < <(nmcli --fields NAME,UUID,TYPE,DEVICE connection show | tail -n +2)

if ((GATE_ON_AP)); then
    echo "[CHECK] At least one GATE is running on $AP_DEVICE (forbidden). Will enforce fix."
fi
if ((AP_NOT_ON_APDEV)); then
    echo "[CHECK] At least one AP is not on $AP_DEVICE. Will enforce fix."
fi

# --- Early Exit only if internet/rpi-connect is fine AND no config errors ---
if [ $FORCE -eq 0 ]; then
    if [ $NEEDS_FIX -eq 0 ]; then
        if ping -q -c 2 -W 2 "$PING_TARGET" > /dev/null 2>&1; then
            echo "[INFO] Internet is reachable via $PING_TARGET."
            echo "[INFO] Running Raspberry Pi Connect doctor..."
            if rpi-connect doctor | tee /tmp/rpi_doctor.txt | grep -q "Peer-to-peer connection candidate via"; then
                echo "[INFO] Pi Connect doctor passed basic checks."
                echo "[INFO] No AP/GATE config error detected. Use --force to override."
                exit 0
            else
                echo "[WARN] Doctor did not pass all checks. Proceeding with battery of fixes."
            fi
        else
            echo "[WARN] Internet unreachable, enforcing role/gateway config."
        fi
    else
        echo "[WARN] AP/GATE misconfiguration detected, will fix even if internet is up."
    fi
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
        nmcli connection down "$uuid" 2>/dev/null || true
        nmcli connection up "$uuid" ifname "$AP_DEVICE"
        continue
    fi

    # Handle LAN (only reconfigure/restart if needed)
    if [[ "$conn_name" == *LAN* ]]; then
        NEED_RECONF=0
        # Check device assignment
        if [[ "$device" != "$LAN_DEVICE" ]]; then
            NEED_RECONF=1
            echo "[LAN] $conn_name ($uuid): device is '$device', should be '$LAN_DEVICE' (will reconfigure)"
        fi
        # Check autoconnect and never-default properties
        AUTOCON=$(nmcli -g connection.autoconnect connection show "$uuid")
        NEVERDEF=$(nmcli -g ipv4.never-default connection show "$uuid")
        if [[ "$AUTOCON" != "yes" || "$NEVERDEF" != "yes" ]]; then
            NEED_RECONF=1
            echo "[LAN] $conn_name ($uuid): autoconnect/never-default are not both yes (will reconfigure)"
        fi

        if [[ $NEED_RECONF -eq 1 ]]; then
            nmcli connection modify "$uuid" connection.interface-name "$LAN_DEVICE"
            nmcli connection modify "$uuid" ipv4.never-default yes
            nmcli connection modify "$uuid" connection.autoconnect yes
            nmcli connection modify "$uuid" 802-11-wireless.mac-address "" 2>/dev/null || true
            nmcli connection down "$uuid" 2>/dev/null || true
            nmcli connection up "$uuid" ifname "$LAN_DEVICE"
            echo "[LAN] $conn_name ($uuid): LAN reconfigured and reconnected."
        else
            echo "[LAN] $conn_name ($uuid): already correctly configured, leaving untouched."
        fi
        continue
    fi

    # Handle GATE
    if [[ "$conn_name" == *GATE* ]]; then
        nmcli connection modify "$uuid" connection.interface-name ""
        nmcli connection modify "$uuid" ipv4.never-default no
        nmcli connection modify "$uuid" connection.autoconnect no
        nmcli connection modify "$uuid" 802-11-wireless.mac-address ""
        nmcli connection down "$uuid" 2>/dev/null || true

        if [ $GATE_STARTED -eq 0 ]; then
            for wifi_if in "${WIFI_IFS[@]}"; do
                if [[ "$wifi_if" == "$AP_DEVICE" ]]; then
                    continue
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

    nmcli connection modify "$uuid" connection.autoconnect no
    nmcli connection down "$uuid" 2>/dev/null || true
    echo "[SKIP] $conn_name ($uuid) – not AP/GATE/LAN, set autoconnect off"
done < <(nmcli --fields NAME,UUID,TYPE,DEVICE connection show | tail -n +2)

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
