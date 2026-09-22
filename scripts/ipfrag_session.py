#!/usr/bin/env python3
"""Manage per-session IP-fragmentation tunables for Jackal LAN."""

import argparse
import fcntl
import json
import os
from pathlib import Path
import sys

IPFRAG = Path('/proc/sys/net/ipv4/ipfrag_high_thresh')
IPFRAG_TIME = Path('/proc/sys/net/ipv4/ipfrag_time')
MIN_IPFRAG = 32 * 1024 * 1024   # 32 MiB
TARGET_IPFRAG_TIME = 3           # seconds

STATE_DIR = Path('/run/jackal-network-ipfrag')
LEGACY_DIR = Path('/run/jackal-nav2-ipfrag')
BOOT_ID = Path('/proc/sys/kernel/random/boot_id')

def status(state_path=None, legacy_path=None, kernel=IPFRAG, kernel_time=IPFRAG_TIME):
    current = int(kernel.read_text()) if kernel.exists() else 0
    return {
        'ready': current >= MIN_IPFRAG,
        'ipfrag_high_thresh': current
    }

def _ros_processes_running():
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            args = (entry / 'cmdline').read_bytes().decode().rstrip('\0').split('\0')
            names = [Path(a).name for a in args[:2]]
            if any(n in names for n in (
                    'fastlivo_mapping', 'pointcloud_relay_node',
                    'amcl', 'controller_server', 'planner_server')):
                return True
            if 'ros2' in names and 'launch' in args:
                return True
        except (OSError, ValueError, UnicodeError):
            continue
    return False


def save(path, state):
    temporary = path.with_suffix('.tmp')
    with temporary.open('w') as stream:
        json.dump(state, stream)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def change(action, state_path, kernel=IPFRAG, kernel_time=IPFRAG_TIME,
           boot_file=BOOT_ID, processes=_ros_processes_running):
    current = int(kernel.read_text())
    boot = boot_file.read_text().strip()
    namespace = os.readlink('/proc/self/ns/net')
    state = json.loads(state_path.read_text()) if state_path.exists() else None
    if state and state['boot'] != boot:
        raise RuntimeError('Saved state belongs to another boot')
    if state and state['network_namespace'] != namespace:
        raise RuntimeError('Saved state belongs to another namespace')
    
    if action == 'apply':
        if current >= MIN_IPFRAG and not state:
            return {'status': 'already_sufficient', 'current': current}
        if processes():
            raise RuntimeError('Stop ROS stack first')
        
        current_time = int(kernel_time.read_text()) if kernel_time.exists() else 30
        state = {'boot': boot, 'network_namespace': namespace,
                 'original': current, 'target': MIN_IPFRAG,
                 'original_time': current_time, 'target_time': TARGET_IPFRAG_TIME}
        save(state_path, state)
        kernel.write_text(str(MIN_IPFRAG) + '\n')
        if kernel_time.exists():
            kernel_time.write_text(str(TARGET_IPFRAG_TIME) + '\n')
        return {'status': 'applied', **state}
        
    # restore
    if not state:
        raise RuntimeError('No saved original value')
    if current != state['original']:
        kernel.write_text(str(state['original']) + '\n')
    if kernel_time.exists():
        kernel_time.write_text(str(state.get('original_time', 30)) + '\n')
    state_path.unlink()
    return {'status': 'restored'}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['status', 'apply', 'restore'])
    args = parser.parse_args(argv)
    
    if args.action == 'status':
        print(json.dumps({'ipfrag_high_thresh': int(IPFRAG.read_text())}))
        return 0
        
    if os.geteuid() != 0:
        raise RuntimeError('sudo required')
        
    STATE_DIR.mkdir(mode=0o700, exist_ok=True)
    with (STATE_DIR / 'lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        print(json.dumps(change(args.action, STATE_DIR / 'state.json'), indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
