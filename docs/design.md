# Jackal network and NUC sensor design

## 범위

이 패키지는 다음 기능만 소유한다.

- Laptop과 NUC의 전용 유선망 주소 및 Fast DDS profile
- NUC 부팅 시 D455와 MID360 자동 실행
- Clearpath platform service에 NUC DDS 환경 적용
- 장비 간 heartbeat와 센서 토픽 검증
- Laptop의 센서 확인용 RViz 실행

지도, localization, 경로 계획, 주행 명령 생성·변환은 이 패키지의 범위가 아니다.

## 고정 구성

| 항목 | 값 |
|---|---|
| ROS 2 | Humble |
| Domain | `1` |
| RMW | `rmw_fastrtps_cpp` |
| Laptop | `192.168.50.1/24` |
| NUC | `192.168.50.2/24` |
| NUC sensor LAN | `192.168.1.5/24` |
| MID360 | `192.168.1.130` |

센서 토픽은 전역 이름(`/camera/...`, `/livox/...`)을 유지한다. Clearpath platform
토픽의 `/j100_0519` namespace는 기존 platform 구성을 그대로 사용한다.

## 실행 구조

```text
Jackal MCU ──USB── Clearpath platform service ──┐
                                                │ Fast DDS / domain 1
D455 ──────────── jackal-sensors.service ───────┼── dedicated LAN ── Laptop
MID360 ────────── jackal-sensors.service ───────┘                   CLI / RViz
```

`clearpath-platform.service`가 Jackal platform을 소유한다.
`jackal-sensors.service`는 `robot.launch.py`를 다음 원칙으로 실행한다.

- `launch_platform=false`: platform 중복 실행 방지
- D455와 MID360 실행
- `base_link -> livox_frame` static transform 발행
- NUC network probe 실행
- 센서 driver가 비정상 종료되면 systemd 또는 launch respawn으로 복구

Laptop의 `laptop.launch.py`는 laptop network probe와 sensor-only RViz만 실행한다.
MID360은 raw `/livox/lidar` PointCloud2로 표시하며 지도나 경로 계획용 display를
포함하지 않는다.

## DDS discovery

역할별 Fast DDS XML은 UDP interface를 해당 장비의 `192.168.50.x` 주소 하나로
제한하고 SHM transport를 함께 유지한다. Laptop과 NUC profile은 현재 실제로 존재하는
두 peer만 초기 peer로 둔다. Radxa profile은 향후 네트워크 참가자 검증을 위해 남겨
두었지만 현재 부팅 경로에서는 사용하지 않는다.

multicast를 끄고 interface allowlist를 사용했으므로 기관망으로 DDS traffic이 나가지
않도록 의도한 구성이다. 다만 실제 패킷이 전용 LAN에만 흐른다는 결론은 packet
capture 없이 확정하지 않는다.

## 부팅과 환경 소유권

systemd service는 interactive `~/.bashrc`에 의존하지 않는다.
`start_nuc_sensors.sh`가 ROS, Livox driver package hook, SDK library path, workspace와
NUC network profile을 명시적으로 설정한다. `set -u`는 ROS setup을 모두 읽은 뒤에만
활성화한다.

NUC의 별도 terminal이나 Laptop terminal에서 ROS CLI를 사용할 때는 각 역할의
`jackal` shell 설정을 먼저 실행한다. 이 설정은 domain, RMW와 Fast DDS profile을
한 terminal에만 적용한다.

## 검증 기준

1. `check_network.sh preflight <role>`이 주소와 middleware 환경을 통과한다.
2. Laptop에서 NUC heartbeat를 10초 동안 연속 수신한다.
3. D455 Color/Depth/CameraInfo publisher와 실제 image rate를 확인한다.
4. MID360 PointCloud2/IMU publisher와 실제 point-cloud rate를 확인한다.
5. NUC 재부팅 후 SSH로 launch하지 않아도 같은 토픽이 Laptop에서 조회된다.

실측 결과에는 날짜, package revision, topic type, frame과 rate를 함께 기록한다.
장착 위치에서 `base_link -> livox_frame` 값이 측정됐다는 자료는 이 저장소에 없으므로,
현재 static transform은 기존 구성에서 가져온 값으로 추론하고 별도 실측 대상으로
취급한다.
