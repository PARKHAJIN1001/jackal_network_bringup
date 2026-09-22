"""Offline policy tests; no kernel changes or network activity."""

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = (ROOT / 'scripts' if (ROOT / 'scripts/network_preflight.py').is_file()
           else Path(__file__).parent)
sys.path.insert(0, str(SCRIPTS))
from network_preflight import inspect_environment, process_evidence  # noqa: E402,I100


def environment(tmp_path):
    path = tmp_path / 'dds.xml'
    path.write_text("""<profiles><transport_descriptors><transport_descriptor>
    <transport_id>udp</transport_id><type>UDPv4</type>
    <sendBufferSize>2097152</sendBufferSize><receiveBufferSize>26214400</receiveBufferSize>
    </transport_descriptor></transport_descriptors>
    <participant is_default_profile="true"><rtps><useBuiltinTransports>false</useBuiltinTransports>
    <userTransports><transport_id>udp</transport_id></userTransports></rtps></participant>
    </profiles>""")
    return {'ROS_DOMAIN_ID': '1', 'ROS_LOCALHOST_ONLY': '0', 'JACKAL_NETWORK_ROLE': 'laptop',
            'RMW_IMPLEMENTATION': 'rmw_fastrtps_cpp',
            'RMW_FASTRTPS_PUBLICATION_MODE': 'ASYNCHRONOUS',
            'FASTRTPS_DEFAULT_PROFILES_FILE': str(path),
            'FASTDDS_DEFAULT_PROFILES_FILE': str(path)}


def test_kernel_limits_follow_xml_not_another_hardcoded_policy(tmp_path):
    env = environment(tmp_path)
    kernel = {'rmem_max': 26214400, 'wmem_max': 2097152}
    assert inspect_environment(env, kernel, {'ready': True})['ready']
    for key in kernel:
        assert not inspect_environment(env, {**kernel, key: kernel[key] - 1},
                                       {'ready': True})['ready']
    assert not inspect_environment(env, kernel, {'ready': False})['ready']
    assert not inspect_environment(env, kernel, {'ready': True})['xml_load_verified']


@pytest.mark.parametrize('key,value', [
    ('RMW_FASTRTPS_PUBLICATION_MODE', 'SYNCHRONOUS'), ('ROS_DOMAIN_ID', '0'),
    ('RMW_IMPLEMENTATION', 'rmw_cyclonedds_cpp'), ('ROS_LOCALHOST_ONLY', '1'),
    ('SKIP_DEFAULT_XML', '1'), ('FASTDDS_DEFAULT_PROFILES_FILE', '/absent.xml'),
])
def test_invalid_or_ambiguous_configuration_fails_closed(tmp_path, key, value):
    env = {**environment(tmp_path), key: value}
    assert not inspect_environment(env, {'rmem_max': 26214400, 'wmem_max': 2097152},
                                   {'ready': True})['ready']


def test_process_environment_is_distinct_and_secrets_are_omitted(tmp_path):
    base = tmp_path / '123'
    base.mkdir()
    (base / 'stat').write_text('123 (process) S ' + '0 ' * 18 + '777 0')
    (base / 'environ').write_bytes(b'ROS_DOMAIN_ID=99\0SECRET_PASSWORD=hidden\0')
    (base / 'maps').write_text('aaa bbb ccc /opt/lib/libfastrtps.so.2.6\n')
    report = process_evidence(123, tmp_path)
    assert report['environment'] == {'ROS_DOMAIN_ID': '99'}
    assert not report['xml_load_verified']
    assert report['start_ticks'] == '777'
    assert report['mapped_dds_libraries'] == ['/opt/lib/libfastrtps.so.2.6']
