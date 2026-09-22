"""Kernel ownership tests use files only; never modify host sysctls."""

import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location(
    'network_ipfrag', Path(__file__).resolve().parents[1] / 'scripts/ipfrag_session.py'
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.fixture
def case(tmp_path):
    limit, timer, boot, state = [tmp_path / n for n in ('limit', 'timer', 'boot', 'state')]
    limit.write_text('4194304')
    timer.write_text('30')
    boot.write_text('boot')

    def change(action, **kwargs):
        return module.change(action, state, limit, timer, boot, lambda: False, **kwargs)

    return SimpleNamespace(limit=limit, timer=timer, boot=boot, state=state, change=change)


def test_apply_repeat_restore_both(case):
    case.change('apply')
    assert (int(case.limit.read_text()), int(case.timer.read_text())) == (16777216, 3)
    case.change('apply')
    case.change('restore')
    assert (int(case.limit.read_text()), int(case.timer.read_text())) == (4194304, 30)
    assert not case.state.exists()


def test_sufficient_memory_changes_only_time(case):
    case.limit.write_text('134217728')
    case.change('apply')
    assert set(json.loads(case.state.read_text())['entries']) == {'ipfrag_time'}
    case.limit.write_text('268435456')
    case.change('restore')
    assert int(case.limit.read_text()) == 268435456
    assert int(case.timer.read_text()) == 30


@pytest.mark.parametrize('field', ['limit', 'timer'])
def test_external_change_refuses_all_writes(case, field):
    case.change('apply')
    getattr(case, field).write_text('999')
    before = (case.limit.read_text(), case.timer.read_text())
    for action in ('apply', 'restore'):
        with pytest.raises(RuntimeError, match='outside'):
            case.change(action)
        assert (case.limit.read_text(), case.timer.read_text()) == before
    assert case.state.exists()


def test_missing_kernel_no_guessed_original(case):
    case.timer.unlink()
    with pytest.raises(FileNotFoundError):
        case.change('apply')
    assert not case.state.exists()
    assert int(case.limit.read_text()) == 4194304


def test_partial_write_can_be_restored(case, monkeypatch):
    write = Path.write_text

    def fail_timer(path, text, *args, **kwargs):
        if path == case.timer:
            raise OSError('simulated write error')
        return write(path, text, *args, **kwargs)

    with monkeypatch.context() as context:
        context.setattr(Path, 'write_text', fail_timer)
        with pytest.raises(OSError):
            case.change('apply')
    assert case.state.exists()
    case.change('restore')
    assert int(case.limit.read_text()) == 4194304
    assert int(case.timer.read_text()) == 30


@pytest.mark.parametrize('mismatch', ['boot', 'namespace'])
def test_identity_rejected(case, mismatch):
    case.change('apply')
    if mismatch == 'boot':
        case.boot.write_text('other')
    else:
        state = json.loads(case.state.read_text())
        state['network_namespace'] = 'other'
        case.state.write_text(json.dumps(state))
    with pytest.raises(RuntimeError):
        case.change('restore')


def test_legacy_restores_only_saved_memory(case, tmp_path):
    legacy = tmp_path / 'legacy'
    legacy.write_text(
        json.dumps(
            {
                'original': 4194304,
                'target': 134217728,
                'boot': 'boot',
                'network_namespace': os.readlink('/proc/self/ns/net'),
            }
        )
    )
    case.limit.write_text('134217728')
    with pytest.raises(RuntimeError, match='Legacy'):
        case.change('apply', legacy_path=legacy)
    module.change('restore', legacy, case.limit, case.timer, case.boot, lambda: False)
    assert int(case.limit.read_text()) == 4194304
    assert int(case.timer.read_text()) == 30


def test_active_stack_and_status(case):
    with pytest.raises(RuntimeError, match='Stop ROS'):
        module.change('apply', case.state, case.limit, case.timer, case.boot, lambda: True)
    assert not module.status(case.limit, case.timer)['ready']
    case.change('apply')
    assert module.status(case.limit, case.timer, case.state, case.boot)['ready']


def test_only_memory_owned_when_time_already_ready(case):
    case.timer.write_text('3')
    case.change('apply')
    assert set(json.loads(case.state.read_text())['entries']) == {'ipfrag_high_thresh'}
    case.timer.write_text('7')
    with pytest.raises(RuntimeError, match='Unowned'):
        case.change('apply')
    case.change('restore')
    assert int(case.timer.read_text()) == 7


def test_write_verification_failure_retains_recovery(case, monkeypatch):
    write = Path.write_text

    def ignore_timer(path, text, *args, **kwargs):
        if path == case.timer:
            return len(text)
        return write(path, text, *args, **kwargs)

    with monkeypatch.context() as context:
        context.setattr(Path, 'write_text', ignore_timer)
        with pytest.raises(RuntimeError, match='verification'):
            case.change('apply')
    assert case.state.exists()
    case.change('restore')
    assert int(case.limit.read_text()) == 4194304


def test_status_check_exit_codes(case, monkeypatch, capsys):
    monkeypatch.setattr(module, 'STATE_DIR', case.state.parent)
    monkeypatch.setattr(module, 'LEGACY_DIR', case.state.parent / 'missing')
    actual_status = module.status
    monkeypatch.setattr(
        module, 'status', lambda **kw: actual_status(case.limit, case.timer, case.state, case.boot)
    )
    assert module.main(['status', '--check']) == 1
    case.change('apply')
    assert module.main(['status', '--check']) == 0
    case.timer.unlink()
    assert module.main(['status', '--check']) == 2
    assert 'error' in capsys.readouterr().out


@pytest.mark.parametrize('field,original', [('limit', '4194304'), ('timer', '30')])
def test_external_reset_to_original_also_refuses_all_writes(case, field, original):
    case.change('apply')
    getattr(case, field).write_text(original)
    before = case.limit.read_text(), case.timer.read_text()
    with pytest.raises(RuntimeError, match='outside'):
        case.change('restore')
    assert (case.limit.read_text(), case.timer.read_text()) == before
    assert case.state.exists()


def test_partial_restore_retains_each_phase_and_can_resume(case, monkeypatch):
    case.change('apply')
    write = Path.write_text

    def fail_timer(path, text, *args, **kwargs):
        if path == case.timer:
            raise OSError('simulated restore failure')
        return write(path, text, *args, **kwargs)

    with monkeypatch.context() as context:
        context.setattr(Path, 'write_text', fail_timer)
        with pytest.raises(OSError):
            case.change('restore')
    saved = json.loads(case.state.read_text())['entries']
    assert saved['ipfrag_high_thresh']['phase'] == 'restored'
    assert saved['ipfrag_time']['phase'] == 'restore_pending'
    with pytest.raises(RuntimeError, match='Restore in progress'):
        case.change('apply')
    status = module.status(case.limit, case.timer, case.state, case.boot)
    assert status['recovery_pending'] and not status['ready']
    assert status['ownership']['ipfrag_time']['owned']
    case.change('restore')
    assert (int(case.limit.read_text()), int(case.timer.read_text())) == (4194304, 30)
