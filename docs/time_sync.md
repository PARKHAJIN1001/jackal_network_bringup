# Jackal LAN 지속 시각 동기화

## 구성과 적용 상태

```text
time.bora.net ── NTP ── laptop chrony (192.168.50.1)
                              └── NTP ── NUC systemd-timesyncd (192.168.50.2)
```

2026-09-11 적용 경과: 사용자가 양쪽 설정을 적용했고 NUC의 최초 동기화를 확인했다.
이후 root distance 초과로 반복 수신이 중단되어 laptop의 초기 보정 기준을 조정 중이다.
**지속 동기화·재부팅 복구와 ROS 운용 검증은 아직 완료되지 않았다.**
NUC는 외부 default route가 없으므로 기존 timesyncd에서 LAN IP를 직접 사용한다.
Laptop만 chrony를 설치한다. `apt install chrony`는 현재 Ubuntu 22.04에서 laptop의
`systemd-timesyncd` 패키지를 교체한다. NUC의 timesyncd는 제거하지 않는다.

- Laptop의 서버 소켓은 `192.168.50.1`, 허용 클라이언트는 `192.168.50.2/32`뿐이다.
  원격 chronyc 명령 포트는 열지 않는다(로컬 loopback 조회는 유지).
- 외부 시간원은 이번 망에서 실제 질의가 성공한 `time.bora.net` 하나로 시작한다.
  서버 다중화와 독립 시간원 교차 검증은 아직 하지 않았다.
- `local stratum`을 사용하지 않는다. 부팅 후 외부 기준을 얻지 못한 상태를
  정상 동기화처럼 가장하지 않는다. 인터넷 단절 때 holdover 상태와 reference age를
  확인해야 하며, 두 장비의 시각이 반드시 계속 일치한다고 보장하지 않는다.
- `makestep 0.1 3`은 chronyd 시작 후 처음 3회 갱신에 큰 오차를 step 보정할 수 있다.
  **ROS 운용 중 chrony 재시작, `init_time`, `ntpdate -b`, 수동 date 변경을 하지 않는다.**
- NUC poll은 16–32초다. 기존 외부 NTP/Fallback 목록을 drop-in에서 명시적으로
  초기화한다. 별도 networkd/DHCP의 LinkNTPServers가 없는지도 검증한다.
- Laptop의 `maxupdateskew=1000`은 chrony 자체 기본 주파수 추정 수용 문턱이다.
  최초 100 ppm 설정에서는 source Freq Skew가 약 110–200 ppm인 동안 tracking
  Skew가 초기 1,000,000 ppm에 머물고, 큰 Root dispersion으로 NUC가 응답을 거부했다.
  사용자 런타임 변경 후 tracking Skew가 약 111 ppm으로 낮아지고 수신이 재개됐다.
  이 값은 허용 시각 오차가 아니며, 아래 실제 offset/slew 검사를 대체하지 않는다.
  NUC RootDistanceMaxSec=5는 그대로 유지한다.
- IP/라우팅/DDS/커널 버퍼/기존 ROS 부팅 unit은 이 적용 스크립트가 변경하지 않는다.

## 1. Laptop 먼저 적용 — 사용자가 직접 실행

Nav2, FAST-LIVO2, perception, RViz를 모두 멈춘 상태에서 laptop 터미널에서 실행한다.
스크립트는 source checkout 또는 동일 구조의 staged bundle에서 실행하도록 설계했다.
ROS launch에서 자동 호출하거나 ROS 설치 공간의 실행 파일로 사용하지 않는다.

```bash
sudo apt install chrony
sudo bash ~/moai_navigation_ws/src/jackal_network_bringup/scripts/configure_time_sync.sh laptop --ros-stopped
```

설정은 `config/time_sync/chrony-laptop.conf`에서 `/etc/chrony/chrony.conf`로 설치한다.
기존 파일과 서비스 상태는 실행 때 표시되는 `/var/backups/jackal-time-sync.XXXXXX`에
보관한다. chronyd의 설정 문법 검사를 통과해야 설치한다.
Ubuntu AppArmor 정책 때문에 `sudo chronyd -p -f ~/...`도 홈 경로를 읽지 못한다.
스크립트는 root 소유 `/etc/chrony/jackal-check.XXXXXX` 임시 사본으로 검사하고,
검사를 통과한 **그 사본**을 설치한다. 임시 사본은 기존 config include 디렉터리 밖에
있으며 성공/실패 시 삭제한다. 검사 실패 시 실제 `chrony.conf`와 서비스는 그대로다.
AppArmor를 끄거나 홈 디렉터리 접근 권한을 넓히지 않는다.
APT는 다른 시간 서비스를 교체할 수 있으므로 표시되는 패키지 변경 목록을 확인한다.
실패하면 오류 출력과 backup 경로를 남기고 ROS를 시작하지 않는다.

