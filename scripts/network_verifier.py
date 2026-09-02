#!/usr/bin/env python3

"""Time-bounded network and sensor verification used by the shell CLI."""

import argparse
import time

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CameraInfo
from sensor_msgs.msg import Image
from sensor_msgs.msg import Imu
from sensor_msgs.msg import PointCloud2
from std_msgs.msg import String


HEARTBEAT_DURATION_SEC = 10.0
HEARTBEAT_MAX_GAP_SEC = 2.5
D455_DURATION_SEC = 30.0
D455_EXPECTED_RATE_HZ = 15.0
D455_MIN_RATE_HZ = D455_EXPECTED_RATE_HZ * 0.8
MID360_DURATION_SEC = 10.0
MID360_EXPECTED_RATE_HZ = 15.0
MID360_MIN_RATE_HZ = MID360_EXPECTED_RATE_HZ * 0.8


class TimedVerifier(Node):
    """Collect arrival timestamps while retaining each ROS subscription."""

    def __init__(self):
        super().__init__('jackal_network_verifier')
        self.arrivals = {}
        self._retained_subscriptions = []

    def watch(self, message_type, topic, qos):
        self.arrivals[topic] = []
        subscription = self.create_subscription(
            message_type,
            topic,
            lambda _message, name=topic: self.arrivals[name].append(
                time.monotonic()),
            qos,
        )
        self._retained_subscriptions.append(subscription)


def _spin_until(node, predicate, timeout_sec):
    deadline = time.monotonic() + timeout_sec
    while rclpy.ok() and time.monotonic() < deadline:
        try:
            rclpy.spin_once(node, timeout_sec=0.2)
        except ExternalShutdownException:
            return False
        if predicate():
            return True
    return False


def verify_heartbeat(role):
    """Require heartbeat arrivals spanning ten seconds without a long gap."""
    topic = f'/jackal_network/heartbeat/{role}'
    node = TimedVerifier()
    node.watch(String, topic, 10)

    def continuous_window_complete():
        arrivals = node.arrivals[topic]
        if len(arrivals) < 2:
            return False
        gaps = [later - earlier
                for earlier, later in zip(arrivals, arrivals[1:])]
        for index, gap in enumerate(gaps):
            if gap > HEARTBEAT_MAX_GAP_SEC:
                node.arrivals[topic] = arrivals[index + 1:]
                return False
        return arrivals[-1] - arrivals[0] >= HEARTBEAT_DURATION_SEC

    success = _spin_until(node, continuous_window_complete, 16.0)
    arrivals = node.arrivals[topic]
    if success:
        duration = arrivals[-1] - arrivals[0]
        print(
            f'heartbeat role={role} messages={len(arrivals)} '
            f'duration={duration:.2f}s')
    else:
        print(
            f'heartbeat role={role} did not provide a continuous '
            f'{HEARTBEAT_DURATION_SEC:.0f}s window')
    node.destroy_node()
    return success


def _message_rate(arrivals):
    if len(arrivals) < 2 or arrivals[-1] <= arrivals[0]:
        return 0.0
    return (len(arrivals) - 1) / (arrivals[-1] - arrivals[0])


def verify_d455():
    """Check all required streams and the two image rates concurrently."""
    color = '/camera/camera/color/image_raw'
    color_info = '/camera/camera/color/camera_info'
    depth = '/camera/camera/depth/image_rect_raw'
    depth_info = '/camera/camera/depth/camera_info'
    topics = (color, color_info, depth, depth_info)

    node = TimedVerifier()
    node.watch(Image, color, qos_profile_sensor_data)
    node.watch(CameraInfo, color_info, qos_profile_sensor_data)
    node.watch(Image, depth, qos_profile_sensor_data)
    node.watch(CameraInfo, depth_info, qos_profile_sensor_data)

    def sample_window_complete():
        image_times = (node.arrivals[color], node.arrivals[depth])
        return all(
            len(values) >= 2
            and values[-1] - values[0] >= D455_DURATION_SEC
            for values in image_times
        )

    window_complete = _spin_until(node, sample_window_complete, 36.0)
    publishers_ok = True
    messages_ok = True
    for topic in topics:
        publisher_count = len(node.get_publishers_info_by_topic(topic))
        message_count = len(node.arrivals[topic])
        print(
            f'D455 topic={topic} publishers={publisher_count} '
            f'messages={message_count}')
        publishers_ok = publishers_ok and publisher_count > 0
        messages_ok = messages_ok and message_count > 0

    rates_ok = True
    for topic in (color, depth):
        rate = _message_rate(node.arrivals[topic])
        print(
            f'D455 topic={topic} measured_rate={rate:.2f}Hz '
            f'minimum={D455_MIN_RATE_HZ:.2f}Hz')
        rates_ok = rates_ok and rate >= D455_MIN_RATE_HZ

    node.destroy_node()
    return window_complete and publishers_ok and messages_ok and rates_ok


def verify_mid360():
    """Check MID360 PointCloud2/IMU delivery and the point-cloud rate."""
    lidar = '/livox/lidar'
    imu = '/livox/imu'

    node = TimedVerifier()
    node.watch(PointCloud2, lidar, qos_profile_sensor_data)
    node.watch(Imu, imu, qos_profile_sensor_data)

    def sample_window_complete():
        arrivals = node.arrivals[lidar]
        return (
            len(arrivals) >= 2
            and arrivals[-1] - arrivals[0] >= MID360_DURATION_SEC
            and bool(node.arrivals[imu])
        )

    window_complete = _spin_until(node, sample_window_complete, 16.0)
    publishers_ok = True
    messages_ok = True
    for topic in (lidar, imu):
        publisher_count = len(node.get_publishers_info_by_topic(topic))
        message_count = len(node.arrivals[topic])
        print(
            f'MID360 topic={topic} publishers={publisher_count} '
            f'messages={message_count}')
        publishers_ok = publishers_ok and publisher_count > 0
        messages_ok = messages_ok and message_count > 0

    rate = _message_rate(node.arrivals[lidar])
    print(
        f'MID360 topic={lidar} measured_rate={rate:.2f}Hz '
        f'minimum={MID360_MIN_RATE_HZ:.2f}Hz')
    rates_ok = rate >= MID360_MIN_RATE_HZ

    node.destroy_node()
    return window_complete and publishers_ok and messages_ok and rates_ok


def main(args=None):
    """Parse the internal verifier command and return a process status."""
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest='command', required=True)
    heartbeat = subparsers.add_parser('heartbeat')
    heartbeat.add_argument('role', choices=('nuc', 'laptop', 'radxa'))
    subparsers.add_parser('d455')
    subparsers.add_parser('mid360')
    parsed = parser.parse_args(args)

    rclpy.init()
    try:
        if parsed.command == 'heartbeat':
            success = verify_heartbeat(parsed.role)
        elif parsed.command == 'd455':
            success = verify_d455()
        else:
            success = verify_mid360()
    finally:
        if rclpy.ok():
            rclpy.shutdown()
    raise SystemExit(0 if success else 1)


if __name__ == '__main__':
    main()
