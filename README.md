# Jackal distributed ROS 2 bringup

J100의 NUC, Laptop, 향후 Radxa X4를 전용 유선망에서 Fast DDS로 연결하는
ROS 2 Humble 패키지다. 현재 기본 동작은 NUC의 D455와 heartbeat를 실행하고,
Laptop에서 heartbeat와 RViz를 실행한다. 실제 플랫폼과 속도 전달은 모두 기본적으로
꺼져 있다.

## 안전 경계

- `robot.launch.py`의 `launch_platform` 기본값은 `false`다.
- Nav2 출력은 `/j100_0519/nav2_cmd_vel_unstamped`에서
  `TwistStamped`인 `/j100_0519/nav2_cmd_vel`로 변환된다.
- `cmd_vel_safety_bridge.py`의 `forward_cmd_vel` 기본값은 `false`다. 이때
  `/j100_0519/cmd_vel` publisher 자체를 만들지 않는다.
- `check_network.sh send-zero-cmd`는 인자를 받지 않으며, 고정된 0 명령만 한 번
  Clearpath Humble API 타입인 `geometry_msgs/msg/Twist`로
  `/j100_0519/cmd_vel`에 보낸다. platform을 실행하지 않은 Phase A에서만 쓴다.
- 이 저장소의 구현과 무하드웨어 테스트는 물리 주행 승인이 아니다.

## 역할과 주소

| 역할 | Phase A/B 주소 | 최종 책임 |
|---|---:|---|
| Laptop | `192.168.50.1/24` | RViz, CLI, goal, 기록 |
| NUC | `192.168.50.2/24` | D455, MID360, 처리, 최종 Nav2 |
| Radxa X4 | `192.168.50.3/24` | MCU, Clearpath platform, watchdog |

모든 장비는 `ROS_DOMAIN_ID=1`, `ROS_LOCALHOST_ONLY=0`,
`rmw_fastrtps_cpp`를 사용한다. Fast DDS discovery는 multicast 대신 `.50.1`,
`.50.2`, `.50.3` static initial peer를 사용하며, 각 장비의 UDP transport는 해당
장비의 `.50.x` 주소에만 bind한다. 같은 장비의 프로세스 간 통신을 위해 SHM은
유지한다.

## 설치와 빌드

ROS 2 Humble이 설치된 각 장비의 workspace `src`에 이 패키지를 checkout한다.

```bash
cd ~/moai_navigation_ws
rosdep install --from-paths src --ignore-src -r -y
colcon build --symlink-install --packages-select jackal_network_bringup
source install/setup.bash
```

NUC에는 `realsense2_camera`가, Laptop/Phase C NUC에는 Nav2가 필요하다. MID360을
쓸 NUC에서는 vendor workspace도 먼저 source해야 한다.

```bash
source /home/parkhajin/ws_livox/install/setup.bash
source ~/moai_navigation_ws/install/setup.bash
```

## 네트워크 구성

네트워크 변경은 launch에서 하지 않는다. 아래 작업은 연결이 끊길 수 있으므로
NUC 로컬 콘솔에서 수행하고, 먼저 현재 설정을 저장한다.

### Laptop: NetworkManager

현재 `eno1`의 `192.168.1.5/24` 프로필을 내리고, gateway와 DNS가 없는 별도
프로필을 만든다.

```bash
nmcli -f NAME,UUID,TYPE,DEVICE connection show
sudo nmcli connection add type ethernet ifname eno1 con-name jackal-lan \
  ipv4.method manual ipv4.addresses 192.168.50.1/24 \
  ipv4.never-default yes ipv6.method disabled
sudo nmcli connection modify jackal-lan ipv4.gateway "" ipv4.dns "" \
  connection.autoconnect no
sudo nmcli connection up jackal-lan
ip -br address show eno1
ip route
```

복구할 때는 `jackal-lan`을 내리고 앞에서 확인한 기존 프로필을 올린다.

