import uuid
import pytest
from conftest import login, start


@pytest.mark.parametrize('question,answer', [('牠是不是動物？', '是'), ('牠有沒有海葵？', '有'),
    ('牠能不能防禦？', '能'), ('牠會不會受傷？', '會'), ('這樣對不對？', '對'), ('可不可以靠近？', '可')])
def test_question_without_type(client, question, answer):
    h = login(client); gid = start(client, h)
    body = {'request_id': str(uuid.uuid4()), 'question': question}
    result = client.post(f'/api/games/{gid}/questions', headers=h, json=body)
    assert result.status_code == 200 and result.json()['answer'] == answer
    assert client.post(f'/api/games/{gid}/questions', headers=h, json=body).json() == result.json()


def test_draft_without_type_and_no_selector(client):
    h = login(client); gid = start(client, h)
    result = client.post(f'/api/games/{gid}/save', headers=h, json={'question': '有沒有海葵？'})
    assert result.status_code == 200 and result.json()['draft'] == '有沒有海葵？'
    assert 'id="question-type"' not in client.get('/').text
