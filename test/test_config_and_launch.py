"""Static tests for installed network, launch, and safety configuration."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import xml.etree.ElementTree as element_tree

from launch import LaunchDescription
import yaml

os.environ.setdefault('ROS_LOG_DIR', '/tmp/jackal_network_bringup_test_logs')


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = PACKAGE_ROOT / 'config'
FAST_DDS_NAMESPACE = {
    'f': 'http://www.eprosima.com/XMLSchemas/fastRTPS_Profiles',
}
ROLE_IPS = {
    'laptop': '192.168.50.1',
    'nuc': '192.168.50.2',
    'radxa': '192.168.50.3',
}


def _load_launch(filename):
    path = PACKAGE_ROOT / 'launch' / filename
    spec = importlib.util.spec_from_file_location(
        filename.replace('.', '_'), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.generate_launch_description()


def test_public_launch_files_generate_descriptions():
    for filename in (
            'network_test.launch.py',
            'robot.launch.py',
            'laptop.launch.py'):
        assert isinstance(_load_launch(filename), LaunchDescription)


def test_role_profiles_are_unicast_only_and_keep_shm():
    peer_addresses = set(ROLE_IPS.values())
    for role, role_ip in ROLE_IPS.items():
        root = element_tree.parse(
            CONFIG_DIR / f'fastdds_{role}.xml').getroot()
        allowlist = {
            item.text
            for item in root.findall(
                './/f:interfaceWhiteList/f:address', FAST_DDS_NAMESPACE)
        }
        initial_peers = {
            item.text
            for item in root.findall(
                './/f:initialPeersList//f:address', FAST_DDS_NAMESPACE)
        }
        transports = {
            item.text
            for item in root.findall(
                './/f:transport_descriptor/f:type', FAST_DDS_NAMESPACE)
        }
        avoid_multicast = root.find(
            './/f:avoid_builtin_multicast', FAST_DDS_NAMESPACE)
        builtin_transports = root.find(
            './/f:useBuiltinTransports', FAST_DDS_NAMESPACE)

        assert allowlist == {role_ip}
        assert initial_peers == peer_addresses
        assert transports == {'UDPv4', 'SHM'}
        assert avoid_multicast.text == 'true'
        assert builtin_transports.text == 'false'

    local_root = element_tree.parse(
        CONFIG_DIR / 'fastdds_local.xml').getroot()
    local_transports = {
        item.text
        for item in local_root.findall(
            './/f:transport_descriptor/f:type', FAST_DDS_NAMESPACE)
    }
    assert local_transports == {'UDPv4', 'SHM'}


def test_structured_config_files_parse():
    with (CONFIG_DIR / 'MID360_config_nuc.json').open(encoding='utf-8') as stream:
        mid360 = json.load(stream)
    assert mid360['MID360']['host_net_info']['point_data_ip'] == '192.168.1.5'
    assert mid360['lidar_configs'][0]['ip'] == '192.168.1.130'

    for path in (
            CONFIG_DIR / 'nav2' / 'j100_0519.yaml',
            CONFIG_DIR / 'jackal_network.rviz'):
        with path.open(encoding='utf-8') as stream:
            assert isinstance(yaml.safe_load(stream), dict)


def test_network_env_refuses_direct_execution():
    result = subprocess.run(
        ['bash', str(CONFIG_DIR / 'network_env.sh'), 'laptop'],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert 'must be sourced' in result.stderr


def test_shell_scripts_have_valid_syntax():
    for path in (
            CONFIG_DIR / 'network_env.sh',
            PACKAGE_ROOT / 'scripts' / 'check_network.sh'):
        result = subprocess.run(
            ['bash', '-n', str(path)],
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr


def test_send_zero_command_rejects_values_before_ros_access():
    result = subprocess.run(
        [
            'bash',
            str(PACKAGE_ROOT / 'scripts' / 'check_network.sh'),
            'send-zero-cmd',
            '0.1',
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert 'does not accept velocity arguments' in result.stderr


def test_no_automatic_middleware_environment_hook_remains():
    assert not (PACKAGE_ROOT / 'env-hooks' / 'ros_network.sh').exists()
    cmake = (PACKAGE_ROOT / 'CMakeLists.txt').read_text(encoding='utf-8')
    package = (PACKAGE_ROOT / 'package.xml').read_text(encoding='utf-8')
    assert 'ament_environment_hooks' not in cmake
    assert 'rmw_cyclonedds_cpp' not in package


def test_probe_does_not_shadow_rclpy_subscription_storage():
    probe = (PACKAGE_ROOT / 'scripts' / 'network_probe.py').read_text(
        encoding='utf-8')
    assert 'self._subscriptions' not in probe
    assert 'self._retained_subscriptions' in probe


def test_realsense_launch_uses_current_profile_argument_names():
    launch = (PACKAGE_ROOT / 'launch' / 'robot.launch.py').read_text(
        encoding='utf-8')
    assert "'rgb_camera.color_profile': '640,480,15'" in launch
    assert "'depth_module.depth_profile': '640,480,15'" in launch


def test_safety_bridge_adapts_to_clearpath_twist_output():
    bridge = (PACKAGE_ROOT / 'scripts' / 'cmd_vel_safety_bridge.py').read_text(
        encoding='utf-8')
    assert 'create_subscription(\n            TwistStamped' in bridge
    assert 'create_publisher(\n                Twist' in bridge
