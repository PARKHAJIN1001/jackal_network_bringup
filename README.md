# Jackal Network Bringup (`jackal_network_bringup`)

NUC(온보드 컴퓨터)와 Laptop 간의 전용 유선 기가비트 이더넷망을 통해 Jackal 로봇 플랫폼, Intel RealSense D455 카메라, Livox MID-360 LiDAR의 ROS 2 Humble 센서 데이터를 초저지연·무손실로 수신하기 위한 통신 및 드라이버 브링업 패키지입니다.

---

## 1. 패키지 목적 및 아키텍처 (Purpose & Architecture)

### 1.1 시스템 구조도
```text
[ Jackal 로봇 하드웨어 (NUC) ]
  ├── Jackal MCU ──(USB)─────> Clearpath Platform Service (`clearpath-platform.service`)
  ├── RealSense D455 ─(USB3)──> realsense2_camera (RGB Color 스트림, 대역폭 최적화)
  └── Livox MID-360 ─(Eth)───> livox_ros_driver2 (Pointcloud2 @ 15Hz, IMU @ 200Hz)
            │
      [ NUC br0 Bridge ] (192.168.50.2 / 192.168.1.5)
            │
            │  전용 유선 LAN (1 Gbps Ethernet Cat6)
            │  Fast-DDS Unicast Static Peer (Multicast 차단)
            │  Kernel IP Reassembly (64 MiB ipfrag buffer)
            ▼
[ Laptop 개발/운용 PC (Laptop) ] (192.168.50.1)
  ├── ROS 2 CLI & Diagnostic Tool (`check_network.sh`)
  ├── Time Sync Client (Chrony Master ↔ timesyncd Slave)
  └── High-level Stack (FAST-LIVO2, Nav2, Perception 등)
```

### 1.2 주요 역할 및 설계 원칙
1. **역할 분담의 명확성**:
   - **NUC (192.168.50.2)**: Clearpath 플랫폼 제어, 센서 하드웨어 드라이버 구동(`jackal-sensors.service` 또는 `robot.launch.py`).
   - **Laptop (192.168.50.1)**: 센서 데이터 수신, 모니터링, 고수준 SLAM 및 Navigation 연산 수행.
2. **Fast-DDS 유니캐스트 피어링 (Static Discovery)**:
   - Wi-Fi 또는 외부 네트워크와의 멀티캐스트 충돌 및 패킷 플러딩을 방지하기 위해 `ROS_LOCALHOST_ONLY=0`과 함께 전용 XML 프로파일을 적용하여 NUC와 Laptop 간 1:1 유니캐스트 통신만 허용합니다.
3. **네트워크 대역폭 최적화**:
   - 15fps RGB Color 이미지만 전송하고 불필요한 Depth 스트림을 비활성화하여 대역폭 사용량을 기존 ~187 Mbps에서 ~30 Mbps 수준으로 안정화.
   - MID-360 포인트클라우드(프레임당 약 430 KB)의 UDP IP 단편화(IP Fragmentation) 유실을 방지하기 위해 커널 재조립 버퍼 최적화.

---

## 2. 패키지 의존성 (Dependencies)

### 2.1 공통 요구사항
- **OS**: Ubuntu 22.04 LTS (Jammy Jellyfish)
- **ROS 2**: Humble Hawksbill
- **RMW 구현체**: `rmw_fastrtps_cpp`
- **빌드 도구**: `colcon`, `ament_cmake`, `python3-colcon-common-extensions`

### 2.2 NUC (온보드 컴퓨터) 의존성
- **Clearpath Platform Stack**:
  - `/etc/clearpath/setup.bash`
  - `clearpath_platform_msgs`
- **센서 드라이버**:
  - `realsense2_camera` (Intel RealSense ROS 2 패키지)
  - `livox_ros_driver2` (Livox SDK2 기반 ROS 2 드라이버, `~/ws_livox`)
  - `Livox-SDK2` (공유 라이브러리 `~/ws_livox/install/livox_sdk2/lib`)
- **시스템 패키지**: `openssh-server`, `systemd-timesyncd`

### 2.3 Laptop (운용 PC) 의존성
- **ROS 패키지**: `rviz2`, `rqt`, `clearpath_platform_msgs` (토픽 직접 디코딩 시)
- **시간 동기화 서버**: `chrony`

---

## 3. Git Clone 후 통신 프로토콜 초기 세팅 (Initial Configuration)

### 3.1 네트워크 인터페이스 및 IP 주소 설정

