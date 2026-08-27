"""Non-composed Humble Nav2 navigation with an isolated velocity output."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.actions import SetEnvironmentVariable
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from nav2_common.launch import RewrittenYaml


def generate_launch_description():
    """Build Nav2 navigation nodes without exposing the platform cmd topic."""
    namespace = LaunchConfiguration('namespace')
    use_sim_time = LaunchConfiguration('use_sim_time')
    autostart = LaunchConfiguration('autostart')
    params_file = LaunchConfiguration('params_file')
    use_respawn = LaunchConfiguration('use_respawn')
    log_level = LaunchConfiguration('log_level')

    configured_params = RewrittenYaml(
        source_file=params_file,
        root_key=namespace,
        param_rewrites={
            'use_sim_time': use_sim_time,
            'autostart': autostart,
        },
        convert_types=True,
    )
    common = {
        'output': 'screen',
        'respawn': use_respawn,
        'respawn_delay': 2.0,
        'parameters': [configured_params],
        'arguments': ['--ros-args', '--log-level', log_level],
    }
    tf_remaps = [('/tf', 'tf'), ('/tf_static', 'tf_static')]
    lifecycle_nodes = [
        'controller_server',
        'smoother_server',
        'planner_server',
        'behavior_server',
        'bt_navigator',
        'waypoint_follower',
        'velocity_smoother',
    ]

    nodes = [
        Node(
            package='nav2_controller',
            executable='controller_server',
            remappings=tf_remaps + [('cmd_vel', 'cmd_vel_nav')],
            **common,
        ),
        Node(
            package='nav2_smoother',
            executable='smoother_server',
            name='smoother_server',
            remappings=tf_remaps,
            **common,
        ),
        Node(
            package='nav2_planner',
            executable='planner_server',
            name='planner_server',
            remappings=tf_remaps,
            **common,
        ),
        Node(
            package='nav2_behaviors',
            executable='behavior_server',
            name='behavior_server',
            remappings=tf_remaps + [('cmd_vel', 'cmd_vel_nav')],
            **common,
        ),
        Node(
            package='nav2_bt_navigator',
            executable='bt_navigator',
            name='bt_navigator',
            remappings=tf_remaps,
            **common,
        ),
        Node(
            package='nav2_waypoint_follower',
            executable='waypoint_follower',
            name='waypoint_follower',
            remappings=tf_remaps,
            **common,
        ),
        Node(
            package='nav2_velocity_smoother',
            executable='velocity_smoother',
            name='velocity_smoother',
            remappings=tf_remaps + [
                ('cmd_vel', 'cmd_vel_nav'),
                ('cmd_vel_smoothed', 'nav2_cmd_vel_unstamped'),
            ],
            **common,
        ),
        Node(
            package='nav2_lifecycle_manager',
            executable='lifecycle_manager',
            name='lifecycle_manager_navigation',
            output='screen',
            arguments=['--ros-args', '--log-level', log_level],
            parameters=[{
                'use_sim_time': use_sim_time,
                'autostart': autostart,
                'node_names': lifecycle_nodes,
            }],
        ),
        Node(
            package='jackal_network_bringup',
            executable='twist_stamper.py',
            name='nav2_twist_stamper',
            output='screen',
        ),
    ]

    declarations = [
        DeclareLaunchArgument('namespace', default_value='j100_0519'),
        DeclareLaunchArgument('use_sim_time', default_value='false'),
        DeclareLaunchArgument('autostart', default_value='true'),
        DeclareLaunchArgument('params_file'),
        DeclareLaunchArgument('use_respawn', default_value='false'),
        DeclareLaunchArgument('log_level', default_value='info'),
        SetEnvironmentVariable('RCUTILS_LOGGING_BUFFERED_STREAM', '1'),
    ]
    return LaunchDescription(declarations + nodes)
