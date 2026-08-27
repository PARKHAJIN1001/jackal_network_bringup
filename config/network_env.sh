#!/usr/bin/env bash

# Source this file after the ROS and workspace setup files:
#   source <package-share>/config/network_env.sh laptop

_jackal_network_env_main() {
  if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    printf 'This script must be sourced, not executed.\n' >&2
    return 2
  fi
  if (($# != 1)); then
    printf 'Usage: source network_env.sh <laptop|nuc|radxa>\n' >&2
    return 2
  fi

  local role="$1"
  local expected_ip
  case "$role" in
    laptop) expected_ip="192.168.50.1" ;;
    nuc) expected_ip="192.168.50.2" ;;
    radxa) expected_ip="192.168.50.3" ;;
    *)
      printf 'Unknown network role: %s\n' "$role" >&2
      return 2
      ;;
  esac

  local config_dir
  config_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)" || return 1
  local profile="$config_dir/fastdds_${role}.xml"
  if [[ ! -f "$profile" ]]; then
    printf 'Fast DDS profile is missing: %s\n' "$profile" >&2
    return 1
  fi
  if ! ip -o -4 address show | awk '{print $4}' | cut -d/ -f1 | grep -Fxq "$expected_ip"; then
    printf 'Expected %s address %s is not configured on this host.\n' \
      "$role" "$expected_ip" >&2
    return 1
  fi

  export ROS_DOMAIN_ID=1
  export ROS_LOCALHOST_ONLY=0
  export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
  export FASTRTPS_DEFAULT_PROFILES_FILE="$profile"
  export FASTDDS_DEFAULT_PROFILES_FILE="$profile"
  export JACKAL_NETWORK_ROLE="$role"

  printf 'Configured Jackal ROS network: role=%s ip=%s domain=%s rmw=%s\n' \
    "$role" "$expected_ip" "$ROS_DOMAIN_ID" "$RMW_IMPLEMENTATION"
}

_jackal_network_env_main "$@"
_jackal_network_env_status=$?
unset -f _jackal_network_env_main
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  exit "$_jackal_network_env_status"
fi
return "$_jackal_network_env_status"
