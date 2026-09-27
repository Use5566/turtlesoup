import asyncio
from contextlib import asynccontextmanager
import threading
from uuid import UUID
from fastapi import FastAPI, Request, Depends
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ConfigDict
from .config import Settings, ROOT
from .models import Store
from .roster import Roster, Unavailable, normalize
from .ai import Gemini, MockAI
from .service import Service, Problem
from .sheets import GoogleSheets, Syncer
from .sheet_state import restore


class LoginInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    classroom: str = Field(pattern=r'^[0-9]{3}$')
    seat: str = Field(pattern=r'^[0-9]{1,2}$')
    password: str = Field(pattern=r'^[0-9]{5}$')


class StartInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    activity: str = Field(min_length=1, max_length=80)


class QuestionInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID
    question: str = Field(min_length=1, max_length=300)
    question_type: str = Field(pattern=r'^(is|correct|will|has|may|can)$')


class DraftInput(BaseModel):
    question: str = Field(max_length=300)
    question_type: str = Field(pattern=r'^(is|correct|will|has|may|can)$')


def create_app(settings=None, roster=None, ai=None, google=None):
    settings = settings or Settings.from_env()
    settings.validate()
    store = Store(settings)
    google = google or GoogleSheets(settings)
    roster = roster or Roster(settings, google)
    ai = ai or (MockAI() if settings.ai_mode == 'mock' else Gemini(settings))
    service = Service(settings, store, roster, ai)
    syncer = Syncer(store, google)
    stop = threading.Event()

    def checkpoint():
        if settings.sheet_storage:
            try:
                syncer.once()
            except Exception:
                raise Problem(503, '尚未儲存至試算表，請保留頁面並稍後重試。') from None

    service.checkpoint = checkpoint

    def sync_loop():
        while not stop.wait(settings.sync_seconds):
            try:
                syncer.once()
            except Exception:
                # Do not log raw provider responses, credentials, or student questions.
                print('試算表同步尚未成功，紀錄保留於資料庫，稍後重試。', flush=True)

    @asynccontextmanager
    async def lifespan(app):
        if settings.sheet_storage:
            await asyncio.to_thread(restore, store, google)
        service.recover()
        await asyncio.to_thread(checkpoint)
        worker = None
        if settings.sheets_sync_enabled:
            worker = threading.Thread(target=sync_loop, daemon=True)
            worker.start()
        yield
        stop.set()
        if worker:
            await asyncio.to_thread(worker.join, 25)
        if settings.sheet_storage:
            try:
                await asyncio.to_thread(checkpoint)
            except Problem:
                pass
        store.engine.dispose()

    app = FastAPI(title='turtlesoup', docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.service, app.state.syncer = service, syncer
    app.add_middleware(CORSMiddleware,
        allow_origins=[s.strip() for s in settings.allowed_origins.split(',') if s.strip()],
        allow_credentials=False, allow_methods=['GET', 'POST'], allow_headers=['Authorization', 'Content-Type'])

    @app.middleware('http')
    async def protect(request, call_next):
        if request.method == 'POST':
            data = bytearray()
            async for part in request.stream():
                data.extend(part)
                if len(data) > 4096:
                    return JSONResponse({'message': '送出的資料太長。'}, status_code=413)
            request._body = bytes(data)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        return response

    @app.exception_handler(Problem)
    async def problem(request, exc):
        return JSONResponse({'message': exc.message}, status_code=exc.code)

    @app.exception_handler(Unavailable)
    async def unavailable(request, exc):
        return JSONResponse({'message': str(exc)}, status_code=503)

    @app.exception_handler(RequestValidationError)
    async def validation(request, exc):
        # Default FastAPI validation echoes input; never echo passwords.
        return JSONResponse({'message': '輸入格式不正確，請檢查後再試。'}, status_code=422)

    def token(request):
        auth = request.headers.get('Authorization', '')
        return auth[7:] if auth.startswith('Bearer ') else ''

    def student(request: Request):
        return service.authenticate(token(request))

    @app.get('/healthz')
    def health():
        return {'status': 'ok'}

    @app.get('/api/config')
    def config():
        return {'mode': settings.ai_mode, 'classes': roster.classes(),
                'sheets_enabled': settings.sheets_sync_enabled}

    @app.post('/api/login')
    def login(body: LoginInput, request: Request):
        # Use actual peer address, not spoofable forwarding headers.
        service.limit('ip:' + (request.client.host if request.client else 'unknown'), 300, 300)
        try:
            sid = normalize(body.classroom, body.seat)
        except ValueError:
            raise Problem(401, '班級、座號或密碼不正確。') from None
        return {'token': service.login(sid, body.password), 'classroom': sid.split(':')[0], 'seat': sid.split(':')[1]}

    @app.post('/api/logout')
    def logout(request: Request):
        checkpoint()
        service.logout(token(request))
        return {'ok': True}

    @app.get('/api/session')
    def session(sid=Depends(student)):
        return {'classroom': sid.split(':')[0], 'seat': sid.split(':')[1]}

    @app.get('/api/activities')
    def activities(sid=Depends(student)):
        return {'activities': service.activities(sid)}

    @app.post('/api/games')
    def start(body: StartInput, sid=Depends(student)):
        result = service.start(sid, body.activity)
        checkpoint()
        return service.game(sid, result['id'])

    @app.get('/api/games/{uid}')
    def game(uid: UUID, sid=Depends(student)):
        return service.game(sid, str(uid))

    @app.post('/api/games/{uid}/questions')
    def ask(uid: UUID, body: QuestionInput, sid=Depends(student)):
        result = service.ask(sid, str(uid), str(body.request_id), body.question, body.question_type)
        checkpoint()
        return result

    @app.post('/api/games/{uid}/save')
    def save(uid: UUID, body: DraftInput, sid=Depends(student)):
        service.save_draft(sid, str(uid), body.question, body.question_type)
        checkpoint()
        return service.game(sid, str(uid))

    @app.post('/api/games/{uid}/finish')
    def finish(uid: UUID, sid=Depends(student)):
        service.finish(sid, str(uid))
        checkpoint()
        return service.game(sid, str(uid))

    if settings.app_mode == 'local':
        app.mount('/', StaticFiles(directory=ROOT / 'web', html=True), name='web')
    return app