| 장치 | 물리/논리 인터페이스 | IP 주소 / 서브넷 | 비고 |
|---|---|---|---|
| **Laptop** | `eno1` (유선 LAN) | `192.168.50.1/24` | 고정 IP, 게이트웨이 없음 |
| **NUC** | `br0` (Bridge) | `192.168.50.2/24` | Laptop 통신용 고정 IP |
| **NUC** | `br0` (Bridge) | `192.168.1.5/24` | MID-360 LiDAR 통신용 IP |
| **MID-360** | 내부 Ethernet | `192.168.1.130` | LiDAR 기본 IP |

#### A. Laptop 유선 네트워크 연결 생성 (1회 실행)
```bash
sudo nmcli connection add type ethernet ifname eno1 con-name jackal-lan \
  ipv4.method manual ipv4.addresses 192.168.50.1/24 \
  ipv4.never-default yes ipv6.method disabled
sudo nmcli connection modify jackal-lan \
  ipv4.gateway "" ipv4.dns "" connection.autoconnect yes

# 연결 활성화 및 통신 확인
sudo nmcli connection up jackal-lan
ping -c 3 192.168.50.2
```

#### B. NUC 네트워크 영구 설정 (NUC에서 1회 실행)
NUC의 `br0` 브리지에 `192.168.50.2`와 `192.168.1.5`를 동시에 바인딩합니다.
```bash
sudo install -D -m 0644 \
  ~/moai_navigation_ws/src/jackal_network_bringup/config/systemd/50-jackal-lan.conf \
  /etc/systemd/network/10-netplan-br0.network.d/50-jackal-lan.conf
sudo systemctl restart systemd-networkd
```

---

### 3.2 커널 IP 재조립 및 네트워크 버퍼 최적화 (`60-jackal-network.conf`)

MID-360 포인트클라우드는 MTU(1500바이트)를 크게 초과하여 대규모 UDP IP 단편화가 발생합니다. 커널 기본 버퍼(기본 4 MiB)는 패킷 드롭을 유발하므로 Laptop 및 NUC 모두에 다음 설정을 적용합니다.

```bash
# 커널 영구 설정 적용 (Laptop 및 NUC)
sudo install -D -m 0644 \
  ~/moai_navigation_ws/src/jackal_network_bringup/config/60-jackal-network.conf \
  /etc/sysctl.d/60-jackal-network.conf
sudo sysctl --system
```

주요 파라미터 적용 값:
- `net.ipv4.ipfrag_high_thresh = 67108864` (64 MiB)
- `net.ipv4.ipfrag_low_thresh = 50331648` (48 MiB)
- `net.ipv4.ipfrag_time = 1`
- `net.core.rmem_max = 33554432` (32 MiB)
- `net.core.netdev_max_backlog = 10000`

임시 세션 관리 도구를 사용할 경우:
```bash
ros2 run jackal_network_bringup ipfrag_session.py status
sudo python3 "$(ros2 pkg prefix jackal_network_bringup)/lib/jackal_network_bringup/ipfrag_session.py" apply
```

---

### 3.3 Fast-DDS Static Peer Profile 및 비동기 모드

Laptop과 NUC 간의 정적 피어링을 위해 각 기기에 최적화된 XML 프로파일을 사용합니다:
- Laptop: `config/fastdds_laptop.xml` (Peer: `192.168.50.2`)
- NUC: `config/fastdds_nuc.xml` (Peer: `192.168.50.1`, `sendBufferSize`: 2 MiB)

Clearpath 기본 플랫폼 서비스(`clearpath-platform.service`)에도 Fast-DDS 설정을 동기화합니다:
```bash
# NUC에서 실행
sudo install -D -m 0644 \
  ~/moai_navigation_ws/src/jackal_network_bringup/config/systemd/clearpath-platform.service.d/50-jackal-fastdds.conf \
  /etc/systemd/system/clearpath-platform.service.d/50-jackal-fastdds.conf
sudo systemctl daemon-reload
sudo systemctl restart clearpath-platform.service
```

---

### 3.4 시간 동기화 (Chrony & timesyncd)
센서 타임스탬프와 TF 오차를 방지하기 위해 Laptop을 로컬 NTP 서버로, NUC를 클라이언트로 운영합니다. 상세 절차는 [docs/time_sync.md](docs/time_sync.md)를 참고하십시오.
- Laptop: `chrony` 서비스 활성화 (`allow 192.168.50.0/24`)
- NUC: `systemd-timesyncd` 서버를 `192.168.50.1`로 지정
```bash
# Laptop에서 확인
chronyc sources -v
# NUC에서 확인
ssh jackal 'timedatectl timesync-status'
```

