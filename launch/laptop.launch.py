"""Bring up laptop-side network probing and sensor visualization."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.actions import IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch.substitutions import PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    """Build the laptop-oriented launch description."""
    package_share = FindPackageShare('jackal_network_bringup')
    config_dir = PathJoinSubstitution([package_share, 'config'])

    declarations = [
        DeclareLaunchArgument('launch_rviz', default_value='true'),
        DeclareLaunchArgument('launch_network_probe', default_value='true'),
        DeclareLaunchArgument(
            'rviz_config',
            default_value=PathJoinSubstitution([
                config_dir, 'jackal_network.rviz']),
        ),
    ]

    probe = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(PathJoinSubstitution([
            package_share, 'launch', 'network_test.launch.py',
        ])),
        condition=IfCondition(LaunchConfiguration('launch_network_probe')),
        launch_arguments={'role': 'laptop'}.items(),
    )
    rviz = Node(
        package='rviz2',
        executable='rviz2',
        name='jackal_network_rviz',
        output='screen',
        condition=IfCondition(LaunchConfiguration('launch_rviz')),
        arguments=['-d', LaunchConfiguration('rviz_config')],
    )

    return LaunchDescription(declarations + [
        probe,
        rviz,
    ])
