import json
import pytest
from backend.sheets import GoogleSheets, Syncer
from conftest import login, start
from test_app import ask


def fake_google(settings):
    settings.roster_mode = 'google'
    google = GoogleSheets(settings)
    table = [['班級', '座號', '密碼', '謎底', '謎面', '互動紀錄', '場次摘要'],
             ['999', '2', '54321', '', '', '', ''],
             ['999', '1', '12345', '測試', '謎面', '', '']]
    google.metadata = lambda: {'sheets': [{'properties': {
        'sheetId': 0, 'title': '學生', 'gridProperties': {'rowCount': 100}}}]}
    def values(tab, cells):
        if cells == 'A1:G100':
            return [r[:] for r in table]
        number = int(cells.split(':')[0][1:])
        return [table[number - 1][:]]
    google.values = values
    calls = []
    notes = {}
    google.test_notes = notes
    def request(method, suffix='', **kwargs):
        if method == 'GET':
            return {'sheets': [{'data': [{'startRow': 1, 'rowData': [
                {'values': [{'note': n} for n in notes.get(i, ['', ''])]}
                for i in range(2, len(table) + 1)]}]}]}
        if suffix == ':batchUpdate':
            for request in kwargs['json']['requests']:
                change = request['updateCells']
                n = change['start']['rowIndex'] + 1
                cells = change['rows'][0]['values']
                table[n - 1][5:7] = [x['userEnteredValue']['stringValue'] for x in cells]
                notes[n] = [x['note'] for x in cells]
            calls.append(kwargs['json'])
            return {}
        assert suffix == '/values:batchUpdate'
        body = kwargs['json']
        assert body['valueInputOption'] == 'RAW'
        for write in body['data']:
            cells = write['range'].split('!')[1]
            assert cells.startswith('F') and ':G' in cells
            n = int(cells.split(':')[0][1:])
            table[n - 1][5:7] = write['values'][0]
        calls.append(body)
        return {}
    google.request = request
    return google, table, calls


def test_full_flow_to_fg_retry_and_finish(client, settings):
    h = login(client)
    gid = start(client, h)
    ask(client, h, gid, question='=IMPORTDATA("https://example.invalid")')
    google, table, calls = fake_google(settings)
    before = [r[:5] for r in table]
    table[2][5] = json.dumps({'older': {'學生問題': 'old'}})
    sync = Syncer(client.app.state.service.store, google)
    real_request = google.request
    def timeout(*args, **kw):
        real_request(*args, **kw)
        raise RuntimeError('timeout after commit')
    google.request = timeout
    with pytest.raises(RuntimeError):
        sync.once()
    google.request = real_request
    sync.once()
    assert len(json.loads(table[2][5])) == 2
    assert '12345' not in table[2][5] + table[2][6]
    assert 'older' in json.loads(table[2][5])
    client.post(f'/api/games/{gid}/finish', headers=h)
    # Identity lookup follows rows moved between sync cycles.
    table[1], table[2] = table[2], table[1]
    sync.once()
    assert json.loads(table[1][6])[gid]['場次狀態'] == 'finished'
    assert client.get(f'/api/games/{gid}', headers=h).json()['sync'] == 'synced'
    assert sorted(r[:5] for r in table) == sorted(before)
    assert table[2][5:] == ['', '']


@pytest.mark.parametrize('content', ['manual notes', '[]', '{"x": 1}', '{"x":{"text":"' + 'x' * 49000 + '"}}'], ids=['notes', 'array', 'bad-value', 'oversize'])
def test_preserves_invalid_or_full_cells(client, settings, content):
    h = login(client); start(client, h)
    google, table, calls = fake_google(settings)
    table[2][6] = content
    with pytest.raises(ValueError):
        Syncer(client.app.state.service.store, google).once()
    assert not calls and table[2][6] == content