---

### 3.5 Shell Alias (`jackal`) 등록

터미널을 열 때마다 환경변수를 수동으로 입력하지 않도록 `~/.bashrc`에 alias를 등록합니다.

#### Laptop (`~/.bashrc` 하단에 추가):
```bash
alias jackal='source /opt/ros/humble/setup.bash && source "$HOME/moai_navigation_ws/install/setup.bash" && source "$HOME/moai_navigation_ws/install/jackal_network_bringup/share/jackal_network_bringup/config/network_env.sh" laptop && ros2 daemon stop >/dev/null 2>&1'
```

#### NUC (`~/.bashrc` 하단에 추가):
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

적용 후:
```bash
source ~/.bashrc
jackal
```

---

## 4. 패키지 운용 및 진단 방법 (Operation & Verification)

### 4.1 NUC 센서 드라이버 운용

#### A. 부팅 시 자동 실행 (권장: systemd 서비스)
패키지에서 제공하는 `jackal-sensors.service`를 등록해 두면 NUC 부팅 시 D455와 MID-360이 자동으로 실행됩니다.
```bash
# 서비스 등록 및 시작 (NUC에서 1회)
sudo install -D -m 0644 \
  ~/moai_navigation_ws/src/jackal_network_bringup/config/systemd/jackal-sensors.service \
  /etc/systemd/system/jackal-sensors.service
sudo systemctl daemon-reload
sudo systemctl enable --now jackal-sensors.service

# 서비스 상태 확인
systemctl status jackal-sensors.service --no-pager
```

#### B. 수동 디버깅 실행 (서비스를 끈 상태에서 실행)
```bash
# 서비스 일시 정지
sudo systemctl stop jackal-sensors.service

# 포그라운드 수동 실행
jackal
ros2 launch jackal_network_bringup robot.launch.py launch_d455:=true launch_mid360:=true
```

---

### 4.2 Laptop에서 센서 스트림 확인

Laptop에서 새 터미널을 열고 `jackal` 환경을 로드한 뒤 토픽을 점검합니다.
```bash
jackal
ros2 topic list -t
```

#### 주요 토픽 및 정상 주기:
| 토픽명 | 메시지 타입 | 정상 발행 주기 | 설명 |
|---|---|---|---|
| `/j100_0519/platform/odom` | `nav_msgs/msg/Odometry` | 50.0 Hz | Jackal 휠 엔코더 오도메트리 |
| `/j100_0519/sensors/imu_0/data` | `sensor_msgs/msg/Imu` | 50.0 Hz | Jackal MCU 내장 IMU |
| `/camera/camera/color/image_raw` | `sensor_msgs/msg/Image` | 15.0 Hz | RealSense D455 RGB 영상 |
| `/camera/camera/color/camera_info`| `sensor_msgs/msg/CameraInfo` | 15.0 Hz | D455 카메라 내부 파라미터 |
| `/livox/lidar` | `sensor_msgs/msg/PointCloud2` | 15.0 Hz | MID-360 라이다 포인트클라우드 |
| `/livox/imu` | `sensor_msgs/msg/Imu` | 200.0 Hz | MID-360 내장 고정밀 IMU |

토픽 발행 주기 확인:
```bash
ros2 topic hz /livox/lidar
ros2 topic hz /camera/camera/color/image_raw
ros2 topic hz /j100_0519/platform/odom
```

---

### 4.3 통합 네트워크 진단 도구 (`check_network.sh`)

패키지에 내장된 스크립트로 통신 상태 및 토픽 수신율을 일괄 검증합니다.
```bash
jackal
# 피어 연결성 검증
ros2 run jackal_network_bringup check_network.sh verify-peer nuc

# D455 카메라 스트림 30초 검증
ros2 run jackal_network_bringup check_network.sh verify-d455

# MID-360 LiDAR 스트림 10초 검증
ros2 run jackal_network_bringup check_network.sh verify-mid360
```

---

## 5. 빌드 및 테스트 (Build & Test)

```bash
cd ~/moai_navigation_ws
colcon build --symlink-install --packages-select jackal_network_bringup
colcon test --packages-select jackal_network_bringup
colcon test-result --verbose
```
모든 단위 테스트 및 통합 테스트가 100% 통과(Pass)해야 합니다.
