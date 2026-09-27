from fastapi.testclient import TestClient
from backend.app import create_app
from conftest import login
from test_sheet_recovery import setup
from test_app import ask


def test_production_same_origin_frontend_and_complete_flow(settings, ai, tmp_path):
    google, table = setup(settings, tmp_path)
    settings.app_mode = 'production'
    settings.ai_mode = 'gemini'
    settings.allowed_origins = 'https://turtlesoup-ytac.onrender.com'
    with TestClient(create_app(settings, ai=ai, google=google),
                    base_url=settings.allowed_origins) as c:
        root = c.get('/')
        assert root.status_code == 200 and 'text/html' in root.headers['content-type']
        for path in ('/app.js', '/config.js', '/style.css', '/turtle.svg'):
            assert c.get(path).status_code == 200
        assert 'apiBase: ""' in c.get('/config.js').text
        for path in ('/backend/config.py', '/private/roster.json', '/.env',
                     '/歐氏尖吻鮫.txt', '/docs/index.html', '/api/missing'):
            assert c.get(path).status_code == 404
        assert c.get('/healthz').json()['status'] == 'ok'
        assert c.get('/api/config').json()['sheets_enabled']
        h = login(c)
        activity = c.get('/api/activities', headers=h).json()['activities'][0]['id']
        game = c.post('/api/games', headers=h, json={'activity': activity}).json()
        assert ask(c, h, game['id']).json()['answer'] == '是'
        assert c.post(f"/api/games/{game['id']}/save", headers=h,
                      json={'question': '草稿', 'question_type': 'is'}).json()['sync'] == 'synced'
        assert c.post('/api/logout', headers=h).status_code == 200
        h = login(c)
        assert c.get(f"/api/games/{game['id']}", headers=h).json()['draft'] == '草稿'
        assert c.post(f"/api/games/{game['id']}/finish", headers=h).json()['state'] == 'finished'
        assert table[2][5] and table[2][6]
