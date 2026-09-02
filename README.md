# Jackal network bringup

NUC에 연결된 Jackal MCU, Intel RealSense D455, Livox MID360의 ROS 2
토픽을 전용 유선망을 통해 Laptop에서 조회하기 위한 ROS 2 Humble 패키지다.

현재 구성은 다음과 같다.

```text
Jackal MCU ──USB──┐
D455 ───────USB──┤
MID360 ─Ethernet─┤ NUC ──192.168.50.0/24── Laptop
                 └──────────────────────────
```

- NUC: Clearpath platform, D455, MID360, sensor launch
- Laptop: ROS 2 CLI, RViz, 데이터 확인
- ROS domain: `1`
- RMW: `rmw_fastrtps_cpp`
- 실제 주행, Nav2, 속도 명령 전달은 현재 사용 범위에 포함하지 않는다.

## 1. Prerequisites

### 1.1 하드웨어와 주소

| 장치 | 인터페이스/주소 | 용도 |
|---|---|---|
| Laptop | `192.168.50.1/24` | ROS 2 조회 |
| NUC `br0` | `192.168.50.2/24` | Laptop 통신 |
| NUC `br0` | `192.168.1.5/24` | MID360 통신 |
| MID360 | `192.168.1.130` | LiDAR |

NUC의 `enp86s0`는 `br0`의 slave이므로 IP 주소는 `enp86s0`가 아니라
`br0`에 설정한다.

### 1.2 필수 소프트웨어

두 장비 공통:

- Ubuntu 22.04
- ROS 2 Humble
- `rmw_fastrtps_cpp`
- `python3-colcon-common-extensions`
- 이 저장소의 `jackal_network_bringup` 패키지

NUC:

- Clearpath Humble stack과 `/etc/clearpath/setup.bash`
- `realsense2_camera`
- Livox-SDK2와 `livox_ros_driver2`
- 현재 Livox install prefix:
  `/home/administrator/ws_livox/install/local_setup.bash`
- `openssh-server`

Laptop:

- `rviz2` — 시각화할 때 사용
- `clearpath_platform_msgs` — Clearpath 전용 메시지를 직접
  `ros2 topic echo`할 때만 필요

`pointcloud_to_laserscan`은 `/scan` 변환에만 필요하다. 현재 NUC에는 설치하지
않았으며, raw MID360 PointCloud2 수신에는 필요하지 않다.

설치 여부는 다음처럼 확인한다.

NUC:

```bash
source /opt/ros/humble/setup.bash
source /etc/clearpath/setup.bash
source ~/ws_livox/install/local_setup.bash

ros2 pkg prefix rmw_fastrtps_cpp
ros2 pkg prefix realsense2_camera
ros2 pkg prefix livox_ros_driver2
```

Laptop:

```bash
source /opt/ros/humble/setup.bash

ros2 pkg prefix rmw_fastrtps_cpp
ros2 pkg prefix rviz2
```

### 1.3 패키지 빌드

NUC와 Laptop 각각의 workspace에 이 패키지가 있어야 한다. 두 장비에서 각각
빌드한다.

```bash
cd ~/moai_navigation_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-select jackal_network_bringup
source install/setup.bash
```

필요한 ROS 의존성을 처음 설치할 때는 다음을 사용할 수 있다.

```bash
cd ~/moai_navigation_ws
rosdep install --from-paths src --ignore-src -r -y
```

Livox-SDK2와 `livox_ros_driver2`는 별도 vendor workspace이므로 위
`rosdep` 명령만으로 준비되지 않을 수 있다.

### 1.4 Laptop 유선망 설정

`jackal-lan` NetworkManager profile이 없다면 한 번 생성한다. 현재 Laptop의
유선 인터페이스 이름은 `eno1`이다.

```bash
sudo nmcli connection add type ethernet ifname eno1 con-name jackal-lan \
  ipv4.method manual ipv4.addresses 192.168.50.1/24 \
  ipv4.never-default yes ipv6.method disabled
sudo nmcli connection modify jackal-lan \
  ipv4.gateway "" ipv4.dns "" connection.autoconnect yes
```

연결하고 확인한다.

```bash
sudo nmcli connection up jackal-lan
ip -br address show eno1
ping -c 3 192.168.50.2
```

`eno1`에 `192.168.50.1/24`가 있고 NUC ping이 성공해야 한다.

