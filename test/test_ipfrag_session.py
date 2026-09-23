"""Kernel ownership tests use files only; never modify host sysctls."""

import importlib.util
import json
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
    limit, timer, boot, state = [tmp_path / n for n in ('limit', 'timer', 'boot', 'state.json')]
    limit.write_text('4194304\n')
    timer.write_text('30\n')
    boot.write_text('test-boot\n')

    def change(action, **kwargs):
        return module.change(action, state, limit, timer, boot, lambda: False, **kwargs)

    return SimpleNamespace(limit=limit, timer=timer, boot=boot, state=state, change=change)


def test_apply_repeat_restore_both(case):
    res = case.change('apply')
    assert res['status'] == 'applied'
    assert (int(case.limit.read_text()), int(case.timer.read_text())) == (33554432, 3)
    assert case.state.exists()

    repeat = case.change('apply')
    assert repeat['status'] == 'already_applied'

    restored = case.change('restore')
    assert restored['status'] == 'restored'
    assert (int(case.limit.read_text()), int(case.timer.read_text())) == (4194304, 30)
    assert not case.state.exists()


def test_sufficient_memory_leaves_limit_unmanaged(case):
    case.limit.write_text('134217728\n')
    res = case.change('apply')
    assert res['status'] == 'already_sufficient'
    assert int(case.limit.read_text()) == 134217728
    assert not case.state.exists()


def test_active_stack_refuses_change(case):
    with pytest.raises(RuntimeError, match='Stop ROS'):
        module.change('apply', case.state, case.limit, case.timer, case.boot, lambda: True)
    assert int(case.limit.read_text()) == 4194304


@pytest.mark.parametrize('mismatch', ['boot', 'namespace'])
def test_identity_rejected(case, mismatch):
    case.change('apply')
    if mismatch == 'boot':
        case.boot.write_text('different-boot\n')
    else:
        state = json.loads(case.state.read_text())
        state['network_namespace'] = 'different-namespace'
        case.state.write_text(json.dumps(state))
    with pytest.raises(RuntimeError):
        case.change('restore')


def test_restore_without_state_raises(case):
    with pytest.raises(RuntimeError, match='No saved original'):
        case.change('restore')


def test_status_reporting(case):
    assert not module.status(kernel=case.limit, kernel_time=case.timer)['ready']
    case.change('apply')
    assert module.status(kernel=case.limit, kernel_time=case.timer)['ready']


def test_status_check_exit_codes(case, monkeypatch):
    monkeypatch.setattr(module, 'IPFRAG', case.limit)
    monkeypatch.setattr(module, 'IPFRAG_TIME', case.timer)

    assert module.main(['status', '--check']) == 1
    case.change('apply')
    assert module.main(['status', '--check']) == 0
