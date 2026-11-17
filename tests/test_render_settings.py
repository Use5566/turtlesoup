import pytest
from backend.config import Settings


@pytest.fixture
def render_env(monkeypatch):
    for name in Settings.__dataclass_fields__:
        monkeypatch.delenv(name.upper(), raising=False)
    monkeypatch.setenv('RENDER', 'true')
    monkeypatch.setenv('GEMINI_API_KEY', 'test-only-key')
    monkeypatch.setenv('GOOGLE_APPLICATION_CREDENTIALS', '/etc/secrets/google-service-account.json')
    return monkeypatch


def test_render_only_two_settings(render_env):
    s = Settings.from_env()
    assert (s.app_mode, s.ai_mode, s.roster_mode) == ('production', 'gemini', 'google')
    assert s.sheets_sync_enabled
    assert s.core_records
    assert s.google_sheet_id == '17LPzhH0CzpiRa_Our-qLanGF7IUJq1COVIjRJ6XI8Qw'
    assert s.google_roster_sheet_id == ''
    assert s.puzzles_path == '臺灣藍鵲.txt'
    assert s.allowed_origins == 'https://turtlesoup-ytac.onrender.com'
    assert s.google_roster_gid == 0
    assert s.gemini_model == 'gemini-3.5-flash-lite'
    assert s.gemini_max_output_tokens == 1024


def test_legacy_variables_cannot_disable_production(render_env):
    for name, value in {'APP_MODE': 'local', 'AI_MODE': 'mock', 'ROSTER_MODE': 'file',
                        'SHEETS_SYNC_ENABLED': 'false', 'PUZZLES_PATH': '/old/puzzles.json',
                        'ALLOWED_ORIGINS': '*', 'GEMINI_MAX_OUTPUT_TOKENS': '50'}.items():
        render_env.setenv(name, value)
    test_render_only_two_settings(render_env)


@pytest.mark.parametrize('name', ['GEMINI_API_KEY', 'GOOGLE_APPLICATION_CREDENTIALS'])
def test_missing_required_setting_fails_without_secret(render_env, name):
    render_env.setenv(name, ' ')
    with pytest.raises(ValueError) as error:
        Settings.from_env()
    assert name in str(error.value)
    assert 'test-only' not in str(error.value)


def test_render_rejects_ephemeral_database(render_env):
    render_env.setenv('DATABASE_URL', 'sqlite:///private/test.db')
    assert Settings.from_env().database_url == 'sqlite:////var/data/turtlesoup/turtlesoup.db'
    assert Settings.from_env().require_persistent_disk
    assert Settings.from_env().sheet_storage
    assert Settings.from_env().sync_seconds == 3


def test_render_refuses_unmounted_path(render_env, monkeypatch):
    from backend.models import Store
    monkeypatch.setattr('backend.models.os.path.ismount', lambda path: False)
    with pytest.raises(ValueError, match='Persistent Disk'):
        Store(Settings.from_env())


def test_local_stays_offline(render_env):
    render_env.delenv('RENDER')
    for name in ('DATABASE_URL', 'GEMINI_API_KEY', 'GOOGLE_APPLICATION_CREDENTIALS'):
        render_env.delenv(name, raising=False)
    s = Settings.from_env()
    assert (s.app_mode, s.ai_mode, s.roster_mode) == ('local', 'mock', 'file')
    assert not s.sheets_sync_enabled
