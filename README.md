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
- 자율주행 알고리즘, 지도, 경로 계획과 속도 명령 전달은 이 패키지의 범위에
  포함하지 않는다.

## 1. Prerequisites

지속 시각 동기화 설정은 [LAN 시간 동기화 절차](docs/time_sync.md)를 따른다.
Laptop chrony → NUC systemd-timesyncd 구성으로, ROS launch에서 설치·시각 변경을
자동 수행하지 않는다. 최초 적용에는 사용자의 직접 sudo 실행이 필요하다.

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
- 현재 Livox driver install prefix:
  `/home/administrator/ws_livox/install/livox_ros_driver2`
- 현재 Livox SDK library 경로:
  `/home/administrator/ws_livox/install/livox_sdk2/lib`
- `openssh-server`

Laptop:

- `rviz2` — 시각화할 때 사용
- `clearpath_platform_msgs` — Clearpath 전용 메시지를 직접
  `ros2 topic echo`할 때만 필요

설치 여부는 다음처럼 확인한다.

NUC:

```bash
source /opt/ros/humble/setup.bash
source /etc/clearpath/setup.bash
export COLCON_CURRENT_PREFIX=~/ws_livox/install/livox_ros_driver2
source ~/ws_livox/install/livox_ros_driver2/share/livox_ros_driver2/package.bash
unset COLCON_CURRENT_PREFIX
export LD_LIBRARY_PATH=~/ws_livox/install/livox_sdk2/lib${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}

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

이전 버전을 같은 workspace에 설치한 장비에서는 삭제된 파일이 incremental install
공간에 남을 수 있다. 이번 구조 변경을 처음 반영할 때에만 아래 두 package 전용
directory를 지운 뒤 다시 build한다. 다른 package의 build/install은 지우지 않는다.

```bash
cd ~/moai_navigation_ws
rm -rf build/jackal_network_bringup install/jackal_network_bringup
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

### 1.6 Clearpath platform과 센서의 DDS profile 통일

Clearpath platform과 sensor launch는 모두 domain 1과 Fast DDS를 사용하지만,
platform 부팅 서비스에도 같은 `fastdds_nuc.xml`을 지정해야 하나의 ROS graph로
검색된다. NUC에서 systemd override를 한 번 설치한다.

```bash
sudo install -D -m 0644 ~/moai_navigation_ws/src/jackal_network_bringup/config/systemd/clearpath-platform.service.d/50-jackal-fastdds.conf /etc/systemd/system/clearpath-platform.service.d/50-jackal-fastdds.conf
sudo systemctl daemon-reload
```

서비스 재시작은 MCU와 joystick 연결을 잠시 끊는다. 로봇을 고정하고 물리 e-stop을
건 상태에서만 실행한다.

```bash
sudo systemctl restart clearpath-platform.service
systemctl is-active clearpath-platform.service
systemctl show clearpath-platform.service -p Environment --no-pager
```

`Environment` 출력에는 domain 1, `rmw_fastrtps_cpp`, 두 Fast DDS profile 변수가
모두 `fastdds_nuc.xml` 경로로 표시돼야 한다.

### 1.7 NUC sensor 부팅 서비스 설치

NUC에서 패키지를 build해 sensor service가 실행할 시작 스크립트를 install한다.

```bash
cd ~/moai_navigation_ws
colcon build --symlink-install --packages-select jackal_network_bringup
```

수동으로 실행 중인 `robot.launch.py`가 있다면 먼저 해당 terminal에서 `Ctrl-C`로
종료한다. 같은 센서 driver를 수동 launch와 systemd service에서 동시에 실행하면
안 된다. 이후 service unit을 설치하고 즉시 시작한다.

```bash
sudo install -D -m 0644 \
  ~/moai_navigation_ws/src/jackal_network_bringup/config/systemd/jackal-sensors.service \
  /etc/systemd/system/jackal-sensors.service
sudo systemctl daemon-reload
sudo systemctl enable --now jackal-sensors.service
```

상태와 부팅 등록을 확인한다.

```bash
systemctl is-enabled jackal-sensors.service
systemctl is-active jackal-sensors.service
systemctl status jackal-sensors.service --no-pager
journalctl -u jackal-sensors.service -n 100 --no-pager
```

