"""Linux shared browser: all service commands and browser launches are mocked."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import shared_browser as sb


@pytest.fixture
def linux(tmp_path, monkeypatch):
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'config'))
    monkeypatch.setenv('DISPLAY', ':77')
    monkeypatch.setenv('WAYLAND_DISPLAY', 'wayland-test')
    monkeypatch.setenv('SECRET_TEST', 'never-import')
    monkeypatch.setattr(sb.platform, 'system', lambda: 'Linux')
    monkeypatch.setattr(sb, 'ROOT', tmp_path / 'state')
    monkeypatch.setattr(sb, 'PROFILE_DIR', tmp_path / 'state' / 'hermes')
    monkeypatch.setattr(sb, 'chromium', lambda: '/opt/chrome path/$browser%test')
    monkeypatch.setattr(sb, 'profile_in_use', lambda: False)
    monkeypatch.setattr(sb, 'listening', lambda: {'pages': 1})
    monkeypatch.setattr(sb, 'wait_for', lambda cond, seconds: cond())
    calls = []
    state = {'active': False}
    def run(args, **kwargs):
        calls.append(args)
        assert args[0] == 'systemctl', 'test must never launch a browser or real service'
        verb = args[2]
        if verb == 'is-active':
            return subprocess.CompletedProcess(args, 0 if state['active'] else 3,
                                               'active\n' if state['active'] else 'inactive\n', '')
        if verb in ('start', 'restart'):
            state['active'] = True
        elif verb == 'stop':
            state['active'] = False
        return subprocess.CompletedProcess(args, 0, '', '')
    monkeypatch.setattr(sb.subprocess, 'run', run)
    return tmp_path, calls, state


def test_linux_install_persists_mode_secure_unit_and_squadctl_status(linux, capsys):
    tmp, calls, _ = linux
    assert sb.main(['install', '--visible']) == 0
    unit = tmp / 'config/systemd/user/ai.hermes.shared-browser.service'
    data = unit.read_text()
    assert '--headless=new' not in data
    assert '--remote-debugging-address=127.0.0.1' in data
    assert '$browser%%test' in data
    assert (tmp / 'state').stat().st_mode & 0o777 == 0o700
    assert (tmp / 'state/hermes').stat().st_mode & 0o777 == 0o700
    assert sb.main(['install']) == 0
    assert unit.read_text() == data
    assert sb.main(['status']) == 0
    status = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert status['service_installed'] and status['service_loaded'] and status['plist_current']
    assert sb.main(['install', '--headless']) == 0
    assert '--headless=new' in unit.read_text()
    imports = [c for c in calls if c[2] == 'import-environment']
    assert imports and 'DISPLAY' in imports[0] and 'WAYLAND_DISPLAY' in imports[0]
    assert all('SECRET_TEST' not in c for c in imports)


def test_linux_start_stop_uninstall(linux):
    tmp, calls, state = linux
    assert sb.main(['install']) == 0
    assert sb.main(['stop']) == 0 and not state['active']
    assert sb.main(['start']) == 0 and state['active']
    assert sb.main(['uninstall']) == 0
    assert not (tmp / 'config/systemd/user/ai.hermes.shared-browser.service').exists()
    assert {'enable', 'disable', 'daemon-reload'} <= {c[2] for c in calls}


def test_linux_login_restores_service_on_probe_error(linux, monkeypatch):
    _, calls, state = linux
    state['active'] = True
    def probe():
        raise sb.ProbeError('failed')
    monkeypatch.setattr(sb, 'profile_in_use', probe)
    assert sb.main(['login']) == 1
    verbs = [c[2] for c in calls]
    assert verbs.index('stop') < verbs.index('start')
    assert state['active']


def test_login_fails_when_restored_service_never_becomes_ready(linux, monkeypatch):
    _, calls, state = linux
    state['active'] = True
    run = sb.subprocess.run
    def launch(args, **kwargs):
        if args[0] != 'systemctl':
            return subprocess.CompletedProcess(args, 0, '', '')
        return run(args, **kwargs)
    monkeypatch.setattr(sb.subprocess, 'run', launch)
    monkeypatch.setattr(sb, 'listening', lambda: None)
    with pytest.raises(SystemExit, match='restor.*(ready|listen)'):
        sb.main(['login'])
    assert any(c[2] == 'start' for c in calls)


def test_systemd_quote_escapes_carriage_return():
    assert sb.systemd_quote('a\rb') == '"a\\rb"'


def test_linux_busy_profile_never_starts_service(linux, monkeypatch):
    _, calls, _ = linux
    monkeypatch.setattr(sb, 'profile_in_use', lambda: True)
    with pytest.raises(SystemExit, match='holds'):
        sb.main(['install'])
    assert not any(c[2] in ('start', 'restart') for c in calls)


def test_linux_missing_systemctl_has_actionable_error(linux, monkeypatch):
    def missing(*args, **kwargs):
        raise FileNotFoundError('systemctl')
    monkeypatch.setattr(sb.subprocess, 'run', missing)
    with pytest.raises(SystemExit, match='systemctl'):
        sb.main(['status'])


def test_unsupported_os_is_rejected(monkeypatch):
    monkeypatch.setattr(sb.platform, 'system', lambda: 'Windows')
    with pytest.raises(SystemExit, match='[Uu]nsupported'):
        sb.main(['login'])


def test_login_without_install_creates_private_profile(linux, monkeypatch):
    tmp, calls, _ = linux
    run = sb.subprocess.run
    def launch(args, **kwargs):
        if args[0] != 'systemctl':
            assert args[0] == '/opt/chrome path/$browser%test'
            assert f"--user-data-dir={tmp / 'state/hermes'}" in args
            assert (tmp / 'state').stat().st_mode & 0o777 == 0o700
            assert (tmp / 'state/hermes').stat().st_mode & 0o777 == 0o700
            return subprocess.CompletedProcess(args, 0, '', '')
        return run(args, **kwargs)
    monkeypatch.setattr(sb.subprocess, 'run', launch)
    assert sb.main(['login', 'https://example.org']) == 0
    assert not any(c[2] == 'start' for c in calls)


def test_unavailable_user_manager_is_actionable(linux, monkeypatch):
    def unavailable(args, **kwargs):
        return subprocess.CompletedProcess(args, 1, '', 'Failed to connect to bus')
    monkeypatch.setattr(sb.subprocess, 'run', unavailable)
    with pytest.raises(SystemExit, match='user manager'):
        sb.main(['install'])


def test_linux_login_restores_after_interrupted_browser(linux, monkeypatch):
    _, calls, state = linux
    state['active'] = True
    run = sb.subprocess.run
    def interrupted(args, **kwargs):
        if args[0] != 'systemctl':
            raise KeyboardInterrupt()
        return run(args, **kwargs)
    monkeypatch.setattr(sb.subprocess, 'run', interrupted)
    with pytest.raises(KeyboardInterrupt):
        sb.main(['login'])
    assert state['active'] and any(c[2] == 'start' for c in calls)


def test_squadctl_reconciles_stale_linux_unit(linux, monkeypatch, capsys):
    import squadctl
    tmp, calls, state = linux
    monkeypatch.setattr(sb, 'listening', lambda: {'pages': 1} if state['active'] else None)
    unit = tmp / 'config/systemd/user/ai.hermes.shared-browser.service'
    unit.parent.mkdir(parents=True)
    unit.write_text('old unit')
    state['active'] = True
    def run_quiet(args, timeout):
        command = args[-1]
        code = sb.main([command])
        return subprocess.CompletedProcess(args, code, capsys.readouterr().out, '')
    monkeypatch.setattr(squadctl, 'run_quiet', run_quiet)
    ctx = type('Context', (), {'src': tmp})()
    assert 'reinstalled' in squadctl.shared_browser_service(ctx, False)
    assert unit.read_bytes() == sb.service_unit()
    assert any(c[2] == 'stop' for c in calls)
    assert any(c[2] == 'start' for c in calls)


def test_x11_imports_xauthority_and_ignores_relative_xdg(linux, monkeypatch):
    tmp, calls, _ = linux
    monkeypatch.delenv('WAYLAND_DISPLAY', raising=False)
    monkeypatch.setenv('XAUTHORITY', str(tmp / 'Xauthority'))
    monkeypatch.setenv('XDG_CONFIG_HOME', 'relative-config')
    assert sb.main(['install', '--visible']) == 0
    assert (tmp / '.config/systemd/user/ai.hermes.shared-browser.service').is_file()
    imported = next(c for c in calls if c[2] == 'import-environment')
    assert 'DISPLAY' in imported and 'XAUTHORITY' in imported and 'WAYLAND_DISPLAY' not in imported


def test_systemctl_timeout_is_actionable(linux, monkeypatch):
    def timeout(args, **kwargs):
        assert kwargs.get('timeout') is not None
        raise subprocess.TimeoutExpired(args, kwargs['timeout'])
    monkeypatch.setattr(sb.subprocess, 'run', timeout)
    with pytest.raises(SystemExit, match='timed out'):
        sb.main(['status'])


def test_profile_probe_matches_literal_path_not_regex_or_prefix(tmp_path):
    import time
    path = tmp_path / 'profile.[x]+foo'
    proc = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)', f'--user-data-dir={path}'])
    try:
        time.sleep(0.1)
        assert sb.profile_in_use(path)
        assert not sb.profile_in_use(tmp_path / 'profile')
        assert not sb.profile_in_use(tmp_path / 'profile.Xfoo')
    finally:
        proc.terminate()
        proc.wait()


def test_systemd_exec_path_keeps_literal_dollar_but_escapes_argument(linux):
    data = sb.service_unit('/opt/a $file%name') .decode()
    assert '"/opt/a $file%%name"' in data
    assert '$$browser' not in data


def test_login_restores_if_stop_reports_failure_after_stopping(linux, monkeypatch):
    _, calls, state = linux
    state['active'] = True
    run = sb.subprocess.run
    def failed_stop(args, **kwargs):
        if args[2] == 'stop':
            calls.append(args)
            state['active'] = False
            return subprocess.CompletedProcess(args, 1, '', 'stop failed')
        return run(args, **kwargs)
    monkeypatch.setattr(sb.subprocess, 'run', failed_stop)
    with pytest.raises(SystemExit, match='stop failed'):
        sb.main(['login'])
    assert state['active'] and any(c[2] == 'start' for c in calls)


def test_profile_probe_terminated_by_signal_fails_closed(monkeypatch):
    monkeypatch.setattr(sb.subprocess, 'run', lambda *a, **k: subprocess.CompletedProcess(a, -9, '', ''))
    with pytest.raises(sb.ProbeError):
        sb.profile_in_use(Path('/private/profile'))


@pytest.mark.parametrize('command', ['stop', 'uninstall', 'login', 'install', 'start'])
def test_pending_restart_is_cancelled_before_profile_operations(linux, monkeypatch, command):
    tmp, calls, state = linux
    unit = tmp / 'config/systemd/user/ai.hermes.shared-browser.service'
    unit.parent.mkdir(parents=True)
    unit.write_text('old unit')
    pending = {'value': True}
    run = sb.subprocess.run
    def fake(args, **kwargs):
        if args[0] != 'systemctl':
            assert not pending['value'], 'login must not race the pending restart'
            calls.append(['browser'])
            return subprocess.CompletedProcess(args, 0, '', '')
        if args[2] == 'is-active' and pending['value']:
            calls.append(args)
            return subprocess.CompletedProcess(args, 3, 'activating\n', '')
        if args[2] == 'stop':
            pending['value'] = False
        return run(args, **kwargs)
    monkeypatch.setattr(sb.subprocess, 'run', fake)
    assert sb.main([command]) == 0
    verbs = [c[2] if c[0] == 'systemctl' else 'browser' for c in calls]
    assert 'stop' in verbs
    if command in ('login', 'install', 'start'):
        assert verbs.index('stop') < verbs.index('start')
    if command == 'login':
        assert verbs.index('stop') < verbs.index('browser') < verbs.index('start')
        assert state['active']
    if command == 'uninstall':
        assert verbs.index('stop') < verbs.index('disable')
    if command == 'install':
        assert verbs.index('stop') < verbs.index('daemon-reload')


@pytest.mark.parametrize('state,code', [('reloading', 0), ('activating', 3)])
def test_login_restores_supervised_lifecycle_states(linux, monkeypatch, state, code):
    _, calls, _ = linux
    run = sb.subprocess.run
    def fake(args, **kwargs):
        if args[0] != 'systemctl':
            return subprocess.CompletedProcess(args, 0, '', '')
        if args[2] == 'is-active':
            calls.append(args)
            return subprocess.CompletedProcess(args, code, state + '\n', '')
        return run(args, **kwargs)
    monkeypatch.setattr(sb.subprocess, 'run', fake)
    assert sb.main(['login']) == 0
    verbs = [c[2] for c in calls]
    assert verbs.index('stop') < verbs.index('start')


@pytest.mark.parametrize('code,output,error', [(3, '', 'Failed to connect to bus'),
                                               (4, '', 'Access denied'),
                                               (3, 'mystery\n', '')])
def test_unknown_systemd_state_fails_closed(linux, monkeypatch, code, output, error):
    _, calls, _ = linux
    run = sb.subprocess.run
    def fake(args, **kwargs):
        if args[2] == 'is-active':
            calls.append(args)
            return subprocess.CompletedProcess(args, code, output, error)
        return run(args, **kwargs)
    monkeypatch.setattr(sb.subprocess, 'run', fake)
    with pytest.raises(SystemExit, match='systemctl'):
        sb.main(['login'])
    assert not any(c[2] in ('stop', 'start') for c in calls)


def test_missing_unit_inactive_exit_four_is_not_an_error(linux, monkeypatch):
    run = sb.subprocess.run
    def fake(args, **kwargs):
        if args[2] == 'is-active':
            return subprocess.CompletedProcess(args, 4, 'inactive\n', '')
        return run(args, **kwargs)
    monkeypatch.setattr(sb.subprocess, 'run', fake)
    assert sb.main(['stop']) == 0


def test_login_reports_browser_failure_and_restores_service(linux, monkeypatch):
    _, calls, state = linux
    state['active'] = True
    run = sb.subprocess.run
    def failing_browser(args, **kwargs):
        if args[0] != 'systemctl':
            return subprocess.CompletedProcess(args, 1, '', '')
        return run(args, **kwargs)
    monkeypatch.setattr(sb.subprocess, 'run', failing_browser)
    with pytest.raises(SystemExit, match='login browser'):
        sb.main(['login'])
    assert state['active'] and any(c[2] == 'start' for c in calls)