```bash
sudo nmcli connection down jackal-lan
sudo nmcli connection up "<기존-eno1-프로필>"
```

### NUC: systemd-networkd

`enp86s0`는 `br0`의 slave이므로 주소는 반드시 `br0`에 추가한다. 먼저
`networkctl status br0`에서 실제로 매칭된 `.network` 파일명을 확인한다. 예를 들어
파일명이 `20-br0.network`라면 다음 drop-in을 만든다.

```ini
# /etc/systemd/network/20-br0.network.d/50-jackal-lan.conf
[Network]
Address=192.168.50.2/24
```

NUC 로컬 콘솔에서 적용하고 기존 주소와 route가 유지되는지 확인한다.

```bash
sudo networkctl reload
sudo networkctl reconfigure br0
ip -br address show br0
ip route
```

`192.168.131.1/24`, DHCP `10.10.22.98/22`, 기존 default route가 사라졌다면
drop-in을 제거하고 `systemd-networkd`를 재시작해 복구한다. Phase B에서 MID360을
연결할 때에는 같은 방식으로 `Address=192.168.1.5/24`를 추가한다.

### SSH

NUC 로컬 콘솔에서 먼저 서버를 설치한다.

```bash
sudo apt update
sudo apt install openssh-server
sudo systemctl enable --now ssh
```

Laptop 전용 키를 만든 뒤 공개키만 등록한다.

```bash
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_jackal_nuc \
  -C jackal-nuc
ssh-copy-id -i ~/.ssh/id_ed25519_jackal_nuc.pub \
  administrator@192.168.50.2
ssh -i ~/.ssh/id_ed25519_jackal_nuc administrator@192.168.50.2
```

현재 hub가 기관망에 연결돼 있으므로 방화벽을 활성화하기 전에 기존 SSH 세션과
규칙을 확인한다. 최소 허용 범위는 TCP 22를 `.50.1`에서만, UDP를 `.50.0/24`에서만
받는 것이다. 원격에서 검증하지 않은 채 `ufw enable`을 실행하지 않는다.

```bash
sudo ufw status numbered
sudo ufw allow in on br0 from 192.168.50.1 to any port 22 proto tcp
sudo ufw allow in on br0 from 192.168.50.0/24 proto udp
```

## 역할 환경 불러오기

자동 ament 환경 hook은 없다. ROS 및 workspace setup 다음에 역할을 명시한다.
기대 IP가 장비에 없으면 source가 실패한다.

```bash
PACKAGE_SHARE="$(ros2 pkg prefix --share jackal_network_bringup)"
source "$PACKAGE_SHARE/config/network_env.sh" laptop  # 또는 nuc, radxa
ros2 daemon stop
ros2 daemon start
ros2 run jackal_network_bringup check_network.sh preflight laptop
```

두 Fast DDS 프로필을 바꿔가며 쓴 shell에서는 반드시 ROS daemon도 다시 시작한다.

## Phase A: D455-only

NUC SSH terminal:

```bash
source /etc/clearpath/setup.bash
source ~/moai_navigation_ws/install/setup.bash
PACKAGE_SHARE="$(ros2 pkg prefix --share jackal_network_bringup)"
source "$PACKAGE_SHARE/config/network_env.sh" nuc
ros2 run jackal_network_bringup check_network.sh preflight nuc
ros2 launch jackal_network_bringup robot.launch.py
```

이 기본 launch는 `launch_platform:=false`, `launch_d455:=true`,
`launch_mid360:=false`, `launch_nav2:=false`, `forward_cmd_vel:=false`다.

Laptop terminal:

```bash
source ~/moai_navigation_ws/install/setup.bash
PACKAGE_SHARE="$(ros2 pkg prefix --share jackal_network_bringup)"
source "$PACKAGE_SHARE/config/network_env.sh" laptop
ros2 run jackal_network_bringup check_network.sh preflight laptop
ros2 launch jackal_network_bringup laptop.launch.py
```