### 1.5 NUC 네트워크 영구 설정

패키지의 systemd-networkd drop-in은 NUC `br0`에
`192.168.50.2/24`와 `192.168.1.5/24`를 추가한다. NUC에서 한 번 설치한다.
파일명이 줄바꿈으로 나뉘지 않도록 다음 명령은 한 줄로 실행한다.

```bash
sudo install -D -m 0644 ~/moai_navigation_ws/src/jackal_network_bringup/config/systemd/50-jackal-lan.conf /etc/systemd/network/10-netplan-br0.network.d/50-jackal-lan.conf
```

설치 확인:

```bash
grep Address /etc/systemd/network/10-netplan-br0.network.d/50-jackal-lan.conf
```

기대 출력:

```text
Address=192.168.50.2/24
Address=192.168.1.5/24
```

다음 재부팅 후 확인한다.

```bash
ip -br address show br0
ping -c 3 192.168.1.130
```

## 2. SSH setup

SSH는 Laptop에서 NUC의 상태를 확인하고 sensor launch를 실행하기 위해 사용한다.
Clearpath platform 서비스는 SSH와 무관하게 NUC 부팅 시 자동 실행된다.

### 2.1 NUC에서 SSH server 준비

NUC 로컬 terminal에서 한 번 실행한다.

```bash
sudo apt update
sudo apt install openssh-server
sudo systemctl enable --now ssh
```

확인:

```bash
systemctl is-enabled ssh
systemctl is-active ssh
ss -lnt | grep ':22'
```

### 2.2 Laptop에서 전용 SSH key 생성

이미 `~/.ssh/id_ed25519_jackal_nuc`가 있다면 다시 생성하지 않는다.

```bash
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_jackal_nuc -C jackal-nuc
ssh-copy-id -i ~/.ssh/id_ed25519_jackal_nuc.pub administrator@192.168.50.2
```

### 2.3 `ssh jackal` 등록

Laptop의 `~/.ssh/config`에 다음을 추가한다.

```sshconfig
Host jackal
    HostName 192.168.50.2
    User administrator
    IdentityFile ~/.ssh/id_ed25519_jackal_nuc
    IdentitiesOnly yes
    ServerAliveInterval 15
    ServerAliveCountMax 3
```

권한과 접속을 확인한다.

```bash
chmod 600 ~/.ssh/config
ssh jackal
```

Jackal 전원을 켠 직후에는 NUC와 Clearpath platform 준비에 시간이 걸릴 수 있다.
접속이 바로 되지 않으면 Laptop에서 다음 순서로 확인한다.

```bash
ip -br address show eno1
ping -c 3 192.168.50.2
ssh jackal
```

## 3. Package usage

### 3.1 Laptop과 NUC에 `jackal` ROS 환경 alias 등록

`ROS_DOMAIN_ID=1`만 설정해서는 충분하지 않다. 이 패키지는 multicast를 끈
Fast DDS static peer 구성을 사용하므로 다음 설정이 모두 필요하다.

- `ROS_DOMAIN_ID=1`
- `ROS_LOCALHOST_ONLY=0`
- `RMW_IMPLEMENTATION=rmw_fastrtps_cpp`
- 역할별 Fast DDS XML profile

`network_env.sh laptop`과 `network_env.sh nuc`가 위 값을 설정하고 각 장비에
기대 IP가 있는지도 검사한다.

Laptop의 `~/.bashrc` 끝에 다음 alias를 한 번 추가한다. 자동으로 환경을
바꾸지 않고, 사용자가 `jackal`을 실행한 현재 shell만 Jackal ROS 환경으로
전환한다.

```bash
alias jackal='source /opt/ros/humble/setup.bash && source "$HOME/moai_navigation_ws/install/setup.bash" && source "$HOME/moai_navigation_ws/install/jackal_network_bringup/share/jackal_network_bringup/config/network_env.sh" laptop && ros2 daemon stop >/dev/null 2>&1'
```

NUC의 `~/.bashrc`에는 역할과 vendor workspace가 다른 다음 alias를 한 번
추가한다.

```bash
alias jackal='source /opt/ros/humble/setup.bash && source /etc/clearpath/setup.bash && source "$HOME/ws_livox/install/local_setup.bash" && source "$HOME/moai_navigation_ws/install/setup.bash" && source "$HOME/moai_navigation_ws/install/jackal_network_bringup/share/jackal_network_bringup/config/network_env.sh" nuc && ros2 daemon stop >/dev/null 2>&1'
```

