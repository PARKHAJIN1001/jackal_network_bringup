"""Bring up NUC sensors, monitoring, and optional platform/Nav2 stacks."""

import os

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.actions import GroupAction
from launch.actions import IncludeLaunchDescription
from launch.actions import OpaqueFunction
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import AndSubstitution
from launch.substitutions import LaunchConfiguration
from launch.substitutions import PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.actions import PushRosNamespace
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare


def _validate_nav2_files(context):
    paths = {
        'map': LaunchConfiguration('nav2_map').perform(context),
        'params': LaunchConfiguration('nav2_params_file').perform(context),
    }
    missing = [f'{name}={path}' for name, path in paths.items()
               if not os.path.isfile(path)]
    if missing:
        raise RuntimeError(
            'Nav2 input file(s) are missing: ' + ', '.join(missing))
    return []


def _nav2_group(package_share):
    namespace = LaunchConfiguration('nav2_namespace')
    common_arguments = {
        'namespace': namespace,
        'use_sim_time': LaunchConfiguration('use_sim_time'),
        'params_file': LaunchConfiguration('nav2_params_file'),
        'autostart': 'true',
        'use_respawn': 'false',
    }
    return GroupAction(
        condition=IfCondition(LaunchConfiguration('launch_nav2')),
        actions=[
            PushRosNamespace(namespace),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(PathJoinSubstitution([
                    FindPackageShare('nav2_bringup'),
                    'launch',
                    'localization_launch.py',
                ])),
                launch_arguments={
                    **common_arguments,
                    'map': LaunchConfiguration('nav2_map'),
                    'use_composition': 'false',
                }.items(),
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(PathJoinSubstitution([
                    package_share,
                    'launch',
                    'nav2_navigation.launch.py',
                ])),
                launch_arguments=common_arguments.items(),
            ),
        ],
    )


