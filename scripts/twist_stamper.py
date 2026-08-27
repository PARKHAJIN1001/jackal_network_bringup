#!/usr/bin/env python3

"""Convert the isolated Humble Nav2 Twist output to TwistStamped."""

from geometry_msgs.msg import Twist
from geometry_msgs.msg import TwistStamped
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import QoSProfile
from rclpy.qos import ReliabilityPolicy


class TwistStamper(Node):
    """Add the local ROS clock and a frame ID to Nav2 velocity commands."""

    def __init__(self):
        super().__init__('nav2_twist_stamper')
        self.declare_parameter(
            'input_topic', '/j100_0519/nav2_cmd_vel_unstamped')
        self.declare_parameter('output_topic', '/j100_0519/nav2_cmd_vel')
        self.declare_parameter('frame_id', 'base_link')

        input_topic = self._required_string('input_topic')
        output_topic = self._required_string('output_topic')
        self._frame_id = self._required_string('frame_id')
        qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)
        self._publisher = self.create_publisher(TwistStamped, output_topic, qos)
        self._subscription = self.create_subscription(
            Twist, input_topic, self._callback, qos)
        self.get_logger().info(
            f'stamping Nav2 commands: {input_topic} -> {output_topic}')

    def _required_string(self, name):
        value = self.get_parameter(name).get_parameter_value().string_value
        if not value:
            raise ValueError(f'{name} must not be empty')
        return value

    def _callback(self, message):
        stamped = TwistStamped()
        stamped.header.stamp = self.get_clock().now().to_msg()
        stamped.header.frame_id = self._frame_id
        stamped.twist = message
        self._publisher.publish(stamped)


def main(args=None):
    """Run the converter until ROS shuts down."""
    rclpy.init(args=args)
    node = None
    try:
        node = TwistStamper()
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    except ValueError as error:
        if node is not None:
            node.get_logger().error(str(error))
        else:
            print(error)
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
