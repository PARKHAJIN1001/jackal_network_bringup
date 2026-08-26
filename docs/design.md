# Jackal–Laptop ROS 2 Network Bringup Design

## 1. Goal

Connect the Clearpath Jackal control PC and a laptop directly over Ethernet and use ROS 2 DDS discovery so that both machines can share ROS 2 topics, services, actions, and TF data.

The intended final workflow is:

```bash
# Jackal control PC
source ~/jackal_ws/install/setup.bash
ros2 launch jackal_network_bringup robot.launch.py

# Laptop
source ~/jackal_ws/install/setup.bash
ros2 launch jackal_network_bringup laptop.launch.py
```

The package should make the ROS-side network configuration reproducible and should eventually allow Nav2 on the Jackal to be monitored and commanded from the laptop.

---

## 2. System Architecture

```text
                    Ethernet LAN
                 192.168.50.0/24

       Laptop                           Jackal PC
   192.168.50.1                      192.168.50.2
        │                                  │
        └──────────── ROS 2 DDS ───────────┘

   RViz2 / CLI                       Jackal drivers
   Monitoring                         Sensors
   Goal commands                      TF / odometry
   Research nodes                     Localization
                                      Nav2
                                      Controller
```

Recommended responsibility split:

### Jackal PC

- Jackal hardware bringup
- Sensor drivers
- TF publishers
- Odometry
- Localization
- Nav2
- Local controller
- `/cmd_vel` generation

### Laptop

- RViz2
- ROS 2 CLI
- Nav2 goal commands
- Topic monitoring
- Data logging
- Experimental / research nodes

The local navigation controller should remain on the Jackal PC so that temporary Ethernet interruptions do not immediately remove the robot's local control capability.

---

## 3. Network Layer

Use a dedicated static-IP Ethernet subnet.

Recommended addresses:

```text
Laptop:    192.168.50.1/24
Jackal PC: 192.168.50.2/24
```

No gateway or DNS server is required for a direct Ethernet connection.

The operating system, not ROS 2, should configure these IP addresses.

Reason:

```text
NetworkManager / OS
        ↓
IP configuration and interface management

ROS 2 bringup package
        ↓
DDS configuration and ROS nodes
```

Avoid calling `sudo`, `nmcli`, or other privileged network configuration commands from a ROS 2 launch file.

---

## 4. ROS 2 DDS Configuration

Initial shared ROS 2 environment:

```bash
export ROS_DOMAIN_ID=42
export ROS_LOCALHOST_ONLY=0
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
```

Both machines must use compatible values.

### ROS_DOMAIN_ID

Use one fixed domain for the Jackal experimental system:

```text
ROS_DOMAIN_ID=42
```

This logically separates this robot system from unrelated ROS 2 nodes on the same network.

### ROS_LOCALHOST_ONLY

```text
ROS_LOCALHOST_ONLY=0
```

Remote DDS communication must be enabled.

### RMW implementation

Initial recommendation:

```text
rmw_cyclonedds_cpp
```

Cyclone DDS makes it straightforward to explicitly control the network interface later if the Jackal PC or laptop has multiple active interfaces such as Ethernet and Wi-Fi.

---

## 5. Why Use an Environment Hook

A launch file can set environment variables for processes that it starts, but it cannot modify the environment of the parent terminal.

For example, setting `ROS_DOMAIN_ID` inside `robot.launch.py` does not automatically affect:

```bash
ros2 topic list
```

executed later from another shell.

Therefore, the package should install an `ament` environment hook.

Expected behavior:

```bash
source ~/jackal_ws/install/setup.bash
```

automatically configures:

```text
ROS_DOMAIN_ID=42
ROS_LOCALHOST_ONLY=0
RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
```

for that shell.

---

## 6. ROS 2 Package

Package name:

```text
jackal_network_bringup
```

Build type:

```text
ament_cmake
```

Initial directory structure:

```text
jackal_network_bringup/
├── CMakeLists.txt
├── package.xml
├── config/
├── env-hooks/
│   └── ros_network.sh
├── launch/
│   ├── robot.launch.py
│   ├── laptop.launch.py
│   └── network_test.launch.py
└── scripts/
    └── check_network.sh
```

---

## 7. Launch Responsibilities

### `robot.launch.py`

Final target:

```text
robot.launch.py
├── Jackal hardware bringup
├── LiDAR / camera drivers
├── robot_state_publisher / TF
├── localization
└── Nav2
```

