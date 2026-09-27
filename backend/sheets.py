import json
import threading
from urllib.parse import quote
from datetime import datetime
from zoneinfo import ZoneInfo
from google.oauth2.service_account import Credentials
from google.auth.transport.requests import AuthorizedSession
from sqlalchemy import select
from .models import Game, Turn
from .roster import normalize

TURN_TAB = '海龜湯互動紀錄'
GAME_TAB = '海龜湯場次摘要'
TURN_HEADERS = ['請求編號', '紀錄時間', '班級', '座號', '活動編號', '場次編號', '題目版本',
                '提問序號', '學生問題', '問句類型', 'AI回答', '處理狀態', '模型', '總tokens']
GAME_HEADERS = ['場次編號', '班級', '座號', '活動編號', '題目版本', '開始時間', '最後互動時間',
                '提問總數', '場次狀態', '累計tokens', '資料版本']


def address(tab, cells):
    return "'" + tab.replace("'", "''") + "'!" + cells


def local_time(value):
    return datetime.fromisoformat(value).astimezone(ZoneInfo('Asia/Taipei')).strftime('%Y-%m-%d %H:%M:%S')


class GoogleSheets:
    def __init__(self, settings, session=None):
        self.settings, self.session = settings, session
        self.lock = threading.RLock()
        self.base = 'https://sheets.googleapis.com/v4/spreadsheets/' + settings.google_sheet_id

    def request(self, method, suffix='', **kwargs):
        with self.lock:
            if self.session is None:
                credentials = Credentials.from_service_account_file(
                    self.settings.path(self.settings.google_application_credentials),
                    scopes=['https://www.googleapis.com/auth/spreadsheets'])
                self.session = AuthorizedSession(credentials)
            response = self.session.request(method, self.base + suffix, timeout=20, **kwargs)
            if not response.ok:
                raise RuntimeError('Google Sheets 請求失敗：HTTP ' + str(response.status_code))
            return response.json()

    def metadata(self):
        return self.request('GET', params={'fields': 'sheets.properties,properties.title'})

    def values(self, tab, cells):
        return self.request('GET', '/values/' + quote(address(tab, cells), safe=''),
            params={'valueRenderOption': 'FORMATTED_VALUE'}).get('values', [])

    def roster_rows(self, gid):
        sheets = self.metadata()['sheets']
        matches = [s['properties'] for s in sheets if s['properties']['sheetId'] == gid]
        if len(matches) != 1:
            raise ValueError('找不到指定名冊分頁')
        tab = matches[0]
        # Bounded classroom roster; never return this data to the browser.
        return self.values(tab['title'], 'A1:' + 'Z' + str(min(tab['gridProperties']['rowCount'], 2000)))

    def init_logs(self):
        """Explicit CLI only. No startup mutations, no roster writes."""
        props = {s['properties']['title']: s['properties'] for s in self.metadata()['sheets']}
        requests = []
        next_id = max((p['sheetId'] for p in props.values()), default=0) + 1
        for tab, headers in ((TURN_TAB, TURN_HEADERS), (GAME_TAB, GAME_HEADERS)):
            if tab in props:
                if self.values(tab, 'A1:Z1') != [headers]:
                    raise ValueError('既有紀錄分頁欄位不符，停止建立：' + tab)
                continue
            sheet_id = next_id
            next_id += 1
            requests.append({'addSheet': {'properties': {'sheetId': sheet_id,
                'title': tab, 'gridProperties': {'rowCount': 1000, 'columnCount': 26, 'frozenRowCount': 1}}}})
            requests.extend([
                {'updateCells': {'start': {'sheetId': sheet_id, 'rowIndex': 0, 'columnIndex': 0},
                    'rows': [{'values': [{'userEnteredValue': {'stringValue': h}, 'userEnteredFormat': {
                        'backgroundColor': {'red': .08, 'green': .24, 'blue': .22},
                        'textFormat': {'bold': True, 'foregroundColor': {'red': 1, 'green': 1, 'blue': 1}}}} for h in headers]}],
                    'fields': 'userEnteredValue,userEnteredFormat'}},
                {'updateDimensionProperties': {'range': {'sheetId': sheet_id, 'dimension': 'COLUMNS',
                    'startIndex': 0, 'endIndex': len(headers)}, 'properties': {'pixelSize': 140}, 'fields': 'pixelSize'}}])
        if requests:
            self.request('POST', ':batchUpdate', json={'requests': requests})

    def write_rows(self, rows):
        if self.settings.roster_mode == 'google':
            return self.write_student_records(rows)
        props = {s['properties']['title']: s['properties'] for s in self.metadata()['sheets']}
        ranges, writes, grow = [], [], []
        required = {r[0] for r in rows}
        for tab, headers in ((TURN_TAB, TURN_HEADERS), (GAME_TAB, GAME_HEADERS)):
            if tab not in required:
                continue
            if tab not in props or self.values(tab, 'A1:Z1') != [headers]:
                raise ValueError('請先建立正確的紀錄分頁：' + tab)
            needed = max(r[1] for r in rows if r[0] == tab)
            count = props[tab]['gridProperties']['rowCount']
            if needed > count:
                grow.append({'appendDimension': {'sheetId': props[tab]['sheetId'], 'dimension': 'ROWS',
                    'length': max(1000, needed - count)}})
        if grow:
            self.request('POST', ':batchUpdate', json={'requests': grow})
        for tab, row, values in rows:
            ranges.append(address(tab, f'A{row}:A{row}'))
            end = chr(64 + len(values))
            writes.append({'range': address(tab, f'A{row}:{end}{row}'), 'values': [values]})
        existing = self.request('GET', '/values:batchGet', params={'ranges': ranges}).get('valueRanges', [])
        if len(existing) != len(rows):
            raise ValueError('紀錄範圍讀取不完整')
        for old, (_, _, values) in zip(existing, rows):
            cells = old.get('values', [])
            if cells and cells[0] and str(cells[0][0]) != str(values[0]):
                raise ValueError('試算表資料列已移動或資料庫版本不符，停止同步以保留既有紀錄')
        # RAW prevents formula execution, including malicious student questions.
        self.request('POST', '/values:batchUpdate', json={'valueInputOption': 'RAW', 'data': writes})

    def write_student_records(self, rows):
        """Merge UUID-keyed history into F/G, preserving earlier database histories."""
        with self.lock:
            props = next(p['properties'] for p in self.metadata()['sheets']
                         if p['properties']['sheetId'] == self.settings.google_roster_gid)
            tab = props['title']
            snapshot = self.values(tab, 'A1:G' + str(min(props['gridProperties']['rowCount'], 2000)))
            expected = ['班級', '座號', '密碼', '謎底', '謎面', '互動紀錄', '場次摘要']
            if not snapshot or [str(v).strip() for v in snapshot[0]] != expected:
                raise ValueError('名冊必須依序包含七欄：' + '、'.join(expected))
            index = {}
            for number, cells in enumerate(snapshot[1:], 2):
                if not any(str(v).strip() for v in cells):
                    continue
                student = normalize(cells[0], cells[1])
                if student in index:
                    raise ValueError('名冊學生重複，停止同步')
                index[student] = (number, cells)
            pending = {}
            for kind, _, values in rows:
                student = normalize(values[2], values[3]) if kind == TURN_TAB else normalize(values[1], values[2])
                if student not in index:
                    raise ValueError('紀錄所屬學生不在名冊，停止同步')
                number, cells = index[student]
                if student not in pending:
                    history = []
                    for col in (5, 6):
                        raw = cells[col] if len(cells) > col else ''
                        obj = json.loads(raw) if raw else {}
                        if not isinstance(obj, dict) or any(not isinstance(v, dict) for v in obj.values()):
                            raise ValueError('既有紀錄格式不符，保留原內容')
                        history.append(obj)
                    pending[student] = history
                col = 0 if kind == TURN_TAB else 1
                headers = TURN_HEADERS if col == 0 else GAME_HEADERS
                pending[student][col][str(values[0])] = dict(zip(headers, values))
            writes = []
            for student, history in pending.items():
                number, cells = index[student]
                serialized = [json.dumps(obj, ensure_ascii=False, indent=2) for obj in history]
                if any(len(value.encode('utf-16-le')) // 2 > 49000 for value in serialized):
                    raise ValueError('紀錄接近單格容量上限，資料保留於資料庫，請封存試算表紀錄')
                # Detect edits or row moves since the initial read. Teachers should not
                # sort/edit the roster during a sync; Sheets has no conditional writes.
                if self.values(tab, f'A{number}:G{number}') != [cells]:
                    raise ValueError('名冊同步期間變更，稍後重新對應')
                writes.append({'range': address(tab, f'F{number}:G{number}'), 'values': [serialized]})
            if writes:
                self.request('POST', '/values:batchUpdate', json={'valueInputOption': 'RAW', 'data': writes})


class Syncer:
    def __init__(self, store, google):
        self.store, self.google = store, google
        self.lock = threading.Lock()
        self.last_error = False

    def once(self):
        with self.lock:
            with self.store.transaction() as db:
                turns = list(db.scalars(select(Turn).where(Turn.synced == 0, Turn.status != 'processing').order_by(Turn.id).limit(100)))
                games = list(db.scalars(select(Game).where(Game.revision > Game.synced_revision).order_by(Game.id).limit(100)))
                rows = []
                for t in turns:
                    g = db.get(Game, t.game_id)
                    classroom, seat = g.student.split(':')
                    tokens = json.loads(t.usage).get('totalTokenCount', '未提供')
                    rows.append((TURN_TAB, t.id + 1, [t.request_id, local_time(t.created), classroom, seat,
                        g.activity, g.uid, g.version, t.sequence, t.question, t.question_type, t.answer, t.status, t.model, tokens]))
                for g in games:
                    classroom, seat = g.student.split(':')
                    all_turns = list(db.scalars(select(Turn).where(Turn.game_id == g.id)))
                    counts = [json.loads(t.usage).get('totalTokenCount') for t in all_turns]
                    known = sum(x for x in counts if type(x) is int)
                    total = known if all(type(x) is int for x in counts) else f'資料不完整（已知 {known}）'
                    rows.append((GAME_TAB, g.id + 1, [g.uid, classroom, seat, g.activity, g.version,
                        local_time(g.started), local_time(g.updated), len(all_turns), g.state, total, g.revision]))
                versions = [(g.id, g.revision) for g in games]
                turn_ids = [t.id for t in turns]
            if not rows:
                return
            try:
                self.google.write_rows(rows)
                with self.store.transaction() as db:
                    for tid in turn_ids:
                        db.get(Turn, tid).synced = 1
                    for gid, version in versions:
                        db.get(Game, gid).synced_revision = version
                self.last_error = False
            except Exception:
                self.last_error = True
                raise
