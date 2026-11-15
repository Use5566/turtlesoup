import copy
import json
import uuid
import pytest
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.core_records import HEADERS, projection
from backend.sheets import GoogleSheets
from backend.readable_records import decode


def literal(value):
    return {'formattedValue': str(value), 'userEnteredValue': {'stringValue': str(value)}}


class CoreSheet(GoogleSheets):
    def __init__(self, settings):
        super().__init__(settings)
        self.table = [[literal(v) for v in row] for row in [HEADERS,
            ['1', '1', '01234', 'alpha', 'beta'], ['1', '2', '23456', 'alpha', '']]]
        self.fail = False
        self.fail_after = False
        self.writes = 0

    def metadata(self):
        return {'sheets': [{'properties': {'sheetId': 0, 'title': '名冊', 'gridProperties': {'rowCount': 100}}}]}

    def values(self, tab, cells):
        return [[c.get('formattedValue', '') for c in r] for r in self.table]

    def request(self, method, suffix='', **kwargs):
        if self.fail:
            raise OSError('offline')
        if method == 'GET':
            return {'sheets': [{'data': [{'startRow': 0, 'rowData': [
                {'values': copy.deepcopy(r)} for r in self.table]}]}]}
        assert suffix == ':batchUpdate'
        for r in kwargs['json']['requests']:
            update = r['updateCells']; start = update['start']
            assert start['columnIndex'] == 5
            row = self.table[start['rowIndex']]
            row.extend([{} for _ in range(max(0, 11-len(row)))])
            for i, value in enumerate(update['rows'][0]['values'], 5):
                assert not value['userEnteredValue'].get('formulaValue')
                row[i] = copy.deepcopy(value)
                row[i]['formattedValue'] = str(next(iter(value['userEnteredValue'].values())))
        self.writes += 1
        if self.fail_after:
            self.fail_after = False
            raise OSError('response lost after successful write')
        return {}


def prepare(settings, tmp_path):
    settings.sheet_storage = settings.sheets_sync_enabled = settings.core_records = True
    settings.database_url = 'sqlite://'; settings.roster_mode = 'google'
    settings.google_roster_sheet_id = ''
    settings.puzzles_path = str(tmp_path / 'alpha.txt')
    for name in ('alpha', 'beta'):
        (tmp_path / (name+'.txt')).write_text('【謎面】測試故事。\n【湯底】PRIVATE_SECRET', encoding='utf-8')
    return CoreSheet(settings)


def login(c, seat='1', password='01234'):
    r = c.post('/api/login', json={'classroom': '1', 'seat': seat, 'password': password})
    assert r.status_code == 200
    return {'Authorization': 'Bearer '+r.json()['token']}


def test_two_puzzles_visible_columns_token_retry_and_restore(settings, ai, tmp_path):
    g = prepare(settings, tmp_path)
    before = copy.deepcopy([row[:5] for row in g.table])
    ids = []
    with TestClient(create_app(settings, ai=ai, google=g)) as c:
        h = login(c)
        activities = c.get('/api/activities', headers=h).json()['activities']
        for n, a in enumerate(activities):
            game = c.post('/api/games', headers=h, json={'activity': a['id']}).json();ids.append(game['id'])
            payload = {'question': '牠是不是動物？', 'request_id': str(uuid.uuid4())}
            assert c.post(f"/api/games/{game['id']}/questions", headers=h, json=payload).status_code == 200
            # Retry after completed provider request never adds tokens again.
            assert c.post(f"/api/games/{game['id']}/questions", headers=h, json=payload).status_code == 200
            if n == 0:
                g.fail_after = True
                assert c.post(f"/api/games/{game['id']}/finish", headers=h).status_code == 503
            assert c.post(f"/api/games/{game['id']}/finish", headers=h).status_code == 200
            assert g.table[1][5]['formattedValue'] == ('進行中' if n == 0 else '已完成所有指定題目')
        assert g.table[1][10]['userEnteredValue'] == {'numberValue': 34}
        assert g.table[2][8]['formattedValue'] == g.table[2][9]['formattedValue'] == ''
        visible = ' '.join(cell['formattedValue'] for cell in g.table[1][5:11])
        for forbidden in ('_restore', 'schema', 'PRIVATE_SECRET', '01234', ids[0], '2026-', '{', '}'):
            assert forbidden not in visible
        assert g.table[1][6]['formattedValue'] == '學生：牠是不是動物？\n主持人：是'
        assert g.table[1][8]['formattedValue'] == g.table[1][6]['formattedValue']
        assert c.post('/api/logout', headers=h).status_code == 200
    with TestClient(create_app(settings, ai=ai, google=g)) as c:
        h = login(c)
        assert c.get('/api/games/'+ids[0], headers=h).json()['state'] == 'finished'
        assert c.get('/api/games/'+ids[1], headers=h).json()['turns'][0]['answer'] == '是'
    assert [row[:5] for row in g.table] == before
    assert ai.calls == 2


def test_single_puzzle_completion_and_draft_failure(settings, ai, tmp_path):
    g = prepare(settings, tmp_path)
    with TestClient(create_app(settings, ai=ai, google=g)) as c:
        h = login(c, '2', '23456')
        a = c.get('/api/activities', headers=h).json()['activities'][0]
        game = c.post('/api/games', headers=h, json={'activity': a['id']}).json()
        g.fail = True
        assert c.post('/api/games/'+game['id']+'/save', headers=h,
                      json={'question': '草稿'}).status_code == 503
        g.fail = False
        assert c.post('/api/games/'+game['id']+'/save', headers=h,
                      json={'question': '草稿'}).status_code == 200
        assert c.post('/api/games/'+game['id']+'/finish', headers=h).status_code == 200
        assert g.table[2][5]['formattedValue'] == '已完成所有指定題目'
        assert g.table[2][10]['formattedValue'] == '0'
    with TestClient(create_app(settings, ai=ai, google=g)) as c:
        assert c.get('/api/games/'+game['id'], headers=login(c, '2', '23456')).json()['draft'] == '草稿'


def test_missing_usage_not_reported_as_zero_and_literal_questions():
    row = [literal(v) for v in ['1','1','01234','alpha','']]
    cells = projection('1:01', row, {'r': {'學生問題': '=IMPORTDATA("x")', '總tokens': '未提供'}}, {})
    assert cells[5]['userEnteredValue']['stringValue'] == '資料不完整（已知 0）'


def test_existing_non_system_notes_are_preserved(settings, ai, tmp_path):
    g = prepare(settings, tmp_path)
    g.table[1].extend([{'note':'teacher note'}])
    with pytest.raises(ValueError):
        with TestClient(create_app(settings, ai=ai, google=g)):
            pass
    assert g.table[1][5]['note'] == 'teacher note'