각 장비에서 저장한 뒤 새 terminal을 열거나, 현재 terminal에 alias 정의만 한 번
다시 읽힌다.

```bash
source ~/.bashrc
type jackal
```

이후에는 `jackal-lan`이 연결된 상태에서 새 Laptop terminal을 열고 먼저
`jackal`을 실행한다.

```bash
jackal
ros2 topic list -t
```

`jackal` 실행 시 다음 설정 완료 메시지가 출력돼야 한다.

```text
Configured Jackal ROS network: role=laptop ip=192.168.50.1 domain=1 rmw=rmw_fastrtps_cpp
```

`jackal` alias가 실행되는 것은 `ssh jackal`과 충돌하지 않는다. Bash alias는
명령 위치의 첫 단어에만 적용되므로 `ssh jackal`은 계속 NUC SSH 접속 명령이다.

ROS 환경 변수는 launch를 실행한 process와 그 자식 process에만 전달된다. 따라서
NUC에서도 sensor launch terminal과 별도로 연 terminal마다 먼저 `jackal`을
실행해야 센서 토픽을 볼 수 있다.

이 Laptop terminal 자체는 NUC에 SSH로 접속할 필요가 없다. 다만 현재 sensor
launch는 NUC SSH terminal의 foreground에서 실행하므로 그 SSH terminal은 열어
둬야 한다. 별도의 Laptop 기본 terminal에서 ROS 2가 NUC와 직접 통신한다.

현재 shell 설정 확인:

```bash
echo "$ROS_DOMAIN_ID"
echo "$RMW_IMPLEMENTATION"
echo "$FASTDDS_DEFAULT_PROFILES_FILE"
```

기대값은 domain `1`, `rmw_fastrtps_cpp`, Laptop Fast DDS XML 경로다.

### 3.2 Jackal 전원 ON 후 NUC sensor launch

Laptop에서 NUC 연결을 확인하고 SSH로 접속한다.

```bash
ping -c 3 192.168.50.2
ssh jackal
```

NUC SSH terminal에서 platform과 센서를 확인한다.

```bash
systemctl is-active clearpath-platform.service
ip -br address show br0
ping -c 3 192.168.1.130
```

기대 상태:

- `clearpath-platform.service`: `active`
- `br0`: `192.168.50.2/24`, `192.168.1.5/24`
- MID360 `192.168.1.130`: ping 손실 0%

같은 NUC SSH terminal에서 `jackal` alias로 환경을 불러오고 sensor launch를
실행한다.

```bash
jackal

ros2 launch jackal_network_bringup robot.launch.py \
  launch_platform:=false \
  launch_d455:=true \
  launch_mid360:=true \
  launch_mid360_scan:=false \
  launch_nav2:=false \
  forward_cmd_vel:=false
```

`clearpath-platform.service`가 이미 MCU를 담당하므로
`launch_platform:=false`를 유지한다. `forward_cmd_vel:=false`에서는 이
패키지가 받은 Nav2 속도 명령을 실제 Jackal base topic으로 전달하지 않는다.

정상 로그에는 다음 내용이 포함된다.

```text
RealSense Node Is Up!
successfully change work mode
livox/imu publish use imu format
livox/lidar publish use PointCloud2 format
```

### 3.3 Laptop에서 SSH 없이 토픽 조회

NUC sensor launch를 실행한 상태에서 Laptop의 새 기본 terminal을 연다.
SSH 접속 없이 `jackal` alias로 ROS 환경을 활성화한 뒤 조회한다.

```bash
jackal
ros2 topic list -t
```

주요 토픽:

| 구분 | 토픽 | 타입 |
|---|---|---|
| Jackal odometry | `/j100_0519/platform/odom` | `nav_msgs/msg/Odometry` |
| Jackal IMU | `/j100_0519/sensors/imu_0/data` | `sensor_msgs/msg/Imu` |
| D455 color | `/camera/camera/color/image_raw` | `sensor_msgs/msg/Image` |
| D455 color info | `/camera/camera/color/camera_info` | `sensor_msgs/msg/CameraInfo` |
| D455 depth | `/camera/camera/depth/image_rect_raw` | `sensor_msgs/msg/Image` |
| D455 depth info | `/camera/camera/depth/camera_info` | `sensor_msgs/msg/CameraInfo` |
| MID360 points | `/livox/lidar` | `sensor_msgs/msg/PointCloud2` |
| MID360 IMU | `/livox/imu` | `sensor_msgs/msg/Imu` |

