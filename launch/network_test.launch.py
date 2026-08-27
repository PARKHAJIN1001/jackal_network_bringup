"""Launch one role-aware network heartbeat probe."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.actions import OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


VALID_ROLES = ('nuc', 'laptop', 'radxa')


def _probe_node(context):
    role = LaunchConfiguration('role').perform(context)
    if role not in VALID_ROLES:
        raise RuntimeError(
            f"role must be one of {', '.join(VALID_ROLES)}; got {role!r}")
    return [Node(
        package='jackal_network_bringup',
        executable='network_probe.py',
        name=f'network_probe_{role}',
        output='screen',
        parameters=[{'role': role}],
    )]


def generate_launch_description():
    """Build the role-selectable heartbeat launch description."""
    return LaunchDescription([
        DeclareLaunchArgument(
            'role',
            default_value='laptop',
            description='Heartbeat role: nuc, laptop, or radxa',
        ),
        OpaqueFunction(function=_probe_node),
    ])
