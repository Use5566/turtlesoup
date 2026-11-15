from pathlib import Path
import uuid
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.config import ROOT
from backend.roster import Roster


def test_one_digit_class_and_per_student_two_puzzles(settings, ai, tmp_path):
    for name in ('臺灣藍鵲', '南亞夜鷹'):
        (tmp_path / (name + '.txt')).write_text('【謎面】測試用故事。\n【湯底】\n', encoding='utf-8')
    settings.puzzles_path = str(tmp_path / '臺灣藍鵲.txt')
    roster = Roster(settings)
    roster.read_rows = lambda: [['班級', '座號', '密碼', '謎面1', '謎面2'],
        ['1', '1', '01234', '臺灣藍鵲', '南亞夜鷹'], ['1', '2', '23456', '臺灣藍鵲', '']]
    with TestClient(create_app(settings, roster=roster, ai=ai)) as c:
        def auth(seat, password):
            r = c.post('/api/login', json={'classroom': '1', 'seat': seat, 'password': password})
            assert r.status_code == 200
            return {'Authorization': 'Bearer ' + r.json()['token']}
        h = auth('1', '01234')
        activities = c.get('/api/activities', headers=h).json()['activities']
        assert len(activities) == 2
        game = c.post('/api/games', headers=h, json={'activity': activities[0]['id']}).json()
        response = c.post(f"/api/games/{game['id']}/questions", headers=h,
                          json={'question': '牠是不是在保護巢？', 'request_id': str(uuid.uuid4())})
        assert response.status_code == 503 and ai.calls == 0
        h2 = auth('2', '23456')
        assert len(c.get('/api/activities', headers=h2).json()['activities']) == 1
        assert c.post('/api/games', headers=h2, json={'activity': activities[1]['id']}).status_code == 404
        p = tmp_path / '臺灣藍鵲.txt'
        p.write_text(p.read_text(encoding='utf-8') + '教師提供的正式真相。', encoding='utf-8')
        updated = c.post('/api/games', headers=h, json={'activity': activities[0]['id']}).json()
        assert updated['id'] != game['id']
        assert c.post(f"/api/games/{updated['id']}/questions", headers=h,
                      json={'question': '牠是不是在保護巢？', 'request_id': str(uuid.uuid4())}).status_code == 200