기대값은 `enabled`, `active`다. 이 service는 network-online 및
`clearpath-platform.service` 뒤에 시작하며, NUC 주소가 아직 준비되지 않았다면
5초 뒤 다시 시도한다. 실제 platform은 기존 Clearpath service가 담당하므로 sensor
service는 `launch_platform:=false`를 유지한다. 시작 스크립트는 별도 Livox
workspace의 driver package hook과 SDK shared-library 경로를 명시적으로 설정한다.
MID360 driver가 예기치 않게 종료되면 launch가 5초 뒤 다시 실행한다.

## 2. SSH setup

SSH는 최초 service 설치와 NUC 상태 점검·유지보수에만 사용한다. service 설치 후의
일상적인 sensor 실행에는 SSH 접속이 필요하지 않다.
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

NUC의 `~/.bashrc`에는 역할과 vendor workspace가 다른 다음 shell function을 한 번
추가한다. 전체 Livox workspace의 `local_setup.bash` 대신 실제 driver package hook을
읽어, 이전 build 경로가 남아 있는 workspace에서도 필요한 package만 활성화한다.

```bash
jackal() {
  source /opt/ros/humble/setup.bash &&
    source /etc/clearpath/setup.bash &&
    export COLCON_CURRENT_PREFIX="$HOME/ws_livox/install/livox_ros_driver2" &&
    source "$COLCON_CURRENT_PREFIX/share/livox_ros_driver2/package.bash" &&
    unset COLCON_CURRENT_PREFIX &&
    export LD_LIBRARY_PATH="$HOME/ws_livox/install/livox_sdk2/lib${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}" &&
    source "$HOME/moai_navigation_ws/install/setup.bash" &&
    source "$HOME/moai_navigation_ws/install/jackal_network_bringup/share/jackal_network_bringup/config/network_env.sh" nuc &&
    ros2 daemon stop >/dev/null 2>&1
}
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

NUC sensor service는 자체 systemd 환경에서 실행되므로 interactive shell의
`jackal` function에 의존하지 않는다. NUC에서 ROS CLI로 점검하는 terminal에서만
`jackal`을 먼저 실행한다. Laptop은 NUC에 SSH로 접속하지 않고 ROS 2 토픽을 직접
조회한다.

현재 shell 설정 확인:

```bash
echo "$ROS_DOMAIN_ID"
echo "$RMW_IMPLEMENTATION"
echo "$FASTDDS_DEFAULT_PROFILES_FILE"
```

기대값은 domain `1`, `rmw_fastrtps_cpp`, Laptop Fast DDS XML 경로다.

### 3.2 Jackal 전원 ON 후 자동 sensor launch

1.7의 `jackal-sensors.service`를 한 번 설치한 뒤에는 Jackal 전원과 함께 NUC가
부팅되면 D455와 MID360이 자동으로 시작한다. Laptop에서 별도 SSH 접속이나 NUC의
수동 `ros2 launch` 없이 연결과 토픽을 확인한다.

```bash
ping -c 3 192.168.50.2
jackal
ros2 topic list -t
```

정상 service 로그에는 다음 내용이 포함된다.

```text
RealSense Node Is Up!
successfully change work mode
livox/imu publish use imu format
livox/lidar publish use PointCloud2 format
```

토픽이 보이지 않을 때만 NUC 상태 확인을 위해 SSH를 사용한다.

```bash
ssh jackal
systemctl is-active clearpath-platform.service
systemctl is-active jackal-sensors.service
ip -br address show br0
ping -c 3 192.168.1.130
journalctl -u jackal-sensors.service -n 100 --no-pager
```

기대 상태는 두 service 모두 `active`, `br0`에 `192.168.50.2/24`와
`192.168.1.5/24`, MID360 ping 손실 0%다.

### 3.3 Laptop에서 SSH 없이 토픽 조회

NUC sensor service가 active인 상태에서 Laptop의 새 기본 terminal을 연다.
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

- Clearpath platform systemd service와 sensor launch에 동일한 NUC Fast DDS
  profile 적용
- Laptop의 한 ROS graph에서 Jackal odometry, D455, MID360 토픽 동시 검색 및
  실제 메시지 수신
- Jackal odometry frame: `odom`
- D455 Color: 14.99 Hz, 30초 동안 451개
- D455 Depth: 14.99 Hz, 30초 동안 451개
- D455 Color frame: `camera_color_optical_frame`
- MID360 PointCloud2: 14.50 Hz, 10초 동안 146개
- MID360 IMU: 10초 동안 1,942개
- MID360 frame: `livox_frame`
- 새 임시 build/install 공간에서 package test 33개, 실패 0개

### 3.5 sensor service 정지와 재시작

유지보수 중 sensor만 정지하거나 재시작할 때 NUC에서 다음을 실행한다.

```bash
sudo systemctl stop jackal-sensors.service
sudo systemctl restart jackal-sensors.service
```

`stop`은 D455, MID360과 network probe만 종료한다. 별도 부팅
서비스인 `clearpath-platform.service`는 계속 실행되므로 Jackal joystick 동작에는
영향을 주지 않는다. 다음 부팅에도 sensor 자동 시작을 막으려면 명시적으로
비활성화한다.

```bash
sudo systemctl disable --now jackal-sensors.service
```

현재 사용 중인 Livox Driver 2 v1.2.4에서는 `Ctrl-C` 종료 시
`Livox Lidar SDK Deinit completely!` 로그 뒤 프로세스가 `exit code -11`을
보고하는 현상이 한 번 관찰됐다. 실행 중 PointCloud2/IMU 수신은 정상 검증됐으므로
종료 경로 문제로 추론하며, driver 업데이트 또는 shutdown 경로 점검이 후속
작업이다.

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
systemctl status jackal-sensors.service --no-pager
journalctl -u jackal-sensors.service -n 100 --no-pager
pgrep -af 'robot.launch.py|realsense2_camera|livox_ros_driver2'
lsusb | grep '8086:0b5c'
ls -l /dev/video*
```

