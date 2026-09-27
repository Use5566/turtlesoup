import uuid
from pathlib import Path

from fastapi.testclient import TestClient
from backend.app import create_app
from backend.config import ROOT
from conftest import login


def test_real_txt_end_to_end_and_revision(settings, ai, tmp_path):
    path = tmp_path / '歐氏尖吻鮫.txt'
    original = (ROOT / path.name).read_text(encoding='utf-8-sig').strip()
    path.write_text('\ufeff' + original, encoding='utf-8')
    settings.puzzles_path = str(path)
    with TestClient(create_app(settings, ai=ai)) as client:
        h = login(client)
        activity = client.get('/api/activities', headers=h).json()['activities'][0]
        assert activity['title'] == path.stem
        game = client.post('/api/games', headers=h, json={'activity': activity['id']}).json()
        assert game['surface'] == original
        assert 'solution' not in game
        puzzle = client.app.state.service.puzzles()[0]
        assert puzzle['solution'] == original
        response = client.post(f"/api/games/{game['id']}/questions", headers=h, json={
            'request_id': str(uuid.uuid4()), 'question': '牠是不是魚類？', 'question_type': 'is'})
        assert response.status_code == 200 and response.json()['answer'] == '是'
        path.write_text(original + '\n測試補充內容。', encoding='utf-8')
        new = client.get('/api/activities', headers=h).json()['activities'][0]
        assert new['id'] == activity['id'] and new['version'] != activity['version']
        next_game = client.post('/api/games', headers=h, json={'activity': new['id']}).json()
        assert next_game['id'] != game['id']
        assert client.get(f"/api/games/{game['id']}", headers=h).json()['surface'] == original


def test_empty_txt_fails_closed(settings, ai, tmp_path):
    path = tmp_path / 'empty.txt'
    path.write_text('  \n', encoding='utf-8')
    settings.puzzles_path = str(path)
    with TestClient(create_app(settings, ai=ai)) as client:
        assert client.get('/api/activities', headers=login(client)).status_code == 503


def test_sheet_assignment_hides_answer_and_is_per_student(settings, ai, tmp_path):
    path = tmp_path / '歐氏尖吻鮫.txt'
    path.write_text('PRIVATE_REFERENCE：歐氏尖吻鮫的顎可以向前彈出。', encoding='utf-8')
    settings.puzzles_path = str(path)
    app = create_app(settings, ai=ai)
    with TestClient(app) as client:
        roster = app.state.service.roster
        roster.read_rows = lambda: [
            ['班級', '座號', '密碼', '謎底', '謎面', '互動紀錄', '場次摘要'],
            ['999', '1', '12345', '歐氏尖吻鮫', '原本在我們面前的魚，瞬間消失了...'],
            ['999', '2', '54321', '', '']]
        h = login(client)
        listing = client.get('/api/activities', headers=h)
        activity = listing.json()['activities'][0]
        game = client.post('/api/games', headers=h, json={'activity': activity['id']})
        assert game.json()['surface'] == '原本在我們面前的魚，瞬間消失了...'
        for response in (listing, game):
            assert '歐氏尖吻鮫' not in response.text and 'PRIVATE_REFERENCE' not in response.text
        assert 'PRIVATE_REFERENCE' in app.state.service.puzzles('999:01')[0]['solution']
        other = login(client, '2', '54321')
        assert client.get('/api/activities', headers=other).json()['activities'] == []
        assert client.post('/api/games', headers=other, json={'activity': activity['id']}).status_code == 404
        roster.assignments['999:01'] = ('../outside', 'test')
        assert client.get('/api/activities', headers=h).status_code == 503