설정 적용 직후 출력에 "Not synchronised"가 보일 수 있다. 서비스가 켜진 것만으로
완료가 아니다. 다음 조회 결과와 실제 NUC–laptop offset 확인이 필요하다.

```bash
chronyc tracking
chronyc sources -v
timedatectl show -p NTPSynchronized
ss -lun | grep ':123'
```

외부 source에 `^*`, tracking에 `Leap status: Normal`, 충분히 작은 `System time`
잔여 보정량이 확인된 뒤에만 다음 단계로 진행한다. 일회성 `chronyc makestep`이나
시간 복사로 이 검증을 대신하지 않는다. LAN NTP 접근이 막혔다면 방화벽 상태를
먼저 확인하고, 꼭 필요할 때만 NUC 주소 → laptop `eno1` UDP/123 규칙을 별도 승인받아
추가한다. 방화벽 전체 비활성화/포괄 포트 허용은 하지 않는다.

`Normal` 또는 `NTPSynchronized=yes`만으로 통과시키지 않는다. 2026-09-11에는
NUC가 마지막 성공 상태를 유지하면서 이후 응답을 계속 거부했다. laptop의 tracking
Skew/Root dispersion, NUC의 수신 timestamp 및 packet count 증가와 journal의
`Server has too large root distance` 재발 여부를 함께 확인한다.
`adjtime` pending=0도 chrony의 남은 보정이 0이라는 뜻은 아니므로 `System time`
필드를 별도로 검사한다. 런타임 `sudo chronyc maxupdateskew 1000`은 설정 파일에
저장되지 않는다. 현장 런타임 시험과 영구 설정 적용을 구분해 기록한다.

chrony가 NTP 클라이언트에 제공하는 추정 시각은 slew 중인 laptop OS 시각과 다를 수
있다. 따라서 **NUC에서 받은 NTP 응답의 offset을 NUC−laptop OS offset으로 해석하지
않는다**. ROS는 OS clock을 사용하므로 양쪽 OS 시각을 SSH 왕복시간과 함께 직접
비교한다. NTP 질의는 서버 응답 품질/Root distance 검사용으로 구분한다.
또한 NUC `PacketCount`는 수신 횟수이며 모두 보정에 수용됐다는 뜻은 아니다.
`NTPMessage`의 timestamp와 `Ignored`도 함께 기록한다.

## 2. NUC 적용 — laptop 동기화 확인 후

**Jackal을 고정하고 물리 E-stop을 건다.** 아래 서비스 정지는 센서와 플랫폼 ROS
연결을 잠시 중단하므로 소프트웨어 수동 조작에만 의존하면 안 된다.
NUC의 약 11.7초 역방향 보정 동안 센서/플랫폼 ROS도 정지해야 한다.

NUC에 `config/time_sync/90-jackal-lan-time.conf`와 `scripts/configure_time_sync.sh`를
같은 디렉터리 구조로 준비한다. 전체 저장소를 덮어쓰지 않아도 되며, 임시 디렉터리에
두 파일만 stage해 적용할 수 있다. 아래 source 경로는 NUC에도 새 파일을 복사한
경우에만 유효하다. stage 사용 시 해당 **실제 경로**로 바꾼다.

```bash
# NUC 터미널: laptop 동기화 확인 및 물리 E-stop 후
sudo systemctl stop jackal-sensors.service clearpath-platform.service
sudo bash ~/moai_navigation_ws/src/jackal_network_bringup/scripts/configure_time_sync.sh nuc --ros-stopped
```

스크립트는 센서/플랫폼 서비스가 아직 켜져 있으면 적용을 거부한다. 시간 설정만
설치하며 ROS를 자동 재시작하지 않는다. 대상은
`/etc/systemd/timesyncd.conf.d/90-jackal-lan-time.conf` 하나이고, 원래
`/etc/systemd/timesyncd.conf`는 직접 수정하지 않는다.

```bash
timedatectl show-timesync --all
timedatectl timesync-status
timedatectl show -p NTPSynchronized
```

`ServerAddress=192.168.50.1`, 증가하는 packet count와 `NTPSynchronized=yes`를
확인한다. SSH 왕복시간을 함께 측정한 두 장비의 실제 offset도 확인한다.
초기 운용 기준은 |NUC−laptop| **20 ms 이하**, pending slew **5 ms 이하**로 두고,
갱신 주기를 포함한 반복 표본에서 유지되는지 확인한다. 이는 이번 시스템의 시험
기준이지 NTP가 보장하는 정확도가 아니다. 엄밀한 장기 오차/드리프트 기준은 후속 계측한다.

모든 확인 후 사용자 승인하에 플랫폼과 센서를 다시 시작한다.

```bash
sudo systemctl start clearpath-platform.service jackal-sensors.service
```

