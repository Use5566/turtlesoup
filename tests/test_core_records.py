import copy
import json
import uuid
import pytest
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.core_records import HEADERS, projection
from backend.sheets import GoogleSheets
from backend.readable_records import decode, cell


def literal(value):
    return {'formattedValue': str(value), 'userEnteredValue': {'stringValue': str(value)}}


class CoreSheet(GoogleSheets):
    def __init__(self, settings):
        super().__init__(settings)
        self.table = [[literal(v) for v in row] for row in [HEADERS,
            ['1', '1', '01234', 'alpha', 'beta'], ['1', '2', '23456', 'alpha', '']]]
        self.hidden = None
        self.hidden_props = None
        self.fail = False
        self.fail_after = False
        self.writes = 0
        self.reads = 0

    def metadata(self):
        sheets = [{'properties': {'sheetId': 0, 'title': '名冊', 'gridProperties': {'rowCount': 100}}}]
        if self.hidden_props:
            sheets.append({'properties': self.hidden_props})
        return {'sheets': sheets}

    def values(self, tab, cells):
        table = self.table if tab == '名冊' else self.hidden
        return [[c.get('formattedValue', '') for c in r] for r in table]

    def request(self, method, suffix='', **kwargs):
        if self.fail:
            raise OSError('offline')
        if method == 'GET':
            self.reads += 1
            sheets = [{'properties': {'sheetId': 0}, 'data': [{'startRow': 0, 'rowData': [
                {'values': copy.deepcopy(r)} for r in self.table]}]}]
            if isinstance(kwargs.get('params', {}).get('ranges'), list) and self.hidden is not None:
                sheets.append({'properties': {'sheetId': self.hidden_props['sheetId']},
                    'data': [{'startRow': 0, 'rowData': [{'values': copy.deepcopy(r)} for r in self.hidden]}]})
            return {'sheets': sheets}
        assert suffix == ':batchUpdate'
        for r in kwargs['json']['requests']:
            if 'addSheet' in r:
                self.hidden_props = copy.deepcopy(r['addSheet']['properties'])
                self.hidden = []
                continue
            update = r['updateCells']; start = update['start']
            table = self.table if start['sheetId'] == 0 else self.hidden
            if start['sheetId'] == 0:
                assert start['columnIndex'] == 5
            while len(table) <= start['rowIndex']:
                table.append([])
            row = table[start['rowIndex']]
            values = update['rows'][0]['values']
            row.extend([{} for _ in range(max(0, start['columnIndex']+len(values)-len(row)))])
            for i, value in enumerate(values, start['columnIndex']):
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
        assert all(not cell.get('note') for row in g.table for cell in row)
        assert g.hidden_props['hidden'] is True
        assert g.table[1][10]['userEnteredValue'] == {'numberValue': 34}
        assert g.table[2][8]['formattedValue'] == g.table[2][9]['formattedValue'] == ''
        visible = ' '.join(cell['formattedValue'] for cell in g.table[1][5:11])
        for forbidden in ('_restore', 'schema', 'PRIVATE_SECRET', '01234', ids[0], '2026-', '{', '}'):
            assert forbidden not in visible
        assert g.table[1][6]['formattedValue'] == '學生：牠是不是動物？\n主持人：是'
        assert g.table[1][8]['formattedValue'] == g.table[1][6]['formattedValue']
        assert c.post('/api/logout', headers=h).status_code == 200
    # Simulate the previous release's populated notes, then verify migration and restore.
    for n, student in [(1, '1:01'), (2, '1:02')]:
        stored = next(row for row in g.hidden[1:] if row[0]['formattedValue'] == student)
        for col, encoded in [(5, stored[1]), (6, stored[2])]:
            g.table[n][col]['note'] = cell(json.loads(encoded['formattedValue']), student)['note']
    g.hidden = g.hidden_props = None
    g._core_metadata = None
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


