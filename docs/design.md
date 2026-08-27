# 분산 Jackal 구조와 이전 계획

## 불변 조건

- ROS 2 Humble, domain 1, `rmw_fastrtps_cpp`를 모든 장비에서 동일하게 쓴다.
- 센서 토픽(`/camera`, `/livox`, `/scan`)은 전역 이름을 유지한다.
- Clearpath와 Nav2는 `/j100_0519` namespace를 사용한다.
- Fast DDS의 네트워크 UDP는 `192.168.50.0/24` 전용 LAN에만 bind한다.
- 실제 플랫폼 속도 입력은 monitor-only 검증과 분리하며, commissioning 전에는
  forwarding하지 않는다.

## Phase A: D455-only

```text
Laptop 192.168.50.1                 NUC 192.168.50.2
-------------------                 ----------------
RViz / CLI                          D455 driver
laptop heartbeat   <--- Fast DDS --> nuc heartbeat
fixed zero command ----------------> CLI subscriber
                                      platform OFF
```

NUC의 기존 `192.168.131.1/24`, 기관망 DHCP `10.10.22.98/22`, default route는
보존한다. DDS XML의 로컬 interface allowlist 때문에 기관망 쪽으로 discovery와 user
data가 나가지 않아야 한다. 이 마지막 문장은 설정 의도이며 packet capture로 확인해야
확정할 수 있다.

## Phase B: MID360과 Laptop Nav2

```text
MID360 192.168.1.130
          |
          | sensor UDP (not DDS)
          v
NUC br0 192.168.1.5 + 192.168.50.2       Laptop 192.168.50.1
----------------------------------       -------------------
Livox driver -> /livox/lidar             AMCL + Nav2
PointCloud -> /scan        ------------> map / scan consumer
D455                                     Twist -> TwistStamped
safety bridge (monitor only) <---------- /j100_0519/nav2_cmd_vel
no /j100_0519/cmd_vel publisher
```

Nav2의 최종 `geometry_msgs/msg/Twist`는
`/j100_0519/nav2_cmd_vel_unstamped`에 격리한다. stamper가 현재 ROS clock과
`base_link` frame을 붙여 `geometry_msgs/msg/TwistStamped`인
`/j100_0519/nav2_cmd_vel`을 만든다. NUC safety bridge는 이 토픽을 관찰하지만
기본값에서는 output publisher를 만들지 않는다. 별도 commissioning에서 forwarding을
켤 때에만 header를 제거하고 Clearpath Humble API 타입인 `geometry_msgs/msg/Twist`로
`/j100_0519/cmd_vel`에 출력한다.

지도와 MID360 extrinsic은 repository에서 임의 생성하지 않는다. 지도 YAML/이미지는
사용자 보유 파일을 넣는다. MID360 기본 장착값은 기존 사용자 workspace의
`base_link -> livox_frame` 설정을 가져왔지만 아직 이 package에서 실측하지 않았으므로
확인 후 static TF 또는 URDF에 반영한다. 현재
Nav2 odometry 입력 토픽은 `/j100_0519/platform/odom`으로 추론해 두었으며 MCU 연결
후 실제 Clearpath graph로 검증해야 한다.

## Phase C: Radxa X4 도입

```text
                  dedicated unmanaged LAN hub
             192.168.50.0/24, no institutional uplink

  Radxa X4 .3             NUC .2                 Laptop .1
  cpr-j100-0519           jackal-sensors
  ------------            --------------         -------------
  MCU serial              D455 / MID360           RViz / CLI
  Clearpath platform      PointCloud -> scan      goals / rosbag
  command watchdog        AMCL / Nav2             diagnostics
```

### 이전 순서

1. Radxa에 Ubuntu 22.04와 ROS 2 Humble을 설치하고 `.50.3` 통신을 검증한다.
2. NUC hostname을 `jackal-sensors`로 변경한 뒤 재부팅하고 DNS/SSH known-host를
   갱신한다.
3. Radxa hostname을 `cpr-j100-0519`로 설정한다. 두 장비가 동시에 같은 hostname을
   쓰는 구간을 만들지 않는다.
4. Clearpath Humble stack과 기존 `robot.yaml`을 Radxa로 옮기고 domain 1,
   namespace `j100_0519`, Fast DDS, 실제 MCU 장치를 반영해 platform 파일을 다시
   생성한다.
5. MCU USB/serial을 Radxa로 옮기고 platform만 단독 검증한다. 이때 바퀴를 지면에서
   분리하거나 제조사 commissioning 절차를 따른다.
6. NUC에서 D455, MID360, `/scan`, AMCL, Nav2를 순차 활성화한다.
7. NUC를 chrony server, Radxa와 Laptop을 client로 구성하고 offset을 기록한다.
8. monitor-only command 도달 시험 후 별도 승인된 commissioning에서만
   `forward_cmd_vel=true`를 사용한다.

### 데이터 배치

대역폭과 지연을 줄이기 위해 D455 이미지와 MID360 raw PointCloud는 NUC 내부
처리에 우선 사용한다. Laptop 기본 RViz/기록 profile은 `/scan`, map, odom, TF,
diagnostics, perception 결과만 구독한다. raw 센서가 필요한 실험에서만 명시적으로
활성화한다.

### 시간과 command safety

NUC는 센서 timestamp의 기준이 되므로 chrony server 역할을 맡는다. Radxa platform
watchdog은 마지막 유효 명령이 0.5초 이상 오래되면 0 속도를 계속 출력해야 한다.
LAN cable 제거, Nav2 process kill, NUC power loss를 각각 시험해 물리 정지가 1초
이내인지 별도 계측한다. repository bridge의 timer 동작만으로 이 물리 안전 조건이
입증됐다고 보지 않는다.

## 완료 판정

| 단계 | 판정 기준 |
|---|---|
| A | 양방향 heartbeat 10초, D455 12 Hz 이상 30초, 고정 0 명령 수신 |
| B | `/scan`, `map -> odom -> base_link`, AMCL, Nav2 active, stamped 명령 도달 |
| B safety | bridge가 `/j100_0519/cmd_vel` publisher가 아니며 platform OFF |
| C network | 전용 hub에서 세 장비 heartbeat와 chrony offset 정상 |
| C safety | 0.5초 watchdog 및 링크 단절 1초 이내 물리 정지 시험 통과 |

각 판정은 실행 날짜, package commit, 실제 topic type/frame/rate, packet capture와 함께
기록해야 한다. 아직 측정하지 않은 항목을 통과로 표기하지 않는다.