This launch file runs on the Jackal control PC.

### `laptop.launch.py`

Final target:

```text
laptop.launch.py
├── RViz2
└── optional monitoring / research nodes
```

This launch file runs on the laptop.

Nav2 itself should not normally be launched a second time on the laptop.

### `network_test.launch.py`

Used before integrating Nav2.

Purpose:

- verify DDS discovery
- verify cross-machine topic communication
- verify ROS domain configuration
- verify selected RMW implementation

---

## 8. Implementation Stages

### Stage 1 — Create the package

Create the package and base directory structure.

### Stage 2 — Add ROS environment hook

Implement:

```text
ROS_DOMAIN_ID
ROS_LOCALHOST_ONLY
RMW_IMPLEMENTATION
```

through `env-hooks/ros_network.sh`.

Update `CMakeLists.txt` so the hook is installed by `ament_environment_hooks()`.

### Stage 3 — Verify basic DDS communication

Use simple publisher/subscriber nodes before starting Nav2.

Example:

Jackal:

```bash
ros2 run demo_nodes_cpp talker
```

Laptop:

```bash
ros2 run demo_nodes_py listener
```

Verify:

```bash
ros2 node list
ros2 topic list
```

### Stage 4 — Integrate Jackal bringup

Include the existing Clearpath / Jackal launch stack inside `robot.launch.py`.

Do not replace the known-working robot bringup unnecessarily.

### Stage 5 — Integrate Nav2

Run localization and Nav2 on the Jackal PC.

Verify from the laptop:

```bash
ros2 action list
```

and confirm that Nav2 actions such as:

```text
/navigate_to_pose
```

are visible.

### Stage 6 — Add laptop RViz bringup

Create `laptop.launch.py` that loads a project-specific RViz configuration.

The laptop should be able to:

- view `/map`
- view `/odom`
- view `/tf`
- view `/scan` or point-cloud topics
- inspect plans
- send Nav2 goals

### Stage 7 — Multi-interface DDS configuration

Only add explicit Cyclone DDS interface selection if necessary.

This becomes relevant when either machine simultaneously uses interfaces such as:

```text
Ethernet
Wi-Fi
sensor-specific Ethernet
Docker bridge interfaces
```

Do not hard-code interface names until the actual names are confirmed with:

```bash
ip -br link
ip -br addr
```

### Stage 8 — Clock synchronization

Ensure the Jackal PC and laptop have synchronized clocks.

This is important for:

- TF
- LiDAR timestamps
- camera timestamps
- odometry
- localization
- Nav2

If the system must operate without Internet access, configure one machine as a local NTP/chrony server and the other as its client.

---

## 9. Initial Package Creation Commands

Assuming the workspace is:

```text
~/jackal_ws
```

create the package with:

```bash
source /opt/ros/humble/setup.bash

mkdir -p ~/jackal_ws/src
cd ~/jackal_ws/src

ros2 pkg create jackal_network_bringup \
  --build-type ament_cmake \
  --license Apache-2.0 \
  --dependencies launch launch_ros
```

Create the initial directories and files:

```bash
cd ~/jackal_ws/src/jackal_network_bringup

mkdir -p launch config env-hooks scripts

touch launch/robot.launch.py
touch launch/laptop.launch.py
touch launch/network_test.launch.py

touch env-hooks/ros_network.sh
touch scripts/check_network.sh

chmod +x scripts/check_network.sh
```

Verify the structure:

```bash
tree ~/jackal_ws/src/jackal_network_bringup
```

Expected result:

```text
jackal_network_bringup/
├── CMakeLists.txt
├── package.xml
├── config
├── env-hooks
│   └── ros_network.sh
├── launch
│   ├── laptop.launch.py
│   ├── network_test.launch.py
│   └── robot.launch.py
└── scripts
    └── check_network.sh
```

Build the empty package once:

```bash
cd ~/jackal_ws

colcon build \
  --symlink-install \
  --packages-select jackal_network_bringup
```

Then source the workspace:

```bash
source ~/jackal_ws/install/setup.bash
```

Confirm that ROS 2 can find the package:

```bash
ros2 pkg prefix jackal_network_bringup
```

---

## 10. Immediate Next Implementation

The next concrete implementation step is to create:

```text
env-hooks/ros_network.sh
```

containing the shared ROS 2 environment configuration and modify `CMakeLists.txt` to install the environment hook.

After that, basic cross-machine DDS communication should be tested before adding Jackal hardware or Nav2 launch files.
