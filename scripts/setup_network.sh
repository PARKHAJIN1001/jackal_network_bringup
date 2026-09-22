#!/usr/bin/env bash
# Unified setup script for Jackal network and kernel parameters
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "============================================="
echo "        Jackal Network Setup                 "
echo "============================================="

# 1. Check if running with sudo or escalate
if [[ $EUID -ne 0 ]]; then
    echo ">> Requesting root privileges..."
    exec sudo bash "$0" "$@"
fi

# 2. Kernel tunables: IP fragmentation (32 MiB)
echo ">> Applying IP fragmentation limit (32 MiB)..."
python3 "${SCRIPT_DIR}/ipfrag_session.py" apply || true

# 3. Time synchronization with Chrony
echo ">> Configuring Chrony time synchronization for laptop..."
if [[ -f "${SCRIPT_DIR}/configure_time_sync.sh" ]]; then
    bash "${SCRIPT_DIR}/configure_time_sync.sh" laptop --ros-stopped || true
fi

# 4. Check interface IP
if ! ip -o -4 address show | awk '{print $4}' | cut -d/ -f1 | grep -Fxq "192.168.50.1"; then
    echo ">> [WARNING] Laptop IP 192.168.50.1 is not configured on any active network interface!"
    echo ">> Please ensure your Ethernet interface is configured with static IP 192.168.50.1/24"
else
    echo ">> [OK] Laptop static IP 192.168.50.1 is active."
fi

echo -e "\n=== [Setup Completed Successfully] ==="
echo "Remember to source the environment in your user shell before launching ROS:"
echo "  source ~/moai_navigation_ws/install/setup.bash"
echo "  source ~/moai_navigation_ws/install/jackal_network_bringup/share/jackal_network_bringup/config/network_env.sh laptop"
