"""Synthetic classroom load and abrupt-exit durability; no external services."""
import json
import subprocess
import sys
import uuid
from pathlib import Path

from sqlalchemy import func, select

from backend.config import Settings
from backend.core_records import HEADERS, activity_id
from backend.models import Game, Store, Turn
from backend.sheet_state import restore
from backend.sheets import Syncer
from test_core_records import CoreSheet, literal


def classroom_store(settings, tmp_path):
    settings.sheet_storage = settings.sheets_sync_enabled = settings.core_records = True
    settings.roster_mode = 'google'
    settings.first_puzzle_only = True
    settings.puzzles_path = str(tmp_path / 'alpha.txt')
    Path(settings.puzzles_path).write_text('【謎面】測試故事。\n【湯底】測試答案。', encoding='utf-8')
    google = CoreSheet(settings)
    # Thirty synthetic accounts across two classes, respecting seats 1–29.
    students = [('1' if n <= 29 else '2', str(n if n <= 29 else 1)) for n in range(1, 31)]
    google.table = [[literal(v) for v in HEADERS]] + [
        [literal(v) for v in [group, seat, '01234', 'alpha', '']]
        for group, seat in students]
    google.write_student_records([], True)
    store = Store(settings)
    with store.transaction() as db:
        for group, seat in students:
            game = Game(uid=str(uuid.uuid4()), student=f'{group}:{int(seat):02}',
                        activity=activity_id('alpha'), version='test-v1', revision=21,
                        state='finished', puzzle=json.dumps({'title': '測試', 'surface': '故事',
                                                            'solution': '答案', 'max_turns': 20}))
            db.add(game)
            db.flush()
            for number in range(1, 21):
                db.add(Turn(request_id=str(uuid.uuid4()), game_id=game.id, sequence=number,
                            question=f'第 {number} 個測試問題是不是成立？', question_type='is',
                            status='answered', answer='是', model='synthetic',
                            usage='{"totalTokenCount":17}'))
    return store, google


def test_thirty_students_six_hundred_turns_share_one_batch_and_restore(settings, tmp_path):
    store, google = classroom_store(settings, tmp_path)
    before = google.writes
    syncer = Syncer(store, google)
    syncer.once()
    assert google.writes - before == 1
    assert len(google.hidden) == 31
    with store.transaction() as db:
        assert db.scalar(select(func.count()).select_from(Turn).where(Turn.synced == 0)) == 0
        assert db.scalar(select(func.count()).select_from(Game).where(Game.revision > Game.synced_revision)) == 0
    total_tokens = 0
    for row in google.hidden[1:]:
        ledger = json.loads(row[1]['formattedValue'])
        games = json.loads(row[2]['formattedValue'])
        assert len(ledger) == 20 and len(games) == 1
        saved = next(iter(games.values()))['_restore']['turns']
        assert {t['request_id'] for t in saved} == set(ledger)
        assert all(t['answer'] == '是' for t in saved)
        total_tokens += sum(t['總tokens'] for t in ledger.values())
    assert total_tokens == 600 * 17
    for row in google.table[1:]:
        assert row[6]['formattedValue'].count('學生：') == 20
        assert row[10]['userEnteredValue'] == {'numberValue': 340}
        assert '_restore' not in row[6]['formattedValue']
    syncer.once()
    assert google.writes - before == 1  # No changes means no remote write.
    store.engine.dispose()

    # The durable file itself retains every record after reopening.
    reopened = Store(settings)
    with reopened.transaction() as db:
        assert db.scalar(select(func.count()).select_from(Game)) == 30
        assert db.scalar(select(func.count()).select_from(Turn)) == 600
    reopened.engine.dispose()

    # The cloud snapshot can also bootstrap a replacement empty disk.
    recovery_settings = Settings(database_url='sqlite:///' + str(tmp_path / 'recovered.sqlite'))
    recovered = Store(recovery_settings)
    restore(recovered, google, 'synthetic-bootstrap')
    assert recovered.initialized('synthetic-bootstrap')
    with recovered.transaction() as db:
        assert db.scalar(select(func.count()).select_from(Game)) == 30
        assert db.scalar(select(func.count()).select_from(Turn)) == 600
        assert sum(json.loads(t.usage)['totalTokenCount'] for t in db.scalars(select(Turn))) == 10200
    recovered.engine.dispose()


def test_stale_cloud_restore_cannot_replace_newer_pending_disk_records(settings, tmp_path):
    store, google = classroom_store(settings, tmp_path)
    Syncer(store, google).once()
    with store.transaction() as db:
        game = db.scalar(select(Game).order_by(Game.id))
        uid = game.uid
        game.draft = '尚未同步的新草稿'
        game.revision += 1
        turn = db.scalar(select(Turn).where(Turn.game_id == game.id).order_by(Turn.id))
        turn.answer = '不是'
        turn.usage = '{"totalTokenCount":29}'
        turn.synced = 0
    store.engine.dispose()
    store = Store(settings)
    restore(store, google, 'stale-import')
    with store.transaction() as db:
        game = db.scalar(select(Game).where(Game.uid == uid))
        assert game.draft == '尚未同步的新草稿'
        assert game.revision > game.synced_revision
        turn = db.scalar(select(Turn).where(Turn.game_id == game.id).order_by(Turn.id))
        assert turn.answer == '不是' and json.loads(turn.usage)['totalTokenCount'] == 29
        assert turn.synced == 0
        assert db.scalar(select(func.count()).select_from(Game)) == 30
        assert db.scalar(select(func.count()).select_from(Turn)) == 600
    store.engine.dispose()


def test_abrupt_process_exit_keeps_committed_answer_but_rolls_back_uncommitted_turn(tmp_path):
    filename = tmp_path / 'crash.sqlite'
    script = r'''
import os, sys
from backend.config import Settings
from backend.models import Store, Game, Turn
store = Store(Settings(database_url='sqlite:///' + sys.argv[1]))
with store.transaction() as db:
    game = Game(uid='committed-game', student='1:01', activity='test', version='1',
                puzzle='{}', revision=3, draft='durable draft')
    db.add(game); db.flush(); gid = game.id
    db.add(Turn(request_id='committed-turn', game_id=gid, sequence=1, question='saved question',
                question_type='is', status='answered', answer='yes', model='synthetic',
                usage='{"totalTokenCount":17}'))
with store.transaction() as db:
    db.add(Turn(request_id='uncommitted-turn', game_id=gid, sequence=2, question='unfinished',
                question_type='is', status='processing', model='synthetic'))
    db.flush()
    os._exit(73)
'''
    result = subprocess.run([sys.executable, '-c', script, str(filename)],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, timeout=30)
    assert result.returncode == 73, result.stderr.decode('utf-8', errors='replace')
    store = Store(Settings(database_url='sqlite:///' + str(filename)))
    with store.engine.connect() as conn:
        assert conn.exec_driver_sql('PRAGMA integrity_check').scalar() == 'ok'
    with store.transaction() as db:
        assert db.scalar(select(func.count()).select_from(Turn)) == 1
        turn = db.scalar(select(Turn))
        assert turn.request_id == 'committed-turn' and turn.answer == 'yes'
        assert turn.synced == 0 and json.loads(turn.usage)['totalTokenCount'] == 17
        assert db.scalar(select(Game)).draft == 'durable draft'
    store.engine.dispose()
