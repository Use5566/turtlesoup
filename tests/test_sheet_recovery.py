import json
import uuid
import pytest
from sqlalchemy import select
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.models import Game, Turn
from conftest import login
from test_app import ask
from test_student_sync import fake_google


def setup(settings, tmp_path):
    settings.sheet_storage = True
    settings.database_url = 'sqlite://'
    settings.sheets_sync_enabled = True
    settings.sync_seconds = 35
    path = tmp_path / '測試.txt'
    path.write_text('測試秘密資料', encoding='utf-8')
    settings.puzzles_path = str(path)
    google, table, _ = fake_google(settings)
    google.roster_rows = lambda gid: [r[:] for r in table]
    return google, table


def test_restart_recovers_questions_draft_and_finish(settings, ai, tmp_path):
    google, table = setup(settings, tmp_path)
    with TestClient(create_app(settings, ai=ai, google=google)) as c:
        h = login(c)
        activity = c.get('/api/activities', headers=h).json()['activities'][0]['id']
        g = c.post('/api/games', headers=h, json={'activity': activity}).json()
        rid = str(uuid.uuid4())
        assert ask(c, h, g['id'], rid).status_code == 200
        assert c.post(f"/api/games/{g['id']}/save", headers=h, json={
            'question': '尚未送出的草稿', 'question_type': 'has'}).json()['sync'] == 'pending'
        c.app.state.syncer.once()
        assert c.post('/api/logout', headers=h).status_code == 200
    with TestClient(create_app(settings, ai=ai, google=google)) as c:
        h = login(c)
        restored = c.post('/api/games', headers=h, json={'activity': activity}).json()
        assert restored['id'] == g['id']
        assert restored['draft'] == '尚未送出的草稿'
        assert restored['draft_kind'] == 'has'
        assert restored['turns'][0]['answer'] == '是'
        assert ask(c, h, g['id'], rid).status_code == 200
        assert ai.calls == 1
        assert c.post(f"/api/games/{g['id']}/finish", headers=h).json()['sync'] == 'synced'
    with TestClient(create_app(settings, ai=ai, google=google)) as c:
        h = login(c)
        assert c.get(f"/api/games/{g['id']}", headers=h).json()['state'] == 'active'
    assert '12345' not in table[2][5] + table[2][6]
    assert '學生：' in table[2][5] and '主持人：是' in table[2][5]
    assert '進行中' in table[2][6]
    for cell in table[2][5:7]:
        assert '_restore' not in cell and 'schema' not in cell and g['id'] not in cell
        assert '測試秘密資料' not in cell


def test_failed_cloud_sync_does_not_block_ai_or_logout(settings, ai, tmp_path):
    google, table = setup(settings, tmp_path)
    with TestClient(create_app(settings, ai=ai, google=google)) as c:
        h = login(c)
        activity = c.get('/api/activities', headers=h).json()['activities'][0]['id']
        g = c.post('/api/games', headers=h, json={'activity': activity}).json()
        write = google.request
        google.request = lambda *a, **kw: (_ for _ in ()).throw(OSError('offline'))
        assert ask(c, h, g['id']).status_code == 200
        assert ai.calls == 1
        assert c.post(f"/api/games/{g['id']}/save", headers=h, json={
            'question': '保留草稿', 'question_type': 'is'}).json()['sync'] == 'pending'
        with pytest.raises(OSError):
            c.app.state.syncer.once()
        assert c.post('/api/logout', headers=h).status_code == 200
        google.request = write
        c.app.state.syncer.once()
        h = login(c)
        result = c.get(f"/api/games/{g['id']}", headers=h).json()
        assert result['draft'] == '保留草稿'
        assert result['turns'][0]['answer'] == '是'
        assert result['sync'] == 'synced'
        assert ai.calls == 1


def test_crashed_processing_is_restored_as_interrupted(settings, ai, tmp_path):
    google, table = setup(settings, tmp_path)
    with TestClient(create_app(settings, ai=ai, google=google)) as c:
        h = login(c)
        activity = c.get('/api/activities', headers=h).json()['activities'][0]['id']
        g = c.post('/api/games', headers=h, json={'activity': activity}).json()
        ask(c, h, g['id'])
        c.app.state.syncer.once()
    records = json.loads(google.recovery_rows()[2][6])
    records[g['id']]['_restore']['turns'][0]['status'] = 'processing'
    records[g['id']]['_restore']['turns'][0]['answer'] = ''
    table[2][6] = json.dumps(records)
    google.test_notes.clear()
    table[2][5] = '{}'
    with TestClient(create_app(settings, ai=ai, google=google)) as c:
        h = login(c)
        result = c.get(f"/api/games/{g['id']}", headers=h).json()
        assert result['turns'][0]['status'] == 'interrupted'
        assert ai.calls == 1


