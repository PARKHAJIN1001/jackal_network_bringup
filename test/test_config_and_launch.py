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
        expected_peers = set(ROLE_IPS.values())
        if role in ('laptop', 'nuc'):
            expected_peers.remove(ROLE_IPS['radxa'])
        assert initial_peers == expected_peers
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
    translation = mid360['lidar_configs'][0]['extrinsic_parameter']
    assert all(isinstance(translation[axis], int) for axis in ('x', 'y', 'z'))

    with (CONFIG_DIR / 'jackal_network.rviz').open(
            encoding='utf-8') as stream:
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


def test_nuc_networkd_dropin_adds_robot_and_sensor_lan_addresses():
    dropin = CONFIG_DIR / 'systemd' / '50-jackal-lan.conf'
    assert dropin.read_text(encoding='utf-8').splitlines() == [
        '[Network]',
        'Address=192.168.50.2/24',
        'Address=192.168.1.5/24',
    ]


def test_clearpath_platform_service_uses_the_nuc_fastdds_profile():
    dropin = (
        CONFIG_DIR / 'systemd' / 'clearpath-platform.service.d'
        / '50-jackal-fastdds.conf'
    )
    lines = dropin.read_text(encoding='utf-8').splitlines()
    profile = (
        '/home/administrator/moai_navigation_ws/install/'
        'jackal_network_bringup/share/jackal_network_bringup/'
        'config/fastdds_nuc.xml'
    )
    assert lines == [
        '[Service]',
        'Environment="ROS_DOMAIN_ID=1"',
        'Environment="ROS_LOCALHOST_ONLY=0"',
        'Environment="RMW_IMPLEMENTATION=rmw_fastrtps_cpp"',
        f'Environment="FASTRTPS_DEFAULT_PROFILES_FILE={profile}"',
        f'Environment="FASTDDS_DEFAULT_PROFILES_FILE={profile}"',
    ]


def test_sensor_service_starts_the_safe_nuc_sensor_profile():
    service = CONFIG_DIR / 'systemd' / 'jackal-sensors.service'
    text = service.read_text(encoding='utf-8')

    assert 'Wants=network-online.target clearpath-platform.service' in text
    assert 'After=network-online.target clearpath-platform.service' in text
    assert 'User=administrator' in text
    assert 'Restart=on-failure' in text
    assert 'KillSignal=SIGINT' in text
    assert 'KillMode=mixed' in text
    assert (
        'ExecStart=/home/administrator/moai_navigation_ws/install/'
        'jackal_network_bringup/lib/jackal_network_bringup/'
        'start_nuc_sensors.sh'
    ) in text

    launcher = (PACKAGE_ROOT / 'scripts' / 'start_nuc_sensors.sh').read_text(
        encoding='utf-8')
    for argument in (
            'launch_platform:=false',
            'launch_d455:=true',
            'launch_mid360:=true',
            'launch_network_probe:=true'):
        assert argument in launcher
    assert 'source "$NETWORK_ENV_FILE" nuc' in launcher
    assert 'source "$LIVOX_PACKAGE_SETUP"' in launcher
    assert 'export COLCON_CURRENT_PREFIX="$LIVOX_PREFIX"' in launcher
    assert 'liblivox_lidar_sdk_shared.so' in launcher
    assert 'export LD_LIBRARY_PATH=' in launcher
    assert 'readonly SENSOR_LAN_IP="192.168.1.5"' in launcher
    assert 'exec ros2 launch jackal_network_bringup robot.launch.py' in launcher
    assert launcher.index('set -u') > launcher.index(
        'source "$NETWORK_ENV_FILE" nuc')


def test_mid360_driver_is_respawned_after_an_unexpected_exit():
    launch_text = (PACKAGE_ROOT / 'launch' / 'robot.launch.py').read_text(
        encoding='utf-8')
    mid360_start = launch_text.index('mid360 = Node(')
    mid360_end = launch_text.index('mid360_static_tf = Node(')
    mid360_block = launch_text[mid360_start:mid360_end]

    assert 'respawn=True' in mid360_block
    assert 'respawn_delay=5.0' in mid360_block


def test_sensor_launcher_fails_cleanly_when_setup_is_missing(tmp_path):
    missing = tmp_path / 'missing-setup.bash'
    environment = os.environ.copy()
    environment.update({
        'JACKAL_ROS_SETUP_FILE': str(missing),
        'JACKAL_WORKSPACE_SETUP_FILE': str(missing),
        'JACKAL_PACKAGE_SHARE_DIR': str(tmp_path / 'missing-share'),
    })
    result = subprocess.run(
        ['bash', str(PACKAGE_ROOT / 'scripts' / 'start_nuc_sensors.sh')],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert result.returncode == 1
    assert f'Required setup file is missing: {missing}' in result.stderr


def test_shell_scripts_have_valid_syntax():
    for path in (
            CONFIG_DIR / 'network_env.sh',
            PACKAGE_ROOT / 'scripts' / 'check_network.sh',
            PACKAGE_ROOT / 'scripts' / 'start_nuc_sensors.sh'):
        result = subprocess.run(
            ['bash', '-n', str(path)],
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr


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


def test_network_package_contains_no_navigation_or_drive_implementation():
    for path in (
            CONFIG_DIR / 'nav2',
            CONFIG_DIR / 'maps',
            PACKAGE_ROOT / 'launch' / 'nav2_navigation.launch.py',
            PACKAGE_ROOT / 'scripts' / 'twist_stamper.py',
            PACKAGE_ROOT / 'scripts' / 'cmd_vel_safety_bridge.py'):
        assert not path.exists()

    inspected_paths = (
        PACKAGE_ROOT / 'CMakeLists.txt',
        PACKAGE_ROOT / 'package.xml',
        PACKAGE_ROOT / 'launch' / 'robot.launch.py',
        PACKAGE_ROOT / 'launch' / 'laptop.launch.py',
        PACKAGE_ROOT / 'scripts' / 'check_network.sh',
        PACKAGE_ROOT / 'scripts' / 'start_nuc_sensors.sh',
    )
    implementation = '\n'.join(
        path.read_text(encoding='utf-8') for path in inspected_paths)
    for forbidden in (
            'nav2_bringup',
            'pointcloud_to_laserscan',
            'launch_nav2',
            'launch_mid360_scan',
            'cmd_vel',
            'send-zero-cmd'):
        assert forbidden not in implementation


def test_rviz_profile_is_sensor_monitoring_only():
    with (CONFIG_DIR / 'jackal_network.rviz').open(
            encoding='utf-8') as stream:
        config = yaml.safe_load(stream)

    manager = config['Visualization Manager']
    displays = manager['Displays']
    display_classes = {display['Class'] for display in displays}
    display_names = {display['Name'] for display in displays}
    tool_classes = {tool['Class'] for tool in manager['Tools']}

    assert manager['Global Options']['Fixed Frame'] == 'base_link'
    assert 'MID360 PointCloud' in display_names
    assert 'D455 Color' in display_names
    assert 'rviz_default_plugins/PointCloud2' in display_classes
    assert {
        'rviz_default_plugins/Map',
        'rviz_default_plugins/LaserScan',
        'rviz_default_plugins/Path',
    }.isdisjoint(display_classes)
    assert {
        'rviz_default_plugins/SetInitialPose',
        'rviz_default_plugins/SetGoal',
    }.isdisjoint(tool_classes)
