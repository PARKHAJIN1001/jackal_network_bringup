"""Bring up laptop monitoring and optionally the Phase-B Nav2 stack."""

import os

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.actions import GroupAction
from launch.actions import IncludeLaunchDescription
from launch.actions import OpaqueFunction
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch.substitutions import PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.actions import PushRosNamespace
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
    """Build the laptop-oriented launch description."""
    package_share = FindPackageShare('jackal_network_bringup')
    config_dir = PathJoinSubstitution([package_share, 'config'])

    declarations = [
        DeclareLaunchArgument('launch_rviz', default_value='true'),
        DeclareLaunchArgument('launch_nav2', default_value='false'),
        DeclareLaunchArgument('launch_network_probe', default_value='true'),
        DeclareLaunchArgument('use_sim_time', default_value='false'),
        DeclareLaunchArgument('nav2_namespace', default_value='j100_0519'),
        DeclareLaunchArgument(
            'rviz_config',
            default_value=PathJoinSubstitution([
                config_dir, 'jackal_network.rviz']),
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
        remappings=[
            ('/tf', '/j100_0519/tf'),
            ('/tf_static', '/j100_0519/tf_static'),
        ],
    )
    validate_nav2 = OpaqueFunction(
        function=_validate_nav2_files,
        condition=IfCondition(LaunchConfiguration('launch_nav2')),
    )

    return LaunchDescription(declarations + [
        probe,
        rviz,
        validate_nav2,
        _nav2_group(package_share),
    ])