def test_previous_fg_format_migrates(settings, ai, tmp_path):
    google, table = setup(settings, tmp_path)
    with TestClient(create_app(settings, ai=ai, google=google)) as c:
        h = login(c)
        activity = c.get('/api/activities', headers=h).json()['activities'][0]['id']
        g = c.post('/api/games', headers=h, json={'activity': activity}).json()
        ask(c, h, g['id'])
        c.app.state.syncer.once()
    recovered = google.recovery_rows()[2]
    records = json.loads(recovered[6])
    del records[g['id']]['_restore']
    table[2][6] = json.dumps(records)
    table[2][5] = recovered[5]
    google.test_notes.clear()
    with TestClient(create_app(settings, ai=ai, google=google)) as c:
        result = c.get(f"/api/games/{g['id']}", headers=login(c)).json()
        assert result['turns'][0]['answer'] == '是'
        c.app.state.syncer.once()
        assert not table[2][6].startswith('{')
        assert '主持人：是' in table[2][5]


def test_corrupt_recovery_fails_without_overwriting(settings, ai, tmp_path):
    google, table = setup(settings, tmp_path)
    table[2][6] = 'manual notes'
    with pytest.raises(ValueError):
        with TestClient(create_app(settings, ai=ai, google=google)):
            pass
    assert table[2][6] == 'manual notes'


def test_file_database_preserves_unsynced_answers_draft_and_tokens_across_restart(settings, ai, tmp_path):
    google, table = setup(settings, tmp_path)
    settings.database_url = 'sqlite:///' + str(tmp_path / 'durable.sqlite')
    with TestClient(create_app(settings, ai=ai, google=google)) as c:
        h = login(c)
        activity = c.get('/api/activities', headers=h).json()['activities'][0]['id']
        g = c.post('/api/games', headers=h, json={'activity': activity}).json()
        # The cloud has an older, empty game before it becomes unavailable.
        c.app.state.syncer.once()
        request = google.request
        google.request = lambda *a, **kw: (_ for _ in ()).throw(OSError('offline'))
        rid = str(uuid.uuid4())
        assert ask(c, h, g['id'], rid).status_code == 200
        assert c.post(f"/api/games/{g['id']}/save", headers=h, json={
            'question': '重啟後仍須保留的草稿', 'question_type': 'has'}).json()['sync'] == 'pending'
        with pytest.raises(OSError):
            c.app.state.syncer.once()
        assert c.post('/api/logout', headers=h).status_code == 200
    # Still offline: startup must use the initialized local database, without
    # replacing its newer records with the older cloud snapshot.
    with TestClient(create_app(settings, ai=ai, google=google)) as c:
        h = login(c)
        result = c.get(f"/api/games/{g['id']}", headers=h).json()
        assert result['draft'] == '重啟後仍須保留的草稿'
        assert result['turns'][0]['answer'] == '是'
        assert result['sync'] == 'pending'
        assert ask(c, h, g['id'], rid).status_code == 200
        assert ai.calls == 1
        with c.app.state.service.store.transaction() as db:
            turn = db.scalar(select(Turn))
            assert json.loads(turn.usage)['totalTokenCount'] == 17
            assert turn.synced == 0
        google.request = request
        scheduler = c.app.state.scheduler
        scheduler.next_due = scheduler.clock()
        scheduler.tick()
        assert c.get(f"/api/games/{g['id']}", headers=h).json()['sync'] == 'synced'
        with c.app.state.service.store.transaction() as db:
            game = db.scalar(select(Game))
            assert game.revision == game.synced_revision
    recovered = json.loads(google.recovery_rows()[2][6])[g['id']]['_restore']
    assert len(recovered['turns']) == 1
    assert recovered['turns'][0]['answer'] == '是'
    assert json.loads(recovered['turns'][0]['usage'])['totalTokenCount'] == 17
    assert recovered['game']['draft'] == '重啟後仍須保留的草稿'
