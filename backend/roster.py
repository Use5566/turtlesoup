import hashlib
import hmac
import json
import re
import secrets
import threading
import time


class Unavailable(Exception):
    pass


def normalize(classroom, seat):
    classroom, seat = str(classroom).strip(), str(seat).strip()
    if not re.fullmatch(r'[0-9]{1,3}', classroom) or not re.fullmatch(r'[0-9]{1,2}', seat) or not 1 <= int(seat) <= 99:
        raise ValueError('班級或座號格式不正確')
    return classroom + ':' + seat.zfill(2)


class Roster:
    def __init__(self, settings, google=None):
        self.settings, self.google = settings, google
        self.lock = threading.RLock()
        self.pepper = secrets.token_bytes(32)
        self.cache, self.loaded = {}, 0
        self.retry_after = 0
        self.assignments = None

    def digest(self, student, password):
        return hmac.new(self.pepper, f'{student}:{password}'.encode(), hashlib.sha256).hexdigest()

    def read_rows(self):
        if self.settings.roster_mode == 'google':
            return self.google.roster_rows(self.settings.google_roster_gid)
        data = json.loads(self.settings.path(self.settings.roster_path).read_text(encoding='utf-8-sig'))
        return [['班級', '座號', '密碼']] + [[x['classroom'], x['seat'], x['password']] for x in data]

    def refresh(self):
        with self.lock:
            now = time.monotonic()
            if now < self.retry_after:
                # Fail closed: cached permissions may have been revoked. Avoid
                # every student's poll immediately retrying a failed Google read.
                raise Unavailable('目前無法核對名冊，請稍後再試或通知老師。')
            if now - self.loaded < 30:
                return
            try:
                rows = self.read_rows()
                header = [str(x).strip() for x in rows[0]]
                indices = [header.index(x) for x in ('班級', '座號', '密碼')]
                parsed = {}
                multi = [key for key in ('謎面1', '謎面2') if key in header]
                assignments = {} if '謎面' in header or multi else None
                for row in rows[1:]:
                    if not any(str(x).strip() for x in row):
                        continue
                    classroom, seat, password = [str(row[i]).strip() for i in indices]
                    student = normalize(classroom, seat)
                    if not re.fullmatch(r'[0-9]{5}', password) or student in parsed:
                        raise ValueError('名冊格式錯誤或重複')
                    parsed[student] = self.digest(student, password)
                    if assignments is not None:
                        if multi:
                            assignments[student] = list(dict.fromkeys(
                                (str(row[header.index(key)]).strip(), None) for key in multi
                                if len(row) > header.index(key) and str(row[header.index(key)]).strip()))
                        elif '謎底' in header:
                            assignments[student] = tuple(str(row[header.index(key)]).strip()
                                if len(row) > header.index(key) else '' for key in ('謎底', '謎面'))
                        else:
                            i = header.index('謎面')
                            assignments[student] = (str(row[i]).strip() if len(row) > i else '', None)
                self.cache, self.loaded = parsed, time.monotonic()
                self.assignments = assignments
                self.retry_after = 0
            except Exception:
                self.retry_after = time.monotonic() + 30
                raise Unavailable('目前無法核對名冊，請稍後再試或通知老師。') from None

    def verify(self, student, password):
        self.refresh()
        expected = self.cache.get(student, '0' * 64)
        return hmac.compare_digest(expected, self.digest(student, password))

    def fingerprint(self, student):
        self.refresh()
        return self.cache.get(student)

    def classes(self):
        self.refresh()
        return sorted({x.split(':')[0] for x in self.cache})

    def assignment(self, student):
        self.refresh()
        return None if self.assignments is None else self.assignments.get(student, ('', ''))
