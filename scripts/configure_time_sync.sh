#!/usr/bin/env bash
# Explicit operator-only configuration. Never called from a ROS launch.
set -euo pipefail

if [[ $# != 2 || "$2" != "--ros-stopped" ]]; then
  printf 'Usage: sudo bash %s <laptop|nuc> --ros-stopped\n' "$0" >&2
  printf 'Stop time-sensitive ROS nodes first. On the NUC, engage physical E-stop.\n' >&2
  exit 2
fi
role="$1"
case "$role" in
  laptop) expected_ip='192.168.50.1'; service='chrony.service' ;;
  nuc) expected_ip='192.168.50.2'; service='systemd-timesyncd.service' ;;
  *) printf 'Unknown role: %s\n' "$role" >&2; exit 2 ;;
esac
if ((EUID != 0)); then
  printf 'Operator sudo execution is required; no changes made.\n' >&2
  exit 2
fi
if ! ip -o -4 address show | awk '{print $4}' | cut -d/ -f1 | grep -Fxq "$expected_ip"; then
  printf 'Expected local address %s is missing; refusing wrong-host configuration.\n' "$expected_ip" >&2
  exit 2
fi
if pgrep -f '(^|/)(laserMapping|rviz2|component_container_isolated|pointcloud_relay_node)([[:space:]]|$)|ros2 launch|pedestrian_figures_node|pedestrian_traces_node' >/dev/null; then
  printf 'ROS launch/navigation/visualization processes are still running; stop them first.\n' >&2
  exit 2
fi
if [[ "$role" == nuc ]]; then
  for unit in jackal-sensors.service clearpath-platform.service; do
    state="$(systemctl is-active "$unit" || true)"
    if [[ "$state" != inactive && "$state" != failed ]]; then
      printf 'Stop %s first (current state: %s). No changes made.\n' "$unit" "$state" >&2
      exit 2
    fi
  done
fi

# This script is intentionally used from the source checkout or a staged bundle.
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
config_dir="$script_dir/../config/time_sync"
candidate=''
cleanup_candidate() {
  if [[ -n "$candidate" ]]; then
    rm -f -- "$candidate"
  fi
}
trap cleanup_candidate EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
if [[ "$role" == laptop ]]; then
  source_file="$config_dir/chrony-laptop.conf"
  target='/etc/chrony/chrony.conf'
  if ! command -v chronyd >/dev/null; then
    printf 'Install chrony first with operator sudo apt install chrony.\n' >&2
    exit 2
  fi
  # Ubuntu's installed chronyd is AppArmor-confined even with -p and sudo.
  # Validate a unique root-owned snapshot in its permitted config directory,
  # outside conf.d/sources.d, without changing the active chrony.conf first.
  candidate="$(mktemp /etc/chrony/jackal-check.XXXXXX)"
  install -o root -g root -m 0644 -- "$source_file" "$candidate"
  chronyd -p -f "$candidate" >/dev/null
  source_file="$candidate"
else
  source_file="$config_dir/90-jackal-lan-time.conf"
  target='/etc/systemd/timesyncd.conf.d/90-jackal-lan-time.conf'
  [[ -r "$source_file" ]] || { printf 'Missing config: %s\n' "$source_file" >&2; exit 2; }
fi

backup_dir="$(mktemp -d /var/backups/jackal-time-sync.XXXXXX)"
printf 'Backup directory: %s\nTarget: %s\n' "$backup_dir" "$target"
systemctl is-enabled "$service" > "$backup_dir/service-enabled.txt" || true
systemctl is-active "$service" > "$backup_dir/service-active.txt" || true
if [[ -e "$target" || -L "$target" ]]; then
  cp -a -- "$target" "$backup_dir/previous-config"
fi
if [[ -f /etc/systemd/timesyncd.conf ]]; then
  cp -a -- /etc/systemd/timesyncd.conf "$backup_dir/timesyncd.conf"
fi
if [[ "$role" == laptop ]]; then
  if [[ "$(systemctl show systemd-timesyncd.service -p LoadState --value)" != not-found ]]; then
    systemctl disable --now systemd-timesyncd.service
  fi
fi
install -D -o root -g root -m 0644 -- "$source_file" "$target"
systemctl enable "$service"
systemctl restart "$service"
printf 'Configuration installed. Clock synchronisation is NOT yet verified.\n'
printf 'Do not start ROS until offset, selected server and pending slew are checked.\n'
if [[ "$role" == laptop ]]; then
  chronyc tracking
  chronyc sources -v
else
  timedatectl show-timesync --all
fi
