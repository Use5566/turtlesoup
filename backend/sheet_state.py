"""Durable game snapshots in roster G; local SQL is only a runtime cache."""
import json
from datetime import datetime, timezone, timedelta
from .models import Game, Turn
from .roster import normalize
from .puzzle_files import resolve_puzzle

GAME_FIELDS = ('uid', 'student', 'activity', 'version', 'puzzle', 'state', 'started',
               'updated', 'revision', 'draft', 'draft_kind')
TURN_FIELDS = ('request_id', 'sequence', 'question', 'question_type', 'status',
               'answer', 'model', 'usage', 'created')


def snapshot(game, turns):
    return {'schema': 1, 'game': {k: getattr(game, k) for k in GAME_FIELDS},
            'turns': [{k: getattr(t, k) for k in TURN_FIELDS} for t in turns]}


def restore(store, google):
    rows = google.recovery_rows()
    if not rows or [str(v).strip() for v in rows[0]][:7] != [
            '班級', '座號', '密碼', '謎底', '謎面', '互動紀錄', '場次摘要']:
        raise ValueError('試算表七欄格式不正確，無法恢復場次')
    with store.transaction() as db:
        for row in rows[1:]:
            if len(row) < 7 or not row[6]:
                continue
            student = normalize(row[0], row[1])
            records = json.loads(row[6])
            if not isinstance(records, dict):
                raise ValueError('場次摘要格式不正確')
            for uid, record in records.items():
                data = record.get('_restore')
                if data is None:
                    # Migrate the previous F/G summary format without deleting
                    # its history. Changed puzzle versions remain read-only.
                    if record.get('場次編號') != uid:
                        raise ValueError('既有場次摘要缺少恢復欄位')
                    answer = str(row[3]).strip()
                    if not answer or any(c in answer for c in '/\\:'):
                        raise ValueError('既有題目資料無法恢復')
                    path = resolve_puzzle(google.settings.path(google.settings.puzzles_path).parent, answer)
                    puzzle = {'title': '海龜湯挑戰', 'surface': row[4],
                              'solution': path.read_text(encoding='utf-8-sig').strip(), 'max_turns': 30}
                    def iso(value):
                        return datetime.fromisoformat(value).replace(
                            tzinfo=timezone(timedelta(hours=8))).isoformat()
                    turns = []
                    for old in json.loads(row[5] or '{}').values():
                        if old.get('場次編號') != uid:
                            continue
                        turns.append(dict(zip(TURN_FIELDS, [old['請求編號'], old['提問序號'],
                            old['學生問題'], old['問句類型'], old['處理狀態'], old['AI回答'], old['模型'],
                            json.dumps({'totalTokenCount': old['總tokens']} if type(old['總tokens']) is int else {}),
                            iso(old['紀錄時間'])])))
                    data = {'schema': 1, 'game': dict(zip(GAME_FIELDS, [uid, student,
                        record['活動編號'], record['題目版本'], json.dumps(puzzle, ensure_ascii=False),
                        record['場次狀態'], iso(record['開始時間']), iso(record['最後互動時間']),
                        record['資料版本'], '', 'is'])), 'turns': turns}
                if data['schema'] != 1 or data['game']['student'] != student or data['game']['uid'] != uid:
                    raise ValueError('場次恢復資料與學生不符')
                game = Game(**{k: data['game'][k] for k in GAME_FIELDS})
                game.synced_revision = game.revision
                db.add(game)
                db.flush()
                for saved in data['turns']:
                    db.add(Turn(game_id=game.id, synced=1,
                                **{k: saved[k] for k in TURN_FIELDS}))
