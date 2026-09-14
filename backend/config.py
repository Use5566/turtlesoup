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

    @classmethod
    def from_env(cls):
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
            if not self.database_url.startswith(('postgresql://', 'postgresql+psycopg://', 'postgres://')):
                raise ValueError('正式模式必須設定持久 PostgreSQL DATABASE_URL')
            if '*' in self.allowed_origins or any(not x.strip().startswith('https://') for x in self.allowed_origins.split(',')):
                raise ValueError('正式模式必須指定 HTTPS 前台來源')
        if self.session_seconds < 60 or self.sync_seconds < 5:
            raise ValueError('登入或同步間隔設定無效')
        if not 0 <= self.gemini_temperature <= 2 or not 128 <= self.gemini_max_output_tokens <= 4096:
            raise ValueError('Gemini 生成參數超出允許範圍')

    def path(self, path):
        p = Path(path)
        return p if p.is_absolute() else ROOT / p
