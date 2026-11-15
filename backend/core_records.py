"""Readable F–K projection. Recovery data lives in a separate hidden sheet."""
import hashlib
import json
import time
from .readable_records import decode, STATUS
from .roster import normalize

HEADERS = ['班級', '座號', '密碼', '謎面1', '謎面2', '作答狀況',
           '謎面1互動紀錄', '謎面1場次摘要', '謎面2互動紀錄', '謎面2場次摘要', '累計總Token']


def read_core(google, snapshot=None):
    metadata = snapshot[0] if snapshot else google.metadata()
    props = next(s['properties'] for s in metadata['sheets']
                 if s['properties']['sheetId'] == google.settings.google_roster_gid)
    tab = props['title'].replace("'", "''")
    if snapshot:
        result = {'sheets': [x for x in snapshot[1]['sheets'] if x['properties']['sheetId'] == props['sheetId']]}
    else:
        result = google.request('GET', params={'ranges': f"'{tab}'!A1:K{min(props['gridProperties']['rowCount'], 2000)}",
            'includeGridData': 'true', 'fields': 'sheets.data(startRow,rowData.values(formattedValue,userEnteredValue,note))'})
    rows = []
    for sheet in result.get('sheets', []):
        for grid in sheet.get('data', []):
            if grid.get('startRow', 0) != 0:
                raise ValueError('名冊讀取起點不正確')
            rows.extend(row.get('values', []) for row in grid.get('rowData', []))
    if not rows or [c.get('formattedValue', '').strip() for c in rows[0]][:11] != HEADERS:
        raise ValueError('正式名冊必須包含 A～K 指定欄位')
    index = {}
    for number, cells in enumerate(rows[1:], 2):
        values = [c.get('formattedValue', '') for c in cells]
        if not any(values):
            continue
        student = normalize(values[0], values[1])
        if student in index:
            raise ValueError('學生班級座號重複')
        cells = cells + [{} for _ in range(max(0, 11 - len(cells)))]
        index[student] = (number, cells)
    return props, index


def histories(student, cells, stored=None):
    if stored is not None and student in stored:
        # Once migrated, hidden storage is authoritative; notes are no longer written.
        return json.loads(json.dumps(stored[student][1]))
    result = []
    for col in (5, 6):
        note = cells[col].get('note', '')
        if not note:
            allowed = ('', '尚未開始', '未分配題目') if col == 5 else ('',)
            if cells[col].get('formattedValue', '') not in allowed:
                raise ValueError('既有紀錄缺少恢復備註，停止覆寫')
        result.append(decode('', note, student))
    return result


def activity_id(name):
    # Use the actual filename when available, matching Service.puzzles.
    from .config import ROOT
    from .puzzle_files import resolve_puzzle
    try:
        filename = resolve_puzzle(ROOT, name).name
    except ValueError:
        filename = name if name.lower().endswith('.txt') else name + '.txt'
    return 'txt-' + hashlib.sha256(filename.encode()).hexdigest()[:12]


def projection(student, cells, turns, games):
    texts, states = [], []
    for col in (3, 4):
        name = cells[col].get('formattedValue', '').strip()
        if not name:
            texts.extend(['', ''])
            continue
        activity = activity_id(name)
        sessions = [g for g in games.values() if g.get('活動編號') == activity]
        uids = {g['場次編號'] for g in sessions}
        questions = sorted((t for t in turns.values() if t.get('場次編號') in uids),
                           key=lambda t: (t.get('紀錄時間', ''), t.get('提問序號', 0), t.get('請求編號', '')))
        transcript = '\n\n'.join('學生：' + str(t.get('學生問題', '')) + '\n主持人：' +
            str(t.get('AI回答') or STATUS.get(t.get('處理狀態'), '尚無回覆')) for t in questions)
        latest = max(sessions, key=lambda g: (g.get('開始時間', ''), g.get('最後互動時間', '')), default=None)
        state = '尚未開始' if latest is None else ('已結束' if latest.get('場次狀態') == 'finished' else '進行中')
        states.append(state)
        count = sum(int(g.get('提問總數', 0)) for g in sessions)
        texts.extend([transcript, f'提問 {count} 次｜{state}'])
    status = ('未分配題目' if not states else '已完成所有指定題目' if all(s == '已結束' for s in states)
              else '尚未開始' if all(s == '尚未開始' for s in states) else '進行中')
    counts = [t.get('總tokens') for t in turns.values()]
    known = sum(x for x in counts if type(x) is int and x >= 0)
    total = known if all(type(x) is int and x >= 0 for x in counts) else f'資料不完整（已知 {known}）'
    visible = [status, *texts, total]
    output = [{} for _ in range(6)]
    for out, value in zip(output, visible):
        if len(str(value).encode('utf-16-le')) // 2 > 49000:
            raise ValueError('互動紀錄超出容量，請封存')
        out['userEnteredValue'] = {'numberValue': value} if type(value) is int else {'stringValue': value}
        out.setdefault('note', '')
    return output