별도 Laptop terminal에서 heartbeat와 D455를 검증한다. D455 검사는 Color/Depth
각 15 Hz 설정의 80%인 12 Hz 이상을 30초 동안 요구하고 CameraInfo도 확인한다.

```bash
ros2 run jackal_network_bringup check_network.sh verify-peer nuc
ros2 run jackal_network_bringup check_network.sh verify-d455
```

0 명령 수신 시험은 platform이 꺼진 상태에서만 진행한다.

```bash
# NUC
ros2 run jackal_network_bringup check_network.sh wait-zero-cmd

# Laptop, NUC가 기다리기 시작한 뒤 실행
ros2 run jackal_network_bringup check_network.sh send-zero-cmd
```

예상 센서 토픽은 다음과 같다.

- `/camera/camera/color/image_raw`
- `/camera/camera/color/camera_info`
- `/camera/camera/depth/image_rect_raw`
- `/camera/camera/depth/camera_info`

PointCloud는 Phase A에서 꺼져 있다.

## Phase B: MCU/MID360 연결 후 Laptop Nav2

1. NUC `br0`에 `192.168.1.5/24`를 추가하고 MID360 `192.168.1.130`을 ping한다.
2. `config/maps/j100_0519.yaml`과 그 YAML이 가리키는 이미지 파일을 추가한다.
3. MCU/platform에서 odometry와 TF를 받아야 하므로 Jackal을 고정하고 e-stop 상태를
   확인한 뒤 platform을 실행한다. 명령 도달 시험에서는
   `forward_cmd_vel:=false`를 유지한다.

NUC:

```bash
source /etc/clearpath/setup.bash
source /home/parkhajin/ws_livox/install/setup.bash
source ~/moai_navigation_ws/install/setup.bash
PACKAGE_SHARE="$(ros2 pkg prefix --share jackal_network_bringup)"
source "$PACKAGE_SHARE/config/network_env.sh" nuc
ros2 launch jackal_network_bringup robot.launch.py \
  launch_platform:=true launch_d455:=true launch_mid360:=true \
  forward_cmd_vel:=false
```

Laptop:

```bash
source ~/moai_navigation_ws/install/setup.bash
PACKAGE_SHARE="$(ros2 pkg prefix --share jackal_network_bringup)"
source "$PACKAGE_SHARE/config/network_env.sh" laptop
ros2 launch jackal_network_bringup laptop.launch.py launch_nav2:=true \
  nav2_map:="$PACKAGE_SHARE/config/maps/j100_0519.yaml"
```

확인 항목:

```bash
ros2 topic echo --once /livox/lidar
ros2 topic echo --once /livox/imu
ros2 topic echo --once /scan
ros2 topic info -v /j100_0519/nav2_cmd_vel
ros2 topic info -v /j100_0519/cmd_vel
ros2 lifecycle get /j100_0519/amcl
ros2 lifecycle get /j100_0519/controller_server
ros2 run tf2_ros tf2_echo map base_link
```

`/j100_0519/nav2_cmd_vel`은 Laptop publisher와 NUC safety bridge subscriber가
보여야 한다. `forward_cmd_vel=false`이면 safety bridge는
`/j100_0519/cmd_vel` publisher로 나타나면 안 된다.

`config/nav2/j100_0519.yaml`의 odometry 입력은 현재
`/j100_0519/platform/odom`으로 설정했다. 이는 Clearpath 토픽 관례에 따른 추론이며,
MCU 연결 후 `ros2 topic list -t`와 TF를 보고 실제 토픽과 frame ID로 확정해야 한다.
MID360의 `livox_frame -> base_link` extrinsic 역시 실측값이 없으므로 commissioning
전에는 navigation 품질을 신뢰하면 안 된다. 기본 `base_link -> livox_frame`은 이
개발 장비의 기존 localization 설정에서 가져온 `z=0.9 m`, pitch `30°` 값이다.
실제 장착과 다르면 `mid360_base_*` launch 인자로 수정하거나, URDF가 같은 TF를
제공할 때 `publish_mid360_static_tf:=false`로 중복 publisher를 끈다.

