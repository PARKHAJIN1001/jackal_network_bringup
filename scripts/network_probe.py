#!/usr/bin/env python3

"""Publish a role heartbeat and observe heartbeats from the other hosts."""

import json
import socket
import time

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import String


VALID_ROLES = ('laptop', 'nuc', 'radxa')


class NetworkProbe(Node):
    """Small bidirectional heartbeat probe for the robot LAN."""

    def __init__(self):
        super().__init__('network_probe')
        self.declare_parameter('role', '')
        self.declare_parameter('publish_period_sec', 1.0)

        self._role = self.get_parameter('role').get_parameter_value().string_value
        if self._role not in VALID_ROLES:
            raise ValueError(f'role must be one of {VALID_ROLES}: {self._role!r}')

        period = self.get_parameter(
            'publish_period_sec').get_parameter_value().double_value
        if period <= 0.0:
            raise ValueError('publish_period_sec must be greater than zero')

        qos = QoSProfile(
            depth=10,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
        )
        own_topic = f'/jackal_network/heartbeat/{self._role}'
        self._publisher = self.create_publisher(String, own_topic, qos)
        self._retained_subscriptions = []
        self._received_counts = {role: 0 for role in VALID_ROLES if role != self._role}
        for peer_role in self._received_counts:
            topic = f'/jackal_network/heartbeat/{peer_role}'
            subscription = self.create_subscription(
                String,
                topic,
                lambda message, role=peer_role: self._heartbeat_callback(role, message),
                qos,
            )
            self._retained_subscriptions.append(subscription)

        self._sequence = 0
        self._hostname = socket.gethostname()
        self._timer = self.create_timer(period, self._publish)
        self.get_logger().info(
            f'network probe role={self._role} publishing {own_topic}')

    def _publish(self):
        self._sequence += 1
        message = String()
        message.data = json.dumps({
            'hostname': self._hostname,
            'role': self._role,
            'sequence': self._sequence,
            'unix_time_ns': time.time_ns(),
        }, sort_keys=True)
        self._publisher.publish(message)

    def _heartbeat_callback(self, role, message):
        self._received_counts[role] += 1
        count = self._received_counts[role]
        if count == 1 or count % 10 == 0:
            self.get_logger().info(
                f'received heartbeat from {role} (count={count}): {message.data}')


def main(args=None):
    """Run the network probe until ROS shuts down."""
    rclpy.init(args=args)
    node = None
    try:
        node = NetworkProbe()
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
            try:
                node.destroy_node()
            except KeyboardInterrupt:
                pass
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
