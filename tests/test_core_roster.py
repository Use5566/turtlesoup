from fastapi.testclient import TestClient
from backend.app import create_app
from backend.roster import Roster
from test_sheet_recovery import setup
from conftest import login
from test_app import ask


def test_four_column_roster_and_separate_log_creation(settings, ai, tmp_path):
    google, table = setup(settings, tmp_path)
    settings.google_roster_sheet_id = 'separate-core'
    (tmp_path / '測試.txt').write_text('【謎面】\n一件奇怪的事。\n【湯底】\n秘密真相。', encoding='utf-8')
    roster = Roster(settings)
    core = [['班級', '座號', '密碼', '謎面'], ['999', '1', '12345', '測試.txt']]
    roster.read_rows = lambda: core
    table.pop()  # The new student's log row does not exist yet.
    request = google.request
    def append(method, suffix='', **kwargs):
        if suffix.endswith(':append'):
            table.extend(kwargs['json']['values'])
            return {}
        return request(method, suffix, **kwargs)
    google.request = append
    with TestClient(create_app(settings, roster=roster, google=google, ai=ai)) as c:
        h = login(c)
        activity = c.get('/api/activities', headers=h).json()['activities'][0]
        game = c.post('/api/games', headers=h, json={'activity': activity['id']}).json()
        assert game['surface'] == '一件奇怪的事。'
        assert '秘密真相' not in str(game)
        assert ask(c, h, game['id']).status_code == 200
        assert table[2][:3] == ['999', '01', '']
        assert '主持人：是' in table[2][5]
        assert len(core[0]) == 4 and len(core[1]) == 4


def test_empty_core_allows_start_but_no_accounts(settings):
    roster = Roster(settings)
    roster.read_rows = lambda: [['班級', '座號', '密碼', '謎面']]
    assert roster.classes() == []
    assert not roster.verify('999:01', '12345')
