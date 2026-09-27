import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Settings:
    app_mode: str = 'local'
    database_url: str = 'sqlite:///private/turtlesoup.db'
    roster_mode: str = 'file'
    roster_path: str = 'private/roster.json'
    puzzles_path: str = 'private/puzzles.json'
    ai_mode: str = 'mock'
    gemini_model: str = 'gemini-3.5-flash-lite'
    gemini_api_key: str = ''
    gemini_temperature: float = 0.0
    gemini_max_output_tokens: int = 1024
    google_sheet_id: str = '1CdLxYuVMC_YJ0hSRWoieaklwLJEdZHsi7MHVq-xyyOU'
    google_roster_gid: int = 0
    google_application_credentials: str = ''
    sheets_sync_enabled: bool = False
    allowed_origins: str = 'http://127.0.0.1:8765,http://localhost:8765'
    session_seconds: int = 7200
    sync_seconds: int = 30
    sheet_storage: bool = False

    @classmethod
    def from_env(cls):
        if os.environ.get('RENDER', '').strip().lower() == 'true':
            # Render supplies RENDER=true. Classroom deployment has one fixed
            # profile; legacy mock/sync switches must not override it.
            required = ('GEMINI_API_KEY', 'GOOGLE_APPLICATION_CREDENTIALS')
            missing = [name for name in required if not os.environ.get(name, '').strip()]
            if missing:
                raise ValueError('Render 缺少必要設定：' + '、'.join(missing))
            settings = cls(
                app_mode='production', ai_mode='gemini', roster_mode='google',
                sheets_sync_enabled=True, puzzles_path='歐氏尖吻鮫.txt',
                sheet_storage=True, sync_seconds=35,
                allowed_origins='https://turtlesoup-ytac.onrender.com',
                gemini_api_key=os.environ['GEMINI_API_KEY'].strip(),
                google_application_credentials=os.environ['GOOGLE_APPLICATION_CREDENTIALS'].strip(),
                database_url='sqlite://')
            settings.validate()
            return settings
        values = {}
        for name, field in cls.__dataclass_fields__.items():
            raw = os.environ.get(name.upper())
            if raw is not None:
                values[name] = raw.lower() == 'true' if field.type is bool else field.type(raw)
        settings = cls(**values)
        settings.validate()
        return settings

    def validate(self):
        if self.app_mode not in ('local', 'preview', 'production') or self.ai_mode not in ('mock', 'gemini'):
            raise ValueError('APP_MODE 或 AI_MODE 設定無效')
        if self.roster_mode not in ('file', 'google'):
            raise ValueError('ROSTER_MODE 設定無效')
        if self.app_mode == 'production':
            if self.ai_mode != 'gemini' or self.roster_mode != 'google':
                raise ValueError('正式模式必須使用 Gemini 與 Google 名冊')
        if self.app_mode in ('preview', 'production'):
            if not self.sheet_storage or not self.sheets_sync_enabled:
                raise ValueError('正式模式必須啟用 Google 試算表儲存')
            if '*' in self.allowed_origins or any(not x.strip().startswith('https://') for x in self.allowed_origins.split(',')):
                raise ValueError('正式模式必須指定 HTTPS 前台來源')
        if self.session_seconds < 60 or self.sync_seconds < 5:
            raise ValueError('登入或同步間隔設定無效')
        if not 0 <= self.gemini_temperature <= 2 or not 128 <= self.gemini_max_output_tokens <= 4096:
            raise ValueError('Gemini 生成參數超出允許範圍')

    def path(self, path):
        p = Path(path)
        return p if p.is_absolute() else ROOT / p
