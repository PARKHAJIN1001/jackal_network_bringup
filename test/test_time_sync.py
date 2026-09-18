"""Static contracts only; never install packages or change the system clock."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def config_lines(name):
    return [line.strip() for line in (ROOT / 'config/time_sync' / name).read_text().splitlines()
            if line.strip() and not line.lstrip().startswith('#')]


def test_laptop_only_serves_nuc_and_requires_an_external_reference():
    lines = config_lines('chrony-laptop.conf')
    assert [s for s in lines if s.startswith('server ')] == [
        'server time.bora.net iburst minpoll 4 maxpoll 6']
    assert [s for s in lines if s.startswith('allow ')] == ['allow 192.168.50.2/32']
    assert 'bindaddress 192.168.50.1' in lines
    assert 'makestep 0.1 3' in lines
    assert not any(s.split()[0] in ('local', 'pool', 'confdir', 'sourcedir') for s in lines)
    assert 'bindcmdaddress 127.0.0.1' in lines and 'bindcmdaddress ::1' in lines


def test_nuc_resets_previous_external_servers_and_uses_only_laptop():
    lines = config_lines('90-jackal-lan-time.conf')
    assert [s for s in lines if s.startswith('NTP=')] == ['NTP=', 'NTP=192.168.50.1']
    assert 'FallbackNTP=' in lines
    assert 'PollIntervalMinSec=16' in lines and 'PollIntervalMaxSec=32' in lines
    assert 'RootDistanceMaxSec=5' in lines


def test_initial_frequency_acceptance_does_not_weaken_nuc_time_quality_gate():
    lines = config_lines('chrony-laptop.conf')
    assert [s for s in lines if s.startswith('maxupdateskew ')] == [
        'maxupdateskew 1000.0']
    assert not any(s.split()[0] in ('local', 'maxdistance') for s in lines)


def test_operator_script_is_valid_bash_and_requires_explicit_ack():
    script = ROOT / 'scripts/configure_time_sync.sh'
    assert subprocess.run(['bash', '-n', str(script)], check=False).returncode == 0
    for args in ([], ['nuc'], ['unknown', '--ros-stopped']):
        result = subprocess.run(['bash', str(script), *args], capture_output=True, text=True)
        assert result.returncode == 2
    text = script.read_text()
    assert 'mktemp -d /var/backups/jackal-time-sync.XXXXXX' in text
    assert 'chronyd -p -f' in text
    assert 'systemctl restart "$service"' in text
    assert 'sudo apt' not in '\n'.join(s for s in text.splitlines() if 'printf' not in s)
    for launch in (ROOT / 'launch').glob('*.py'):
        assert 'configure_time_sync' not in launch.read_text()


def test_chrony_validation_uses_apparmor_allowed_snapshot_before_live_changes():
    text = (ROOT / 'scripts/configure_time_sync.sh').read_text()
    stage = text.index('candidate="$(mktemp /etc/chrony/jackal-check.XXXXXX)"')
    copy = text.index('install -o root -g root -m 0644 -- "$source_file" "$candidate"')
    validate = text.index('chronyd -p -f "$candidate"')
    snapshot = text.index('source_file="$candidate"')
    backup = text.index('backup_dir="$(mktemp -d /var/backups/')
    apply = text.index('install -D -o root -g root -m 0644 -- "$source_file" "$target"')
    restart = text.index('systemctl restart "$service"')
    assert stage < copy < validate < snapshot < backup < apply < restart
    assert 'trap cleanup_candidate EXIT' in text
    assert 'rm -f -- "$candidate"' in text
    assert 'chronyd -p -f "$source_file"' not in text
    assert 'aa-disable' not in text and 'aa-complain' not in text
