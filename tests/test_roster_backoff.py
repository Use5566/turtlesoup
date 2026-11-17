import pytest

from backend.roster import Roster, Unavailable


class FakeGoogle:
    def __init__(self):
        self.calls = 0
        self.fail = False
        self.password = '12345'

    def roster_rows(self, gid):
        self.calls += 1
        if self.fail:
            raise OSError('provider error must not reach the student')
        return [['班級', '座號', '密碼', '謎面1'], ['1', '1', self.password, 'alpha']]


@pytest.fixture
def clock(monkeypatch):
    now = [100.0]
    monkeypatch.setattr('backend.roster.time.monotonic', lambda: now[0])
    return now


def test_failed_roster_read_throttles_thirty_students_for_thirty_seconds(settings, clock):
    settings.roster_mode = 'google'
    google = FakeGoogle()
    google.fail = True
    roster = Roster(settings, google)
    for second in range(30):
        clock[0] = 100 + second
        for number in range(1, 31):
            with pytest.raises(Unavailable, match='無法核對名冊') as error:
                roster.verify(f'1:{number:02}', '12345')
            assert 'provider error' not in str(error.value)
    assert google.calls == 1
    clock[0] = 130
    with pytest.raises(Unavailable):
        roster.classes()
    assert google.calls == 2


def test_roster_failure_never_uses_expired_permissions_and_recovery_resets(settings, clock):
    settings.roster_mode = 'google'
    google = FakeGoogle()
    roster = Roster(settings, google)
    assert roster.verify('1:01', '12345')
    old_fingerprint = roster.fingerprint('1:01')
    clock[0] = 130
    google.fail = True
    for operation in [lambda: roster.verify('1:01', '12345'),
                      lambda: roster.fingerprint('1:01'),
                      lambda: roster.assignment('1:01'), roster.classes]:
        with pytest.raises(Unavailable):
            operation()
    assert google.calls == 2
    google.fail = False
    google.password = '54321'
    clock[0] = 159.9
    with pytest.raises(Unavailable):
        roster.verify('1:01', '12345')
    assert google.calls == 2
    clock[0] = 160
    assert not roster.verify('1:01', '12345')
    assert roster.verify('1:01', '54321')
    assert roster.fingerprint('1:01') != old_fingerprint
    assert roster.retry_after == 0
    assert google.calls == 3


def test_successful_roster_cache_still_refreshes_every_thirty_seconds(settings, clock):
    settings.roster_mode = 'google'
    google = FakeGoogle()
    roster = Roster(settings, google)
    for second in range(30):
        clock[0] = 100 + second
        assert roster.verify('1:01', '12345')
        assert roster.classes() == ['1']
    assert google.calls == 1
    clock[0] = 130
    assert roster.verify('1:01', '12345')
    assert google.calls == 2