## Phase C: Radxa 최종 구조

최종 구성과 이전 순서는 [설계 문서](docs/design.md)에 정리했다. 핵심은 Radxa가
`cpr-j100-0519` hostname과 MCU/platform/watchdog을 맡고, `jackal-sensors`로
이름을 바꾼 NUC가 센서 처리와 Nav2를 맡는 것이다. NUC를 chrony server,
Radxa/Laptop을 client로 구성한다. 실제 forwarding은 별도 commissioning에서만
활성화하고, 입력 0.5초 단절 시 0 출력 및 링크 단절 1초 이내 정지를 시험한다.

## DDS 및 문제 해결

발견이 안 되면 양쪽에서 다음 순서로 확인한다.

```bash
ip -br address
ping -c 3 192.168.50.2        # Laptop에서
echo "$ROS_DOMAIN_ID $RMW_IMPLEMENTATION"
echo "$FASTDDS_DEFAULT_PROFILES_FILE"
ros2 daemon stop
ros2 run jackal_network_bringup check_network.sh preflight laptop
```

`.50.x` 외 인터페이스로 DDS UDP가 나가는지 검사한다. domain 1과 많은 initial peer
port 범위를 포함하도록 넓게 잡는다.

```bash
sudo tcpdump -ni any 'udp portrange 7400-8000'
ss -uapn
```

기관망 `10.10.x`, Wi-Fi, Docker 인터페이스에 DDS packet이 보이면 해당 역할 XML의
allowlist와 실제 IP가 일치하는지 확인한다. D455 rate가 낮으면 USB 3 연결,
RealSense log, CPU 부하를 먼저 확인한다.

## 검증 상태

2026-08-28 개발 Laptop의 격리된 loopback Fast DDS profile에서 다음을 실제로
검증했다. 이는 두 물리 장비 간 Ethernet 시험을 대신하지 않는다.

- 임시 build/install 디렉터리에서 `colcon build` 성공
- pytest, flake8, pep257, CMake lint, XML lint: 31개 결과, 실패 0개
- hardware 옵션을 끈 robot/laptop launch 기동 및 SIGINT 정상 종료
- `nuc -> laptop`, `laptop -> nuc` heartbeat 각각 11개/10.00초 연속 수신
- 고정 0 `Twist` 1건 송신 및 수신 성공, 값 인자 전달 거부
- 비영 `/j100_0519/nav2_cmd_vel`을 bridge가 관찰한 뒤에도
  `/j100_0519/cmd_vel` publisher가 생성되지 않음
- 별도 `/test` 토픽에서 0.5초 watchdog: 총 30개 출력 중 비영 15개,
  timeout 이후 0 출력 15개 확인

다음 항목은 실제 두 장비와 센서가 필요한 현장 검증이며 아직 결과를 단정하지 않는다.

- NUC/Laptop `.50.x` 네트워크와 SSH
- 양방향 heartbeat 10초 연속 수신
- D455 실제 topic/frame/rate와 RViz 표시
- packet capture에서 다른 인터페이스의 ROS UDP 부재
- MID360 `/scan`, 실제 odometry topic, `map -> odom -> base_link`
- Nav2 lifecycle active와 NUC까지의 command 도달

## 참고 자료

- [Clearpath ROS 2 Humble middleware](https://docs.clearpathrobotics.com/docs/ros2humble/ros/)
- [Fast DDS 2.6 multicast 비활성화](https://fast-dds.docs.eprosima.com/en/2.6.x/fastdds/transport/disabling_multicast.html)
- [Clearpath Humble Platform API](https://docs.clearpathrobotics.com/docs/ros2humble/ros/api/platform_api/)
- [RealSense ROS launch](https://github.com/realsenseai/realsense-ros/blob/ros2-master/README.md)
