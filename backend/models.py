from contextlib import contextmanager
from datetime import datetime, timezone
from sqlalchemy import create_engine, event, Integer, String, Text, Float, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


class Base(DeclarativeBase):
    pass


class Login(Base):
    __tablename__ = 'logins'
    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    student: Mapped[str] = mapped_column(String(40), index=True)
    expires: Mapped[float] = mapped_column(Float)
    fingerprint: Mapped[str] = mapped_column(String(64))


class Game(Base):
    __tablename__ = 'games'
    __table_args__ = (UniqueConstraint('student', 'activity', 'version'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uid: Mapped[str] = mapped_column(String(36), unique=True)
    student: Mapped[str] = mapped_column(String(40))
    activity: Mapped[str] = mapped_column(String(80))
    version: Mapped[str] = mapped_column(String(64))
    puzzle: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(20), default='active')
    started: Mapped[str] = mapped_column(String(40), default=utcnow)
    updated: Mapped[str] = mapped_column(String(40), default=utcnow)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    synced_revision: Mapped[int] = mapped_column(Integer, default=0)


class Turn(Base):
    __tablename__ = 'turns'
    __table_args__ = (UniqueConstraint('game_id', 'sequence'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(36), unique=True)
    game_id: Mapped[int] = mapped_column(Integer, index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    question: Mapped[str] = mapped_column(Text)
    question_type: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(30), default='processing')
    answer: Mapped[str] = mapped_column(String(20), default='')
    model: Mapped[str] = mapped_column(String(80))
    usage: Mapped[str] = mapped_column(Text, default='{}')
    created: Mapped[str] = mapped_column(String(40), default=utcnow)
    synced: Mapped[int] = mapped_column(Integer, default=0)


class Limit(Base):
    __tablename__ = 'limits'
    key: Mapped[str] = mapped_column(String(150), primary_key=True)
    until: Mapped[float] = mapped_column(Float)
    count: Mapped[int] = mapped_column(Integer)


class Store:
    def __init__(self, settings):
        url = settings.database_url
        if url.startswith('sqlite:///'):
            p = settings.path(url.removeprefix('sqlite:///'))
            p.parent.mkdir(parents=True, exist_ok=True)
            url = 'sqlite:///' + p.as_posix()
        for prefix in ('postgres://', 'postgresql://'):
            if url.startswith(prefix):
                url = 'postgresql+psycopg://' + url.removeprefix(prefix)
        self.engine = create_engine(url, pool_pre_ping=True,
            connect_args={'check_same_thread': False, 'timeout': 20} if url.startswith('sqlite') else {})
        if url.startswith('sqlite'):
            @event.listens_for(self.engine, 'connect')
            def configure(dbapi, _):
                dbapi.execute('PRAGMA journal_mode=WAL')
                dbapi.execute('PRAGMA synchronous=FULL')
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(self.engine, expire_on_commit=False)

    @contextmanager
    def transaction(self):
        with self.session.begin() as db:
            yield db
