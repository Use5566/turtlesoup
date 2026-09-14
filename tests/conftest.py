import json
import pytest
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.config import Settings
from backend.ai import Decision


class CountingAI:
    def __init__(self):
        self.calls = 0
        self.result = 'yes'

    def judge(self, puzzle, question, kind, history):
        self.calls += 1
        return Decision(self.result, {'totalTokenCount': 17})


@pytest.fixture
def settings(tmp_path):
    roster = tmp_path / 'roster.json'
    roster.write_text(json.dumps([
        {'classroom': '999', 'seat': '1', 'password': '12345'},
        {'classroom': '999', 'seat': '2', 'password': '54321'}]), encoding='utf-8')
    puzzle = tmp_path / 'puzzles.json'
    puzzle.write_text(json.dumps([{'id': 'test', 'version': '1', 'title': '測試題', 'surface': '某人撐傘。',
        'solution': 'PRIVATE_SOLUTION_SENTINEL', 'facts': ['在做實驗'], 'max_turns': 3,
        'mock_examples': [{'question': '他是不是在做實驗？', 'type': 'is'}]}]), encoding='utf-8')
    return Settings(database_url='sqlite:///' + str(tmp_path / 'db.sqlite'),
                    roster_path=str(roster), puzzles_path=str(puzzle))


@pytest.fixture
def ai():
    return CountingAI()


@pytest.fixture
def client(settings, ai):
    app = create_app(settings, ai=ai)
    with TestClient(app) as c:
        yield c


def login(client, seat='1', password='12345'):
    r = client.post('/api/login', json={'classroom': '999', 'seat': seat, 'password': password})
    assert r.status_code == 200, r.text
    return {'Authorization': 'Bearer ' + r.json()['token']}


def start(client, headers):
    r = client.post('/api/games', headers=headers, json={'activity': 'test'})
    assert r.status_code == 200, r.text
    return r.json()['id']
