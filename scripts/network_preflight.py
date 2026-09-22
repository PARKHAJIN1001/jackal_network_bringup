#!/usr/bin/env python3
"""Read-only network policy and process evidence; never write kernel or DDS settings."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

import ipfrag_session


ENV_KEYS = (
    'ROS_DOMAIN_ID', 'ROS_LOCALHOST_ONLY', 'RMW_IMPLEMENTATION', 'JACKAL_NETWORK_ROLE',
    'FASTRTPS_DEFAULT_PROFILES_FILE', 'FASTDDS_DEFAULT_PROFILES_FILE',
    'RMW_FASTRTPS_PUBLICATION_MODE', 'RMW_FASTRTPS_USE_QOS_FROM_XML',
    'SKIP_DEFAULT_XML', 'ROS_DISCOVERY_SERVER',
)


def xml_evidence(path):
    path = Path(path).expanduser().resolve(strict=True)
    data = path.read_bytes()
    root = ET.fromstring(data)
    for element in root.iter():
        element.tag = element.tag.rsplit('}', 1)[-1]
    participants = [p for p in root.iter('participant')
                    if p.get('is_default_profile', '').lower() == 'true']
    if len(participants) != 1:
        raise ValueError('Exactly one default participant is required')
    rtps = participants[0].find('rtps')
    if rtps is None or rtps.findtext('useBuiltinTransports', '').lower() != 'false':
        raise ValueError('Explicit user transports required for buffer verification')
    identifiers = [e.text for e in rtps.findall('userTransports/transport_id')]
    transports = {e.findtext('transport_id'): e for e in root.iter('transport_descriptor')}
    buffers = []
    for name in identifiers:
        transport = transports.get(name)
        if transport is None:
            raise ValueError(f'Unknown transport: {name}')
        if transport.findtext('type') in ('UDPv4', 'UDPv6'):
            send, receive = (int(transport.findtext(k, '0'))
                             for k in ('sendBufferSize', 'receiveBufferSize'))
            if min(send, receive) <= 0:
                raise ValueError('Explicit positive UDP buffer requests required')
            buffers.append({'transport': name, 'send': send, 'receive': receive})
    if not buffers:
        raise ValueError('No explicit UDP transport found')
    return {'path': str(path), 'sha256_now': hashlib.sha256(data).hexdigest(),
            'udp_buffers': buffers,
            'xml_publication_modes': [e.text for e in root.iter('kind')
                                      if e.text in ('SYNCHRONOUS', 'ASYNCHRONOUS')]}


def inspect_environment(environment, kernel, ipfrag, role='laptop'):
    selected = {key: environment.get(key, '') for key in ENV_KEYS}
    checks = {
        'domain': selected['ROS_DOMAIN_ID'] == '1',
        'role': selected['JACKAL_NETWORK_ROLE'] == role,
        'rmw': selected['RMW_IMPLEMENTATION'] == 'rmw_fastrtps_cpp',
        'localhost': selected['ROS_LOCALHOST_ONLY'] == '0',
        'publication_mode': selected['RMW_FASTRTPS_PUBLICATION_MODE'] == 'ASYNCHRONOUS',
        'default_xml_enabled': selected['SKIP_DEFAULT_XML'] != '1',
        'ipfrag': ipfrag.get('ready') is True,
    }
    profiles, errors = {}, []
    for key in ('FASTRTPS_DEFAULT_PROFILES_FILE', 'FASTDDS_DEFAULT_PROFILES_FILE'):
        try:
            if not selected[key]:
                raise ValueError(f'{key} is unset')
            profiles[key] = xml_evidence(selected[key])
        except (OSError, ValueError, ET.ParseError) as error:
            errors.append(str(error))
    checks['xml_profiles'] = len(profiles) == 2
    checks['xml_aliases_match'] = (len(profiles) == 2 and
                                   len({p['path'] for p in profiles.values()}) == 1)
    for key, profile in profiles.items():
        for request in profile['udp_buffers']:
            for field, limit in (('receive', 'rmem_max'), ('send', 'wmem_max')):
                checks[f'{key}:{request["transport"]}:{limit}'] = (
                    type(kernel.get(limit)) is int and kernel[limit] >= request[field])
    return {'schema': 1, 'ready': all(checks.values()), 'checks': checks,
            'environment': selected, 'profiles': profiles, 'kernel': kernel, 'ipfrag': ipfrag,
            'errors': errors, 'xml_load_verified': False,
            'meaning': 'Configured inputs only. Environment paths and current file hashes '
                       'do not prove a running DDS participant loaded these bytes. '
                       'No discovery, buffer, time-sync or persistent policy is changed.'}


def process_evidence(pid, proc=Path('/proc')):
    folder = proc / str(pid)
    before = (folder / 'stat').read_text().rsplit(')', 1)[1].split()[19]
    # Only these transport keys leave /proc; unrelated environment secrets are omitted.
    environment = {}
    for entry in (folder / 'environ').read_bytes().split(b'\0'):
        key, separator, value = entry.partition(b'=')
        if separator and key.decode(errors='replace') in ENV_KEYS:
            environment[key.decode()] = value.decode(errors='replace')
    profiles = {}
    for key in ('FASTRTPS_DEFAULT_PROFILES_FILE', 'FASTDDS_DEFAULT_PROFILES_FILE'):
        requested = environment.get(key)
        if requested:
            try:
                # Resolve within the target process root/cwd, not the observer's cwd.
                path = folder / 'root' / requested.lstrip('/') if requested.startswith('/') else (
                    folder / 'cwd' / requested)
                profiles[key] = {'requested_path': requested, **xml_evidence(path)}
            except (OSError, ValueError, ET.ParseError) as error:
                profiles[key] = {'requested_path': requested, 'error': str(error)}
    libraries = sorted({
        line.split()[-1] for line in (folder / 'maps').read_text().splitlines()
        if '/' in line and any(name in line for name in
                               ('libfastrtps', 'libfastdds', 'libfastcdr', 'librmw'))})
    after = (folder / 'stat').read_text().rsplit(')', 1)[1].split()[19]
    if before != after:
        raise ValueError('PID reused during inspection')
    return {'pid': pid, 'start_ticks': before, 'environment': environment,
            'profiles_current_on_disk': profiles, 'mapped_dds_libraries': libraries,
            'xml_load_verified': False,
            'meaning': 'Process environment and mapped libraries observed; actual XML '
                       'load/content at initialization requires startup trace evidence.'}


def report(role='laptop', pids=()):
    kernel = {}
    for name in ('rmem_max', 'wmem_max'):
        kernel[name] = int((Path('/proc/sys/net/core') / name).read_text())
    ipfrag = ipfrag_session.status(
        state_path=ipfrag_session.STATE_DIR / 'state.json',
        legacy_path=ipfrag_session.LEGACY_DIR / 'state.json')
    result = inspect_environment(os.environ, kernel, ipfrag, role)
    result['processes'] = []
    for pid in pids:
        try:
            result['processes'].append(process_evidence(pid))
        except (OSError, ValueError, IndexError) as error:
            result['processes'].append({'pid': pid, 'error': str(error)})
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--role', choices=('laptop', 'nuc', 'radxa'), default='laptop')
    parser.add_argument('--pid', type=int, action='append', default=[])
    args = parser.parse_args(argv)
    try:
        result = report(args.role, args.pid)
        print(json.dumps(result, indent=2))
        return int(not result['ready']) if args.check else 0
    except (OSError, ValueError, KeyError) as error:
        print(json.dumps({'ready': False, 'error': str(error)}))
        return 2


if __name__ == '__main__':
    sys.exit(main())
