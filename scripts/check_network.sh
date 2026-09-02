#!/usr/bin/env bash

set -u

readonly PACKAGE_NAME="jackal_network_bringup"
readonly CMD_TOPIC="/j100_0519/cmd_vel"

usage() {
  cat <<'EOF'
Usage:
  check_network.sh preflight <laptop|nuc|radxa>
  check_network.sh verify-peer <laptop|nuc|radxa>
  check_network.sh verify-d455
  check_network.sh verify-mid360
  check_network.sh wait-zero-cmd
  check_network.sh send-zero-cmd

send-zero-cmd publishes one fixed, all-zero Twist. It never accepts
velocity values from the command line.
EOF
}

pass() {
  printf '[PASS] %s\n' "$1"
}

fail() {
  printf '[FAIL] %s\n' "$1" >&2
}

expected_ip_for_role() {
  case "$1" in
    laptop) printf '192.168.50.1\n' ;;
    nuc) printf '192.168.50.2\n' ;;
    radxa) printf '192.168.50.3\n' ;;
    *) return 1 ;;
  esac
}

validate_role() {
  if ! expected_ip_for_role "$1" >/dev/null; then
    fail "unknown role '$1' (expected laptop, nuc, or radxa)"
    return 2
  fi
}

check_equal() {
  local name="$1"
  local actual="$2"
  local expected="$3"
  if [[ "$actual" == "$expected" ]]; then
    pass "$name=$expected"
    return 0
  fi
  fail "$name is '${actual:-<unset>}', expected '$expected'"
  return 1
}

check_package() {
  local package="$1"
  if ros2 pkg prefix "$package" >/dev/null 2>&1; then
    pass "ROS package '$package' is available"
    return 0
  fi
  fail "ROS package '$package' is not available"
  return 1
}

preflight() {
  local role="$1"
  local expected_ip
  local profile
  local failures=0

  validate_role "$role" || return $?
  expected_ip="$(expected_ip_for_role "$role")"

  if ip -o -4 address show | awk '{print $4}' | cut -d/ -f1 | grep -Fxq "$expected_ip"; then
    pass "$role IP $expected_ip is configured"
  else
    fail "$role IP $expected_ip is not configured on this host"
    failures=$((failures + 1))
  fi

  check_equal "ROS_DOMAIN_ID" "${ROS_DOMAIN_ID:-}" "1" || failures=$((failures + 1))
  check_equal "ROS_LOCALHOST_ONLY" "${ROS_LOCALHOST_ONLY:-}" "0" || failures=$((failures + 1))
  check_equal "RMW_IMPLEMENTATION" "${RMW_IMPLEMENTATION:-}" "rmw_fastrtps_cpp" || failures=$((failures + 1))

  profile="${FASTRTPS_DEFAULT_PROFILES_FILE:-}"
  if [[ -f "$profile" ]]; then
    pass "Fast DDS profile exists: $profile"
  else
    fail "Fast DDS profile does not exist: ${profile:-<unset>}"
    failures=$((failures + 1))
  fi
  if [[ "${FASTDDS_DEFAULT_PROFILES_FILE:-}" == "$profile" ]]; then
    pass "Fast DDS legacy and modern profile variables match"
  else
    fail "FASTRTPS_DEFAULT_PROFILES_FILE and FASTDDS_DEFAULT_PROFILES_FILE differ"
    failures=$((failures + 1))
  fi
  if [[ -n "$profile" ]] && python3 -c '
import sys
import xml.etree.ElementTree as ET

namespace = {"f": "http://www.eprosima.com/XMLSchemas/fastRTPS_Profiles"}
root = ET.parse(sys.argv[1]).getroot()
addresses = {
    item.text
    for item in root.findall(".//f:interfaceWhiteList/f:address", namespace)
}
raise SystemExit(0 if addresses == {sys.argv[2]} else 1)
' "$profile" "$expected_ip"; then
    pass "Fast DDS UDP allowlist is exactly $expected_ip"
  else
    fail "Fast DDS UDP allowlist is not exactly $expected_ip"
    failures=$((failures + 1))
  fi

  check_package "$PACKAGE_NAME" || failures=$((failures + 1))
  check_package "rmw_fastrtps_cpp" || failures=$((failures + 1))
  case "$role" in
    laptop)
      check_package "rviz2" || failures=$((failures + 1))
      ;;
    nuc)
      check_package "realsense2_camera" || failures=$((failures + 1))
      ;;
    radxa)
      check_package "clearpath_control" || failures=$((failures + 1))
      ;;
  esac

  if ((failures > 0)); then
    fail "preflight completed with $failures failure(s)"
    return 1
  fi
  pass "preflight completed for role '$role'"
}