def write_core(google, incoming, initialize=False):
    from .sheets import TURN_TAB, TURN_HEADERS, GAME_HEADERS
    with google.lock:
        state = read_snapshot(google)
        props, index = read_core(google, state)
        storage, stored, setup = read_storage(google, state)
        pending = {s: histories(s, c, stored) for s, (_, c) in index.items()} if initialize else {}
        for kind, _, values in incoming:
            student = normalize(values[2], values[3]) if kind == TURN_TAB else normalize(values[1], values[2])
            if student not in index:
                raise ValueError('學生已不在正式名冊，保留紀錄待處理')
            if student not in pending:
                pending[student] = histories(student, index[student][1], stored)
            col = 0 if kind == TURN_TAB else 1
            headers = TURN_HEADERS if col == 0 else GAME_HEADERS
            record = dict(zip(headers, values))
            if col == 1 and len(values) > len(headers):
                record['_restore'] = values[-1]
            pending[student][col][str(values[0])] = record
        requests = list(setup)
        next_row = max((r for r, _ in stored.values()), default=1) + 1
        for student, (turns, games) in pending.items():
            number, cells = index[student]
            output = projection(student, cells, turns, games)
            encoded = [student, pack(turns), pack(games)]
            if student not in stored or stored[student][1] != [turns, games]:
                row = stored[student][0] if student in stored else next_row
                if student not in stored:
                    next_row += 1
                if row > storage["gridProperties"]["rowCount"]:
                    raise ValueError("恢復資料超出容量，請封存")
                requests.append({"updateCells": {"start": {"sheetId": storage["sheetId"], "rowIndex": row-1, "columnIndex": 0},
                    "rows": [{"values": [{"userEnteredValue": {"stringValue": v}} for v in encoded]}], "fields": "userEnteredValue"}})
            # Do not write unchanged rows at every startup or autosave.
            if all(output[i]['userEnteredValue'] == cells[i+5].get('userEnteredValue') and
                   output[i]['note'] == cells[i+5].get('note', '') for i in range(6)):
                continue
            requests.append({'updateCells': {'start': {'sheetId': props['sheetId'], 'rowIndex': number - 1, 'columnIndex': 5},
                'rows': [{'values': output}], 'fields': 'userEnteredValue,note'}})
        if requests:
            # Re-read before writing; no atomic compare-and-swap exists in Sheets.
            state = read_snapshot(google)
            _, current = read_core(google, state)
            if read_storage(google, state)[1] != stored:
                raise ValueError("恢復資料已變動，稍後重試")
            if any(current.get(student) != index[student] for student in pending):
                raise ValueError('名冊已變動，稍後重試')
            google.request('POST', ':batchUpdate', json={'requests': requests})
            if setup:
                google._core_metadata = None


def recovery_core(google):
    _, index = read_core(google)
    _, stored, _ = read_storage(google)
    # Feed the existing versioned snapshot restorer without exposing metadata.
    result = [['班級', '座號', '密碼', '謎底', '謎面', '互動紀錄', '場次摘要']]
    for student, (_, cells) in index.items():
        turns, games = histories(student, cells, stored)
        result.append([*student.split(':'), '', '', '', json.dumps(turns), json.dumps(games)])
    return result


STORAGE_TITLE = '系統恢復資料（請勿編輯）'
STORAGE_HEADERS = ['student', 'turns_v1', 'games_v1']


def pack(records):
    value = json.dumps(records, ensure_ascii=False, separators=(',', ':'))
    if len(value.encode('utf-16-le')) // 2 > 49000:
        raise ValueError('恢復資料接近容量上限，請封存')
    return value


def read_storage(google, snapshot=None):
    metadata = snapshot[0] if snapshot else google.metadata()
    props = [s['properties'] for s in metadata['sheets']]
    storage = next((p for p in props if p['title'] == STORAGE_TITLE), None)
    if storage is None:
        storage = {'sheetId': max(p['sheetId'] for p in props) + 1,
                   'title': STORAGE_TITLE, 'hidden': True,
                   'gridProperties': {'rowCount': 2000, 'columnCount': 3}}
        return storage, {}, [{'addSheet': {'properties': storage}}, {'updateCells': {
            'start': {'sheetId': storage['sheetId'], 'rowIndex': 0, 'columnIndex': 0},
            'rows': [{'values': [{'userEnteredValue': {'stringValue': h}} for h in STORAGE_HEADERS]}],
            'fields': 'userEnteredValue'}}]
    if snapshot:
        sheet = next(x for x in snapshot[1]['sheets'] if x['properties']['sheetId'] == storage['sheetId'])
        rows = [[c.get('formattedValue', '') for c in row.get('values', [])]
                for grid in sheet.get('data', []) for row in grid.get('rowData', [])]
        rows = [row[:3] for row in rows]
    else:
        rows = google.values(STORAGE_TITLE, 'A1:C' + str(min(storage['gridProperties']['rowCount'], 2000)))
    if not rows or rows[0] != STORAGE_HEADERS:
        raise ValueError('恢復分頁格式不符，保留原資料')
    stored = {}
    for n, row in enumerate(rows[1:], 2):
        if not any(row):
            continue
        if len(row) != 3 or row[0] in stored:
            raise ValueError('恢復資料重複或格式不符')
        stored[row[0]] = (n, [decode(row[1], '', row[0]), decode(row[2], '', row[0])])
    return storage, stored, []


def read_snapshot(google):
    # Cache layout only, never student data. Read both bounded ranges together.
    from .sheets import address
    cached = getattr(google, '_core_metadata', None)
    if cached is None or time.monotonic() - cached[0] > 60:
        cached = (time.monotonic(), google.metadata())
        google._core_metadata = cached
    metadata = cached[1]
    ranges = []
    for sheet in metadata['sheets']:
        p = sheet['properties']
        if p['sheetId'] == google.settings.google_roster_gid:
            end = 'K'
        elif p['title'] == STORAGE_TITLE:
            end = 'C'
        else:
            continue
        ranges.append(address(p['title'], 'A1:' + end + str(min(p['gridProperties']['rowCount'], 2000))))
    result = google.request('GET', params={'ranges': ranges, 'includeGridData': 'true',
        'fields': 'sheets(properties.sheetId,data(startRow,rowData.values(formattedValue,userEnteredValue,note)))'})
    return metadata, result