재시작 후 NUC `forward_cmd_vel=false`와 센서 timestamp freshness를 다시 확인하고,
Nav2/relay → FAST-LIVO2 → 사용자 초기 pose 순서로 localization 기준선을 측정한다.
전체 perception은 기준선 이후 사용자가 별도 실행한다.

## 3. 재부팅·재연결 및 운용 제한

서비스 enable로 재부팅 후에도 설정은 유지된다. 그러나 **재부팅/케이블 재연결 후
자동 복구와 drift 성능은 적용 후 별도로 검증해야 한다.** 이번에는 플랫폼의 수동
조작을 NTP 가용성에 종속시키는 부팅 gate를 자동 추가하지 않았다.

NUC 센서가 동기화 전에 시작했거나 운용 중 큰 clock step이 발생했다면, 정지/E-stop
상태에서 해당 ROS 스택을 정리하고 동기화 확인 후 다시 시작한다. FAST-LIVO2 재시작 시
perception과 시각화도 재시작하고 AMCL의 2D Pose Estimate를 다시 입력한다.
노트북 LAN 주소가 바뀌거나 다른 클라이언트를 추가할 때는 두 설정의 주소와 ACL을
함께 재검토한다. 네트워크 단절이나 시각 불량을 TF tolerance 확대로 숨기지 않는다.

## 복구 방법

복구도 ROS를 멈추고 사용자가 sudo로 수행한다. 적용 때 표시된 **실제 backup 경로**와
그 안의 `previous-config`, `service-enabled.txt`, `service-active.txt`를 먼저 확인한다.
아래는 복구 절차 설명이며 가상의 backup 경로를 그대로 실행해서는 안 된다.

- Laptop의 chrony 설정만 되돌리기: `previous-config`를 `/etc/chrony/chrony.conf`로
  복사해 원래 설정을 복원하고 chrony를 재시작한다. 이 백업은 chrony 설치 후의 설정이다.
- Laptop을 원래 timesyncd로 완전히 되돌리기: chrony를 멈추고
  `sudo apt install systemd-timesyncd`로 패키지를 교체한다(chrony 제거 목록 확인).
  백업한 `timesyncd.conf`를 복원하고 원래 active/enabled 상태로 되돌린다.
  이 호스트의 최초 관측 상태는 timesyncd active, NTP=yes였으며 실제 동기화는 실패 중이었다.
- NUC: 이 파일이 최초 추가였다면 `/etc/systemd/timesyncd.conf.d/90-jackal-lan-time.conf`를
  backup 디렉터리로 **이동**해 비활성화한다. 기존 파일이 있었다면 `previous-config`로
  복원한다. timesyncd를 재시작하고 원래 service-enabled 상태도 복원한다.
- 복구는 시각 보정 자체를 되돌리는 작업이 아니다. 시각/offset을 재검증하기 전에는
  ROS를 재시작하지 않는다. 미확인 경로 삭제나 다른 설정 파일 일괄 삭제는 하지 않는다.

## 근거와 사전 검사

- [chrony 4.2 설정 공식 문서](https://chrony-project.org/doc/4.2/chrony.conf.html):
  allow/bindaddress, makestep, local reference 동작을 확인했다.
  [maxupdateskew](https://chrony-project.org/doc/4.2/chrony.conf.html#maxupdateskew)의
  기본값은 1000 ppm이며 주파수 추정 오차의 수용 여부를 제어한다.
- [chronyd 4.2 공식 문서](https://chrony-project.org/doc/4.2/chronyd.html):
  `-p`는 설정 출력·문법 검사 후 종료하며 clock daemon을 시작하지 않는다.
- [systemd v249 timesyncd 설정](https://github.com/systemd/systemd/blob/v249/man/timesyncd.conf.xml):
  빈 NTP 목록 초기화, per-link 서버와의 관계, 16초 minimum poll 제한을 확인했다.

Ubuntu 저장소의 chrony 4.2 deb를 `/tmp`에 다운로드·추출한 뒤 `chronyd -p -f`로
설정 문법만 검사했다(패키지 설치·daemon 실행 아님). 기존 네트워크 테스트와 신규
시간 설정 계약 테스트 18개, 새 Python 테스트 파일 flake8, shell `bash -n` 통과.
이 검사들은 실제 동기화 성공 또는 재부팅 안정성 검증을 대신하지 않는다.

2026-09-11 첫 sudo 적용은 설치본 AppArmor의 홈 경로 읽기 제한으로 문법 검사에서
실패했다. 설치 전 추출본 검사는 이 정책을 재현하지 못했다. 위 임시 사본 방식으로
수정하고 회귀 테스트를 추가했다. 실패 당시에는 LAN 설정을 설치/재시작하지 않았고,
APT가 시작한 기본 설정의 chrony는 별도로 실행 중이었다. 수정본 재적용과 동기화 확인은
사용자의 재실행으로 적용됐으며, 위 초기 수렴 문제의 연속 검증은 별도로 진행 중이다.