verify_peer() {
  local role="$1"
  validate_role "$role" || return $?

  printf 'Checking 10 seconds of continuous %s heartbeat ...\n' "$role"
  if timeout 30s ros2 run "$PACKAGE_NAME" network_verifier.py \
      heartbeat "$role"; then
    pass "received a continuous heartbeat from '$role'"
    return 0
  fi
  fail "heartbeat from '$role' was missing or discontinuous"
  return 1
}

verify_d455() {
  printf 'Checking D455 publishers and 30-second image rates ...\n'
  if timeout 50s ros2 run "$PACKAGE_NAME" network_verifier.py d455; then
    pass "D455 Color/Depth/CameraInfo verification completed"
    return 0
  fi
  fail "D455 publisher, message, or rate verification failed"
  return 1
}

verify_mid360() {
  printf 'Checking MID360 publishers and 10-second point-cloud rate ...\n'
  if timeout 25s ros2 run "$PACKAGE_NAME" network_verifier.py mid360; then
    pass "MID360 PointCloud2/IMU verification completed"
    return 0
  fi
  fail "MID360 publisher, message, or rate verification failed"
  return 1
}

wait_zero_cmd() {
  local payload
  printf 'Waiting up to 20 seconds for one %s message ...\n' "$CMD_TOPIC"
  if ! payload="$(timeout 20s ros2 topic echo --no-daemon --once \
      --qos-profile system_default "$CMD_TOPIC" geometry_msgs/msg/Twist)"; then
    fail "did not receive $CMD_TOPIC"
    return 1
  fi

  if printf '%s\n' "$payload" | python3 -c '
import math
import sys
import yaml

documents = [item for item in yaml.safe_load_all(sys.stdin) if isinstance(item, dict)]
if not documents:
    raise SystemExit(1)
twist = documents[0]
values = []
for group in ("linear", "angular"):
    vector = twist.get(group, {})
    values.extend(float(vector.get(axis, 0.0)) for axis in ("x", "y", "z"))
raise SystemExit(0 if all(math.isfinite(value) and value == 0.0 for value in values) else 1)
'; then
    pass "received an all-zero Twist on $CMD_TOPIC"
    return 0
  fi
  fail "received a non-zero or invalid Twist on $CMD_TOPIC"
  return 1
}

send_zero_cmd() {
  if (($# != 0)); then
    fail "send-zero-cmd does not accept velocity arguments"
    return 2
  fi

  local message
  message='{linear: {x: 0.0, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.0}}'
  if timeout 20s ros2 topic pub --once --wait-matching-subscriptions 1 \
      --qos-profile system_default "$CMD_TOPIC" geometry_msgs/msg/Twist "$message"; then
    pass "published one all-zero Twist on $CMD_TOPIC"
    return 0
  fi
  fail "zero command was not delivered to a matching subscriber"
  return 1
}

main() {
  if (($# < 1)); then
    usage
    return 2
  fi

  local command="$1"
  shift
  case "$command" in
    preflight)
      (($# == 1)) || { usage; return 2; }
      preflight "$1"
      ;;
    verify-peer)
      (($# == 1)) || { usage; return 2; }
      verify_peer "$1"
      ;;
    verify-d455)
      (($# == 0)) || { usage; return 2; }
      verify_d455
      ;;
    verify-mid360)
      (($# == 0)) || { usage; return 2; }
      verify_mid360
      ;;
    wait-zero-cmd)
      (($# == 0)) || { usage; return 2; }
      wait_zero_cmd
      ;;
    send-zero-cmd)
      send_zero_cmd "$@"
      ;;
    -h|--help|help)
      usage
      ;;
    *)
      fail "unknown command '$command'"
      usage
      return 2
      ;;
  esac
}

main "$@"