def test_migrate_notes_atomically_and_reorder_roster(settings, ai, tmp_path):
    g = prepare(settings, tmp_path)
    # Existing empty notes written by the previous release migrate without changing identity.
    for n, student in [(1, '1:01'), (2, '1:02')]:
        g.table[n].extend([cell({}, student), cell({}, student, True)])
    g.write_student_records([], True)
    assert all(not c.get('note') for row in g.table for c in row)
    before = copy.deepcopy(g.hidden)
    g.table[1], g.table[2] = g.table[2], g.table[1]
    g.write_student_records([], True)
    assert g.hidden == before
    rows = g.recovery_rows()
    assert [r[:2] for r in rows[1:]] == [['1','02'], ['1','01']]


def test_changed_draft_uses_two_combined_reads(settings, ai, tmp_path):
    g = prepare(settings, tmp_path)
    with TestClient(create_app(settings, ai=ai, google=g)) as c:
        h = login(c)
        a = c.get('/api/activities', headers=h).json()['activities'][0]
        game = c.post('/api/games', headers=h, json={'activity': a['id']}).json()
        before = g.reads
        assert c.post('/api/games/'+game['id']+'/save', headers=h, json={'question':'新草稿'}).status_code == 200
        assert g.reads - before == 2


def test_startup_failure_releases_connections(settings, ai, tmp_path):
    g = prepare(settings, tmp_path)
    app = create_app(settings, ai=ai, google=g)
    closed = []
    close, dispose = g.close, app.state.service.store.engine.dispose
    def close_google():
        close(); closed.append('google')
    def close_database():
        dispose(); closed.append('database')
    g.close = close_google
    app.state.service.store.engine.dispose = close_database
    g.fail = True
    with pytest.raises(OSError):
        with TestClient(app):
            pass
    assert closed == ['google', 'database']


def test_first_only_and_twenty_turn_limit_apply_to_old_games(settings, ai, tmp_path):
    from backend.models import Game, Turn
    from sqlalchemy import select
    g = prepare(settings, tmp_path)
    app = create_app(settings, ai=ai, google=g)
    with TestClient(app) as c:
        h = login(c)
        activities = c.get('/api/activities', headers=h).json()['activities']
        first = c.post('/api/games', headers=h, json={'activity':activities[0]['id']}).json()
        second = c.post('/api/games', headers=h, json={'activity':activities[1]['id']}).json()
        with app.state.service.store.transaction() as db:
            old = db.scalar(select(Game).where(Game.uid == first['id']))
            puzzle = json.loads(old.puzzle); puzzle['max_turns'] = 30; old.puzzle = json.dumps(puzzle)
            for n in range(19):
                db.add(Turn(request_id=str(uuid.uuid4()), game_id=old.id, sequence=n+1,
                    question='既有提問', question_type='is', model='mock', status='answered', answer='是', usage='{"totalTokenCount":1}'))
        settings.first_puzzle_only = True
        assert len(c.get('/api/activities',headers=h).json()['activities']) == 1
        assert c.post('/api/games',headers=h,json={'activity':activities[1]['id']}).status_code == 404
        assert c.post('/api/games/'+second['id']+'/questions',headers=h,json={'request_id':str(uuid.uuid4()),'question':'是不是？'}).status_code == 409
        assert c.get('/api/games/'+first['id'],headers=h).json()['max_turns'] == 20
        assert c.post('/api/games/'+first['id']+'/questions',headers=h,json={'request_id':str(uuid.uuid4()),'question':'是不是？'}).status_code == 200
        assert c.post('/api/games/'+first['id']+'/questions',headers=h,json={'request_id':str(uuid.uuid4()),'question':'是不是？'}).status_code == 409
        assert ai.calls == 1
        assert c.post('/api/games/'+first['id']+'/finish',headers=h).status_code == 200
        assert g.table[1][5]['formattedValue'] == '已完成所有指定題目'
    with TestClient(create_app(settings, ai=ai, google=g)) as c:
        h = login(c)
        restored = c.post('/api/games',headers=h,json={'activity':activities[0]['id']}).json()
        assert restored['id'] == first['id'] and len(restored['turns']) == 20
        assert restored['state'] == 'finished' and restored['max_turns'] == 20