실제 메시지 한 건을 확인한다.

```bash
ros2 topic echo --once --field header \
  /j100_0519/platform/odom nav_msgs/msg/Odometry

ros2 topic echo --once --field header \
  /camera/camera/color/image_raw sensor_msgs/msg/Image

ros2 topic echo --once --field header \
  /livox/lidar sensor_msgs/msg/PointCloud2
```

패키지에 포함된 자동 검사를 실행한다.

```bash
ros2 run jackal_network_bringup check_network.sh verify-peer nuc
ros2 run jackal_network_bringup check_network.sh verify-d455
ros2 run jackal_network_bringup check_network.sh verify-mid360
```

`verify-d455`는 Color/Depth/CameraInfo publisher와 30초 수신률을 확인한다.
`verify-mid360`은 PointCloud2/IMU publisher와 10초 PointCloud 수신률을
확인한다.

### 3.4 현재 검증 결과

2026-09-03 실제 NUC와 Laptop에서 다음을 확인했다.

- Laptop에서 Jackal odometry와 IMU 메시지 수신
- D455 Color: 14.92 Hz
- D455 Depth: 14.95 Hz
- MID360 PointCloud2: 15.01 Hz, 10초 동안 152개
- MID360 IMU: 10초 동안 2,019개
- MID360 frame: `livox_frame`
- Laptop과 NUC에서 package test 33개, 실패 0개
- `forward_cmd_vel=false` monitor-only mode

### 3.5 종료

NUC sensor launch terminal에서 `Ctrl-C`를 누른다. 이는 D455, MID360,
network probe, safety bridge만 종료한다. 부팅 서비스인
`clearpath-platform.service`는 계속 실행되므로 Jackal joystick 동작에는 영향을
주지 않는다.

### 3.6 문제 해결

Laptop에서 토픽이 보이지 않을 때:

```bash
ip -br address show eno1
ping -c 3 192.168.50.2
type jackal
jackal
echo "$ROS_DOMAIN_ID $RMW_IMPLEMENTATION"
echo "$FASTDDS_DEFAULT_PROFILES_FILE"
ros2 daemon stop
ros2 topic list -t
```

`type jackal`이 alias를 찾지 못하면 `~/.bashrc` 저장 또는 새 terminal 실행이
누락된 것으로 추론할 수 있다. `jackal`이 IP 오류를 출력하면 `eno1`의
`192.168.50.1/24` 설정부터 확인한다.

D455 토픽이 없을 때 NUC에서 확인한다.

```bash
lsusb | grep '8086:0b5c'
ls -l /dev/video*
```

MID360 토픽이 없을 때 NUC에서 확인한다.

```bash
jackal
ip -br address show br0
ping -c 3 192.168.1.130
ros2 pkg prefix livox_ros_driver2
ros2 topic list -t --no-daemon | grep '^/livox'
```

NUC의 다른 terminal에서 Jackal 토픽만 보이고 D455/MID360 토픽이 보이지 않으면
그 terminal의 Fast DDS profile이 적용되지 않은 것으로 추론할 수 있다. `jackal`
실행 후 `FASTDDS_DEFAULT_PROFILES_FILE`이 `fastdds_nuc.xml`인지 확인한다.

`/scan`은 현재 발행하지 않는다. NUC에 `pointcloud_to_laserscan`을 설치한 뒤
`launch_mid360_scan:=true`로 실행해야 한다. 현재 검증된 입력은 raw
`/livox/lidar` PointCloud2다.

`ros2 topic list`는 Clearpath 전용 토픽 이름과 타입을 표시할 수 있지만,
`clearpath_platform_msgs`가 Laptop에 없으면 해당 전용 메시지를
`ros2 topic echo`로 디코딩할 수 없다. 표준 타입인 odometry, IMU, Image,
PointCloud2는 현재 환경에서 조회할 수 있다.

속도 명령을 시험할 목적이 아니라면 `send-zero-cmd` 또는
`/j100_0519/cmd_vel` publish 명령을 실행하지 않는다.
