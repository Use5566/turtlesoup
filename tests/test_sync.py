import uuid
import pytest
from sqlalchemy import select
from backend.sheets import Syncer, GoogleSheets, TURN_TAB, GAME_TAB, TURN_HEADERS, GAME_HEADERS
from backend.models import Turn, Game
from conftest import login, start
from test_app import ask


class MemorySheets:
    def __init__(self): self.rows = {}; self.fail_after_write = False
    def write_rows(self, rows):
        for tab, number, values in rows:
            self.rows[(tab, number)] = values
        if self.fail_after_write: raise RuntimeError('timeout after server committed')


def test_retry_after_remote_commit_does_not_duplicate(client):
    h = login(client); gid = start(client, h); rid = str(uuid.uuid4())
    ask(client, h, gid, rid, '=IMPORTDATA("https://example.invalid")')
    remote = MemorySheets(); remote.fail_after_write = True
    sync = Syncer(client.app.state.service.store, remote)
    with pytest.raises(RuntimeError): sync.once()
    with client.app.state.service.store.transaction() as db:
        assert db.scalar(select(Turn)).synced == 0
    remote.fail_after_write = False
    sync.once(); sync.once()
    assert len(remote.rows) == 2
    assert remote.rows[(TURN_TAB, 2)][0] == rid
    assert remote.rows[(TURN_TAB, 2)][8].startswith('=IMPORTDATA')
    assert '12345' not in str(remote.rows)
    with client.app.state.service.store.transaction() as db:
        assert db.scalar(select(Turn)).synced == 1
        g = db.scalar(select(Game)); assert g.synced_revision == g.revision


def test_sheet_raw_and_collision_guard(settings):
    google = GoogleSheets(settings)
    google.metadata = lambda: {'sheets': [{'properties': {'title': TURN_TAB, 'sheetId': 1, 'gridProperties': {'rowCount': 1000}}}]}
    google.values = lambda *a: [TURN_HEADERS]
    calls = []
    def request(method, suffix='', **kwargs):
        calls.append((method, suffix, kwargs))
        if suffix == '/values:batchGet': return {'valueRanges': [{}]}
        return {}
    google.request = request
    google.write_rows([(TURN_TAB, 2, ['unique', '=1+1'])])
    assert calls[-1][2]['json']['valueInputOption'] == 'RAW'
    def collision(method, suffix='', **kwargs):
        assert method == 'GET'
        return {'valueRanges': [{'values': [['different-request']]}]}
    google.request = collision
    with pytest.raises(ValueError, match='停止同步'):
        google.write_rows([(TURN_TAB, 2, ['unique', '=1+1'])])


def test_missing_tabs_never_created_implicitly(settings):
    google = GoogleSheets(settings)
    google.metadata = lambda: {'sheets': []}
    with pytest.raises(ValueError): google.write_rows([(TURN_TAB, 2, ['id'])])


def test_production_rejects_mock_and_ephemeral_database(settings):
    settings.app_mode = 'production'
    with pytest.raises(ValueError): settings.validate()
    settings.ai_mode = 'gemini'; settings.roster_mode = 'google'
    with pytest.raises(ValueError): settings.validate()


def test_atomic_log_initialization(settings):
    google = GoogleSheets(settings)
    google.metadata = lambda: {'sheets': [{'properties': {'title': '名冊', 'sheetId': 0}}]}
    calls = []
    google.request = lambda *a, **kw: calls.append((a, kw))
    google.init_logs()
    assert len(calls) == 1
    operations = calls[0][1]['json']['requests']
    assert sum('addSheet' in op for op in operations) == 2
    assert all(op.get('updateCells', {}).get('start', {}).get('sheetId') != 0 for op in operations)


def test_preview_reserves_gemini_but_requires_sheets(settings):
    settings.app_mode = 'preview'
    with pytest.raises(ValueError): settings.validate()
    settings.sheet_storage = True
    settings.sheets_sync_enabled = True
    settings.allowed_origins = 'https://use5566.github.io'
    settings.validate()
    assert settings.ai_mode == 'mock' and settings.gemini_api_key == ''