`pgrep` 출력에 sensor process가 하나도 없으면 sensor launch가 실행 중인 상태가
아니다. journal에서 누락된 setup file, NUC IP 또는 driver 오류를 확인한 뒤 service를
재시작한다.

```bash
sudo systemctl restart jackal-sensors.service
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

`ros2 topic list`는 Clearpath 전용 토픽 이름과 타입을 표시할 수 있지만,
`clearpath_platform_msgs`가 Laptop에 없으면 해당 전용 메시지를
`ros2 topic echo`로 디코딩할 수 없다. 표준 타입인 odometry, IMU, Image,
PointCloud2는 현재 환경에서 조회할 수 있다.

## Temporary IP reassembly settings (2026-09-21)

This package owns both `ipfrag_high_thresh` (minimum 16777216 bytes) and
`ipfrag_time` (3 seconds). Larger existing memory limits are preserved. These
are a trial policy; historical Nav2 measurements at 128MiB do not validate it.

```bash
ros2 run jackal_network_bringup ipfrag_session.py status --check
sudo python3 "$(ros2 pkg prefix jackal_network_bringup)/lib/jackal_network_bringup/ipfrag_session.py" apply
# After the ROS stacks have stopped:
sudo python3 "$(ros2 pkg prefix jackal_network_bringup)/lib/jackal_network_bringup/ipfrag_session.py" restore
```

`status --check` exits 0 ready, 1 not ready, 2 error and never changes settings.
Root-owned recovery state is under `/run/jackal-network-ipfrag`. The directory
is readable but only writable by root. Unreadable legacy state is an error (2),
not evidence of readiness; restore that state with sudo before a new apply.
Only changed values are owned and restored. External edits, missing originals,
boot/network-namespace mismatches and failed writes retain recovery information.
No permanent sysctl configuration or terminal-exit restoration is installed.

If `/run/jackal-nav2-ipfrag/state.json` exists, stop the ROS stacks and use
`restore --legacy-nav2` with the network tool before a new apply. It restores
only values actually present in that legacy record. Never guess an original.
Tests for the helper belong to this package; Nav2 consumes the status CLI.
Rebuild both packages after migration. Remove only the verified dangling old
Nav2 ipfrag helper link; do not copy the laptop network package over the NUC.
