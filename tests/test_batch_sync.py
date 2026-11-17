"""Batch scheduling and synchronization races; no Google network calls."""
import threading
from types import SimpleNamespace

from sqlalchemy import select

from backend.models import Game, Turn
from backend.sheets import Syncer, GAME_TAB, TURN_TAB
from backend.sync_worker import SyncWorker
from conftest import login, start
from test_app import ask


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class Recorder:
    def __init__(self):
        self.calls = 0
        self.offline = False

    def once(self):
        self.calls += 1
        if self.offline:
            raise OSError('private provider response must not reach logs')


def test_three_second_schedule_coalesces_ticks():
    clock, syncer = Clock(), Recorder()
    worker = SyncWorker(syncer, interval=3, clock=clock, jitter=lambda: 0)
    worker.tick()
    clock.now = 2.99
    worker.tick()
    assert syncer.calls == 0
    clock.now = 3
    for _ in range(30):
        worker.tick()
    assert syncer.calls == 1
    clock.now = 5.99
    worker.tick()
    assert syncer.calls == 1
    clock.now = 6
    worker.tick()
    assert syncer.calls == 2


def test_delayed_worker_does_not_replay_missed_intervals():
    clock, syncer = Clock(), Recorder()
    worker = SyncWorker(syncer, interval=3, clock=clock, jitter=lambda: 0)
    clock.now = 100
    for _ in range(30):
        worker.tick()
    assert syncer.calls == 1
    clock.now = 103
    worker.tick()
    assert syncer.calls == 2


def test_backoff_resets_after_success_and_hides_provider_details(capsys, caplog):
    clock, syncer = Clock(), Recorder()
    syncer.offline = True
    worker = SyncWorker(syncer, interval=3, clock=clock, jitter=lambda: 0)
    clock.now = 3
    worker.tick()
    assert syncer.calls == 1
    clock.now = 8.99
    worker.tick()
    assert syncer.calls == 1
    clock.now = 9
    worker.tick()
    assert syncer.calls == 2
    clock.now = 20.99
    worker.tick()
    assert syncer.calls == 2
    syncer.offline = False
    clock.now = 21
    worker.tick()
    assert syncer.calls == 3
    syncer.offline = True
    clock.now = 24
    worker.tick()
    clock.now = 29.99
    worker.tick()
    assert syncer.calls == 4
    clock.now = 30
    worker.tick()
    assert syncer.calls == 5
    captured = capsys.readouterr()
    assert 'private provider response' not in captured.out + captured.err + caplog.text


def test_backoff_caps_delay_and_adds_jitter():
    clock, syncer = Clock(), Recorder()
    syncer.offline = True
    worker = SyncWorker(syncer, interval=3, clock=clock, jitter=lambda: .5)
    for delay in (6.5, 12.5, 24.5, 48.5, 60.5, 60.5, 60.5):
        clock.now = worker.next_due
        worker.tick()
        assert worker.next_due == clock.now + delay


def test_inflight_ticks_never_start_a_second_batch():
    entered, release = threading.Event(), threading.Event()
    clock, syncer = Clock(), Recorder()

    def blocking_once():
        syncer.calls += 1
        entered.set()
        assert release.wait(5)

    syncer.once = blocking_once
    worker = SyncWorker(syncer, interval=3, clock=clock, jitter=lambda: 0)
    clock.now = 3
    first = threading.Thread(target=worker.tick)
    first.start()
    try:
        assert entered.wait(2)
        clock.now = 30  # Even missed intervals must not launch overlapping work.
        second = threading.Thread(target=worker.tick)
        second.start()
        second.join(2)
        assert not second.is_alive()
        assert syncer.calls == 1
    finally:
        release.set()
        first.join(2)
    assert not first.is_alive()
    assert worker.next_due == 33
    worker.tick()
    assert syncer.calls == 1


def test_answer_arriving_during_sheet_write_remains_pending(client):
    """A snapshot of processing must not acknowledge a later completed answer."""
    headers = login(client)
    gid = start(client, headers)
    assert ask(client, headers, gid).status_code == 200
    store = client.app.state.service.store
    with store.transaction() as db:
        turn = db.scalar(select(Turn))
        turn.status, turn.answer, turn.usage, turn.synced = 'processing', '', '{}', 0
        game = db.scalar(select(Game))
        game.synced_revision = 0
    writes = []

    def write_rows(rows):
        writes.append(rows)
        if len(writes) == 1:
            with store.transaction() as db:
                turn = db.scalar(select(Turn))
                turn.status, turn.answer, turn.usage = 'answered', '是', '{"totalTokenCount":17}'
                db.scalar(select(Game)).revision += 1

    remote = SimpleNamespace(settings=SimpleNamespace(sheet_storage=True), write_rows=write_rows)
    syncer = Syncer(store, remote)
    syncer.once()
    with store.transaction() as db:
        game = db.scalar(select(Game))
        assert game.synced_revision < game.revision
        assert db.scalar(select(Turn)).synced == 0
    first_snapshot = next(values[-1] for tab, _, values in writes[0] if tab == GAME_TAB)
    assert first_snapshot['turns'][0]['status'] == 'processing'
    syncer.once()
    assert any(tab == TURN_TAB for tab, _, _ in writes[1])
    final_snapshot = next(values[-1] for tab, _, values in writes[1] if tab == GAME_TAB)
    assert final_snapshot['turns'][0]['answer'] == '是'
    with store.transaction() as db:
        game = db.scalar(select(Game))
        assert game.synced_revision == game.revision
        assert db.scalar(select(Turn)).synced == 1
