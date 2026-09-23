"""Bring up NUC sensors and network monitoring."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.actions import GroupAction
from launch.actions import IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import AndSubstitution
from launch.substitutions import LaunchConfiguration
from launch.substitutions import PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    """Build the NUC-oriented launch description."""
    package_share = FindPackageShare('jackal_network_bringup')
    config_dir = PathJoinSubstitution([package_share, 'config'])

    declarations = [
        DeclareLaunchArgument('launch_platform', default_value='false'),
        DeclareLaunchArgument('launch_d455', default_value='true'),
        DeclareLaunchArgument('launch_mid360', default_value='false'),
        DeclareLaunchArgument(
            'publish_mid360_static_tf', default_value='true'),
        DeclareLaunchArgument('launch_network_probe', default_value='true'),
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
                    'enable_depth': 'false',
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
        respawn=True,
        respawn_delay=5.0,
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
    probe = Node(
        package='jackal_network_bringup',
        executable='network_probe.py',
        name='network_probe_nuc',
        output='screen',
        condition=IfCondition(LaunchConfiguration('launch_network_probe')),
        parameters=[{'role': 'nuc'}],
    )
    return LaunchDescription(declarations + [
        platform,
        d455,
        mid360,
        mid360_static_tf,
        probe,
    ])
