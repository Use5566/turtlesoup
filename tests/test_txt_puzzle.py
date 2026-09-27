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
