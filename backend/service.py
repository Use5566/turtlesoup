import hashlib
import json
import re
import secrets
import threading
import time
import uuid
from sqlalchemy import select, delete, func
from .ai import AIError, display, PAIRS
from .models import Login, Game, Turn, Limit, utcnow


MESSAGES = {'rephrase': '請改成一個可用肯定或否定回答的問題。',
            'uncertain': '目前題目資訊不足以判斷，請換個問法或請老師協助。',
            'service_error': '主持人暫時無法回應，這次問題已記錄，請稍後再提出問題。',
            'invalid_output': '主持人回答格式不符，已擋下這次回答。',
            'not_configured': '主持人尚未啟用，請通知老師。',
            'interrupted': '這次提問在處理時中斷，結果未確認，請重新提問。',
            'processing': '正在判斷你的問題…'}


class Problem(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message


class Service:
    def __init__(self, settings, store, roster, ai):
        self.settings, self.store, self.roster, self.ai = settings, store, roster, ai
        # One process/worker, serialized state changes; remote API calls happen outside this lock.
        self.lock = threading.RLock()

    def recover(self):
        with self.store.transaction() as db:
            # New roster pepper invalidates saved sessions on restart; progress remains durable.
            db.execute(delete(Login))
            for turn in db.scalars(select(Turn).where(Turn.status == 'processing')):
                turn.status = 'interrupted'
                g = db.get(Game, turn.game_id)
                g.revision += 1
                g.updated = utcnow()

    def limit(self, key, cap, window):
        with self.lock, self.store.transaction() as db:
            now = time.time()
            db.execute(delete(Limit).where(Limit.until < now - window))
            row = db.get(Limit, key)
            if row is None:
                db.add(Limit(key=key, until=now + window, count=1))
            elif row.until <= now:
                row.until, row.count = now + window, 1
            elif row.count >= cap:
                raise Problem(429, '操作太頻繁，請稍後再試。')
            else:
                row.count += 1

    @staticmethod
    def token_hash(token):
        return hashlib.sha256(token.encode()).hexdigest()

    def login(self, student, password):
        self.limit('login:' + student, 8, 300)
        if not self.roster.verify(student, password):
            raise Problem(401, '班級、座號或密碼不正確。')
        token = secrets.token_urlsafe(32)
        with self.lock, self.store.transaction() as db:
            db.execute(delete(Login).where((Login.student == student) | (Login.expires < time.time())))
            db.add(Login(digest=self.token_hash(token), student=student,
                fingerprint=self.roster.fingerprint(student), expires=time.time() + self.settings.session_seconds))
        return token

    def authenticate(self, token):
        if not token or len(token) > 100:
            raise Problem(401, '請先登入。')
        with self.store.transaction() as db:
            login = db.get(Login, self.token_hash(token))
            if not login or login.expires <= time.time():
                raise Problem(401, '登入已過期，請重新登入。')
            if self.roster.fingerprint(login.student) != login.fingerprint:
                raise Problem(401, '身分資料已更新，請重新登入。')
            return login.student

    def logout(self, token):
        with self.lock, self.store.transaction() as db:
            db.execute(delete(Login).where(Login.digest == self.token_hash(token)))

    def puzzles(self):
        try:
            path = self.settings.path(self.settings.puzzles_path)
            text = path.read_text(encoding='utf-8-sig')
            if path.suffix.lower() == '.txt':
                # A plain TXT is a visible reading passage and the judging reference.
                # Never invent a hidden solution that the teacher did not provide.
                surface = text.strip()
                data = [{'id': 'txt-' + hashlib.sha256(path.name.encode()).hexdigest()[:12],
                         'version': '1', 'title': path.stem, 'surface': surface,
                         'solution': surface, 'facts': [], 'max_turns': 30}]
            else:
                data = json.loads(text)
            if not isinstance(data, list) or not data:
                raise ValueError()
            ids = set()
            for p in data:
                for key in ('id', 'version', 'title', 'surface', 'solution'):
                    if not isinstance(p.get(key), str) or not p[key].strip():
                        raise ValueError()
                if p['id'] in ids or not 1 <= p.get('max_turns', 30) <= 100:
                    raise ValueError()
                ids.add(p['id'])
                # Bind progress to the exact private story, even if author forgets to bump version.
                p['revision_key'] = p['version'] + '-' + hashlib.sha256(json.dumps(
                    {k: p.get(k) for k in ('surface', 'solution', 'facts')}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]
            return data
        except Exception:
            raise Problem(503, '活動題目尚未準備完成，請通知老師。') from None

    def activities(self):
        return [{'id': p['id'], 'title': p['title'], 'version': p['revision_key']} for p in self.puzzles() if p.get('enabled', True)]

    def start(self, student, activity):
        puzzle = next((p for p in self.puzzles() if p['id'] == activity and p.get('enabled', True)), None)
        if not puzzle:
            raise Problem(404, '活動尚未開放。')
        with self.lock, self.store.transaction() as db:
            game = db.scalar(select(Game).where(Game.student == student, Game.activity == activity, Game.version == puzzle['revision_key']))
            if not game:
                game = Game(uid=str(uuid.uuid4()), student=student, activity=activity, version=puzzle['revision_key'],
                    puzzle=json.dumps(puzzle, ensure_ascii=False))
                db.add(game)
                db.flush()
            uid = game.uid
        return self.game(student, uid)

    def owned(self, db, student, uid):
        game = db.scalar(select(Game).where(Game.uid == uid, Game.student == student))
        if not game:
            raise Problem(404, '找不到此場次。')
        return game

    def turn_json(self, t):
        return {'request_id': t.request_id, 'sequence': t.sequence, 'question': t.question,
            'question_type': t.question_type, 'status': t.status, 'answer': t.answer,
            'message': MESSAGES.get(t.status, ''), 'created': t.created,
            'sync': 'synced' if t.synced else ('pending' if self.settings.sheets_sync_enabled else 'local')}

    def game(self, student, uid):
        with self.store.transaction() as db:
            g = self.owned(db, student, uid)
            p = json.loads(g.puzzle)
            turns = list(db.scalars(select(Turn).where(Turn.game_id == g.id).order_by(Turn.sequence)))
            return {'id': g.uid, 'activity': g.activity, 'title': p['title'], 'surface': p['surface'],
                'state': g.state, 'max_turns': p.get('max_turns', 30), 'turns': [self.turn_json(t) for t in turns],
                'sync': 'synced' if g.synced_revision == g.revision else ('pending' if self.settings.sheets_sync_enabled else 'local'),
                'mock_examples': p.get('mock_examples', []) if self.settings.ai_mode == 'mock' else []}

    def ask(self, student, uid, request_id, question, kind):
        if kind not in PAIRS or not question.strip() or len(question) > 300:
            raise Problem(422, '請輸入 1–300 字的問題並選擇問句類型。')
        question = question.strip()
        with self.lock, self.store.transaction() as db:
            g = self.owned(db, student, uid)
            old = db.scalar(select(Turn).where(Turn.request_id == request_id))
            if old:
                if old.game_id != g.id or old.question != question or old.question_type != kind:
                    raise Problem(409, '提問編號已使用，請重新整理。')
                return self.turn_json(old)
            if g.state != 'active':
                raise Problem(409, '這個場次已結束。')
            if not any(p['id'] == g.activity and p['revision_key'] == g.version and p.get('enabled', True) for p in self.puzzles()):
                raise Problem(409, '活動已關閉或題目已更新，請返回活動列表。')
            previous = list(db.scalars(select(Turn).where(Turn.game_id == g.id).order_by(Turn.sequence)))
            if any(t.status == 'processing' for t in previous):
                raise Problem(409, '上一個問題仍在處理，請稍候。')
            puzzle = json.loads(g.puzzle)
            if len(previous) >= puzzle.get('max_turns', 30):
                raise Problem(409, '已達本場次提問上限。')
            history = [{'question': t.question, 'answer': t.answer} for t in previous if t.answer]
        self.limit('ask:' + student, 20, 300)
        # Re-check under the lock after consuming rate quota.
        with self.lock, self.store.transaction() as db:
            g = self.owned(db, student, uid)
            old = db.scalar(select(Turn).where(Turn.request_id == request_id))
            if old:
                if old.game_id != g.id or old.question != question or old.question_type != kind:
                    raise Problem(409, '提問編號已使用。')
                return self.turn_json(old)
            if g.state != 'active' or db.scalar(select(Turn.id).where(Turn.game_id == g.id, Turn.status == 'processing')):
                raise Problem(409, '場次狀態已變更，請重新整理。')
            count = db.scalar(select(func.count()).select_from(Turn).where(Turn.game_id == g.id))
            if count >= puzzle.get('max_turns', 30):
                raise Problem(409, '已達本場次提問上限。')
            turn = Turn(request_id=request_id, game_id=g.id, sequence=count + 1, question=question,
                question_type=kind, model='local-mock' if self.settings.ai_mode == 'mock' else self.settings.gemini_model)
            db.add(turn)
            db.flush()
            tid = turn.id
            g.revision += 1
            g.updated = utcnow()
        try:
            result = self.ai.judge(puzzle, question, kind, history)
            answer, usage = display(result.decision, kind), result.usage
            status = 'answered' if answer else result.decision
        except AIError as error:
            status, answer, usage = error.code, '', error.usage
        except Exception:
            status, answer, usage = 'service_error', '', {}
        with self.lock, self.store.transaction() as db:
            turn = db.get(Turn, tid)
            turn.status, turn.answer, turn.usage = status, answer, json.dumps(usage)
            g = db.get(Game, turn.game_id)
            g.updated, g.revision = utcnow(), g.revision + 1
            return self.turn_json(turn)

    def finish(self, student, uid):
        with self.lock, self.store.transaction() as db:
            g = self.owned(db, student, uid)
            if db.scalar(select(Turn.id).where(Turn.game_id == g.id, Turn.status == 'processing')):
                raise Problem(409, '請等目前問題處理完成。')
            if g.state != 'finished':
                g.state, g.updated, g.revision = 'finished', utcnow(), g.revision + 1
        return self.game(student, uid)
