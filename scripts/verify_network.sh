#!/usr/bin/env bash
# Unified verification script for Jackal network and sensor streams
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WS_DIR="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

# Source ROS 2 environment if not already loaded
if [[ -z "${ROS_DISTRO}" ]]; then
    if [[ -f "/opt/ros/humble/setup.bash" ]]; then
        source "/opt/ros/humble/setup.bash"
    fi
fi

# Source workspace environment if available
if [[ -f "${WS_DIR}/install/setup.bash" ]]; then
    source "${WS_DIR}/install/setup.bash"
fi

# Source network env
if [[ -f "${WS_DIR}/install/jackal_network_bringup/share/jackal_network_bringup/config/network_env.sh" ]]; then
    source "${WS_DIR}/install/jackal_network_bringup/share/jackal_network_bringup/config/network_env.sh" laptop || true
elif [[ -f "${SCRIPT_DIR}/../config/network_env.sh" ]]; then
    source "${SCRIPT_DIR}/../config/network_env.sh" laptop || true
fi

echo "============================================="
echo "        Jackal Network Verification          "
echo "============================================="

echo -e "\n1. [Time Synchronization Status]"
if command -v chronyc >/dev/null 2>&1; then
    chronyc tracking | grep -E 'Reference ID|Stratum|System time|Last offset|RMS offset' || chronyc tracking
else
    echo "chronyc command not found. Please install chrony."
fi

echo -e "\n2. [Preflight & Environment Check]"
if [[ -f "${SCRIPT_DIR}/check_network.sh" ]]; then
    bash "${SCRIPT_DIR}/check_network.sh" preflight laptop || true
fi

echo -e "\n3. [NUC Peer Heartbeat Check]"
if [[ -f "${SCRIPT_DIR}/check_network.sh" ]]; then
    bash "${SCRIPT_DIR}/check_network.sh" verify-peer nuc || true
fi

echo -e "\n4. [LiDAR & Sensor Stream Verification]"
if [[ -f "${SCRIPT_DIR}/check_network.sh" ]]; then
    bash "${SCRIPT_DIR}/check_network.sh" verify-mid360 || true
fi

echo -e "\n============================================="
echo "Verification complete."