def generate_launch_description():
    """Build the NUC-oriented launch description."""
    package_share = FindPackageShare('jackal_network_bringup')
    config_dir = PathJoinSubstitution([package_share, 'config'])

    declarations = [
        DeclareLaunchArgument('launch_platform', default_value='false'),
        DeclareLaunchArgument('launch_d455', default_value='true'),
        DeclareLaunchArgument('launch_mid360', default_value='false'),
        DeclareLaunchArgument('launch_mid360_scan', default_value='false'),
        DeclareLaunchArgument(
            'publish_mid360_static_tf', default_value='true'),
        DeclareLaunchArgument('launch_nav2', default_value='false'),
        DeclareLaunchArgument('forward_cmd_vel', default_value='false'),
        DeclareLaunchArgument('launch_network_probe', default_value='true'),
        DeclareLaunchArgument('use_sim_time', default_value='false'),
        DeclareLaunchArgument('nav2_namespace', default_value='j100_0519'),
        DeclareLaunchArgument('mid360_base_x', default_value='0.0'),
        DeclareLaunchArgument('mid360_base_y', default_value='0.0'),
        DeclareLaunchArgument('mid360_base_z', default_value='0.9'),
        DeclareLaunchArgument('mid360_base_qx', default_value='0.0'),
        DeclareLaunchArgument(
            'mid360_base_qy', default_value='0.25881904510252074'),
        DeclareLaunchArgument('mid360_base_qz', default_value='0.0'),
        DeclareLaunchArgument(
            'mid360_base_qw', default_value='0.9659258262890683'),
        DeclareLaunchArgument(
            'platform_launch_file',
            default_value=(
                '/etc/clearpath/platform/launch/platform-service.launch.py'),
        ),
        DeclareLaunchArgument(
            'nav2_map',
            default_value=PathJoinSubstitution([
                config_dir, 'maps', 'j100_0519.yaml']),
        ),
        DeclareLaunchArgument(
            'nav2_params_file',
            default_value=PathJoinSubstitution([
                config_dir, 'nav2', 'j100_0519.yaml']),
        ),
    ]

    platform = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            LaunchConfiguration('platform_launch_file')),
        condition=IfCondition(LaunchConfiguration('launch_platform')),
    )
    d455 = GroupAction(
        condition=IfCondition(LaunchConfiguration('launch_d455')),
        scoped=True,
        forwarding=False,
        actions=[
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(PathJoinSubstitution([
                    FindPackageShare('realsense2_camera'),
                    'launch',
                    'rs_launch.py',
                ])),
                launch_arguments={
                    'camera_name': 'camera',
                    'camera_namespace': 'camera',
                    'enable_color': 'true',
                    'enable_depth': 'true',
                    'enable_infra1': 'false',
                    'enable_infra2': 'false',
                    'pointcloud.enable': 'false',
                    'rgb_camera.color_profile': '640,480,15',
                    'depth_module.depth_profile': '640,480,15',
                }.items(),
            ),
        ],
    )
    mid360 = Node(
        package='livox_ros_driver2',
        executable='livox_ros_driver2_node',
        name='livox_lidar_publisher',
        output='screen',
        condition=IfCondition(LaunchConfiguration('launch_mid360')),
        parameters=[{
            'xfer_format': 0,
            'multi_topic': 0,
            'data_src': 0,
            'publish_freq': 15.0,
            'output_data_type': 0,
            'frame_id': 'livox_frame',
            'user_config_path': ParameterValue(
                PathJoinSubstitution([
                    config_dir, 'MID360_config_nuc.json']),
                value_type=str,
            ),
        }],
    )
    mid360_static_tf = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='base_to_mid360_static_tf',
        output='screen',
        condition=IfCondition(AndSubstitution(
            LaunchConfiguration('launch_mid360'),
            LaunchConfiguration('publish_mid360_static_tf'),
        )),
        arguments=[
            '--x', LaunchConfiguration('mid360_base_x'),
            '--y', LaunchConfiguration('mid360_base_y'),
            '--z', LaunchConfiguration('mid360_base_z'),
            '--qx', LaunchConfiguration('mid360_base_qx'),
            '--qy', LaunchConfiguration('mid360_base_qy'),
            '--qz', LaunchConfiguration('mid360_base_qz'),
            '--qw', LaunchConfiguration('mid360_base_qw'),
            '--frame-id', 'base_link',
            '--child-frame-id', 'livox_frame',
        ],
    )
    scan_converter = Node(
        package='pointcloud_to_laserscan',
        executable='pointcloud_to_laserscan_node',
        name='livox_pointcloud_to_laserscan',
        output='screen',
        condition=IfCondition(AndSubstitution(
            LaunchConfiguration('launch_mid360'),
            LaunchConfiguration('launch_mid360_scan'),
        )),
        remappings=[
            ('cloud_in', '/livox/lidar'),
            ('scan', '/scan'),
        ],
        parameters=[{
            'target_frame': 'base_link',
            'transform_tolerance': 0.05,
            'min_height': -0.25,
            'max_height': 1.00,
            'angle_min': -3.141592653589793,
            'angle_max': 3.141592653589793,
            'angle_increment': 0.008726646259972,
            'scan_time': 0.0667,
            'range_min': 0.20,
            'range_max': 30.0,
            'use_inf': True,
            'inf_epsilon': 1.0,
        }],
    )
    probe = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(PathJoinSubstitution([
            package_share, 'launch', 'network_test.launch.py',
        ])),
        condition=IfCondition(LaunchConfiguration('launch_network_probe')),
        launch_arguments={'role': 'nuc'}.items(),
    )
    safety_bridge = Node(
        package='jackal_network_bringup',
        executable='cmd_vel_safety_bridge.py',
        name='cmd_vel_safety_bridge',
        output='screen',
        parameters=[{
            'forward_cmd_vel': ParameterValue(
                LaunchConfiguration('forward_cmd_vel'), value_type=bool),
        }],
    )
    validate_nav2 = OpaqueFunction(
        function=_validate_nav2_files,
        condition=IfCondition(LaunchConfiguration('launch_nav2')),
    )

    return LaunchDescription(declarations + [
        platform,
        d455,
        mid360,
        mid360_static_tf,
        scan_converter,
        probe,
        safety_bridge,
        validate_nav2,
        _nav2_group(package_share),
    ])
