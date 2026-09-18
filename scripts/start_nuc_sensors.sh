#!/usr/bin/env bash

set -eo pipefail

readonly ROS_SETUP_FILE="${JACKAL_ROS_SETUP_FILE:-/opt/ros/humble/setup.bash}"
readonly LIVOX_PREFIX="${JACKAL_LIVOX_PREFIX:-/home/administrator/ws_livox/install/livox_ros_driver2}"
readonly LIVOX_PACKAGE_SETUP="${LIVOX_PREFIX}/share/livox_ros_driver2/package.bash"
readonly LIVOX_SDK_LIB_DIR="${JACKAL_LIVOX_SDK_LIB_DIR:-/home/administrator/ws_livox/install/livox_sdk2/lib}"
readonly LIVOX_SDK_LIBRARY="${LIVOX_SDK_LIB_DIR}/liblivox_lidar_sdk_shared.so"
readonly WORKSPACE_SETUP_FILE="${JACKAL_WORKSPACE_SETUP_FILE:-/home/administrator/moai_navigation_ws/install/setup.bash}"
readonly PACKAGE_SHARE_DIR="${JACKAL_PACKAGE_SHARE_DIR:-/home/administrator/moai_navigation_ws/install/jackal_network_bringup/share/jackal_network_bringup}"
readonly NETWORK_ENV_FILE="${PACKAGE_SHARE_DIR}/config/network_env.sh"
readonly SENSOR_LAN_IP="192.168.1.5"

for required_file in \
    "$ROS_SETUP_FILE" \
    "$LIVOX_PACKAGE_SETUP" \
    "$LIVOX_SDK_LIBRARY" \
    "$WORKSPACE_SETUP_FILE" \
    "$NETWORK_ENV_FILE"; do
  if [[ ! -f "$required_file" ]]; then
    printf 'Required setup file is missing: %s\n' "$required_file" >&2
    exit 1
  fi
done

source "$ROS_SETUP_FILE"
export COLCON_CURRENT_PREFIX="$LIVOX_PREFIX"
source "$LIVOX_PACKAGE_SETUP"
unset COLCON_CURRENT_PREFIX
source "$WORKSPACE_SETUP_FILE"
source "$NETWORK_ENV_FILE" nuc
export LD_LIBRARY_PATH="${LIVOX_SDK_LIB_DIR}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
set -u

if ! ip -o -4 address show | awk '{print $4}' | cut -d/ -f1 | \
    grep -Fxq "$SENSOR_LAN_IP"; then
  printf 'Expected NUC sensor LAN address %s is not configured.\n' \
    "$SENSOR_LAN_IP" >&2
  exit 1
fi

exec ros2 launch jackal_network_bringup robot.launch.py \
  launch_platform:=false \
  launch_d455:=true \
  launch_mid360:=true \
  launch_network_probe:=true
