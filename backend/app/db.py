from datetime import datetime, timezone
from sqlalchemy import create_engine, event, String, Text, ForeignKey, Integer
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from .settings import settings

def now():
    return datetime.now(timezone.utc).isoformat()

class Base(DeclarativeBase):
    pass

class CardRecord(Base):
    __tablename__ = 'cards'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, index=True)
    set_id: Mapped[str] = mapped_column(String, index=True)
    category: Mapped[str] = mapped_column(String, index=True)
    payload: Mapped[str] = mapped_column(Text)

class Meta(Base):
    __tablename__ = 'meta'
    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(Text)

class UserSession(Base):
    __tablename__ = 'sessions'
    token_hash: Mapped[str] = mapped_column(String, primary_key=True)
    expires: Mapped[int] = mapped_column(Integer, index=True)
    game_id: Mapped[str | None] = mapped_column(String, nullable=True)

class Game(Base):
    __tablename__ = 'games'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner: Mapped[str] = mapped_column(ForeignKey('sessions.token_hash'), index=True)
    created: Mapped[str] = mapped_column(String, default=now)
    version: Mapped[int] = mapped_column(Integer, default=0)
    recommendation: Mapped[str | None] = mapped_column(String, nullable=True)

class Attempt(Base):
    __tablename__ = 'attempts'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[str] = mapped_column(ForeignKey('games.id'), index=True)
    card_id: Mapped[str] = mapped_column(String)
    observed_card: Mapped[str | None] = mapped_column(Text, nullable=True)
    clues: Mapped[str] = mapped_column(Text)
    remaining: Mapped[int] = mapped_column(Integer)
    created: Mapped[str] = mapped_column(String, default=now)

engine = create_engine(f'sqlite:///{settings.storage / "cartosolver.sqlite3"}', connect_args={'check_same_thread': False, 'timeout': 30})
@event.listens_for(engine, 'connect')
def pragmas(connection, _):
    connection.execute('PRAGMA journal_mode=WAL')
    connection.execute('PRAGMA foreign_keys=ON')

Session = sessionmaker(engine, expire_on_commit=False)

def init_db():
    Base.metadata.create_all(engine)
    # Additive migration: retain existing games and their legacy catalog fallback.
    with engine.begin() as db:
        if 'observed_card' not in {r[1] for r in db.exec_driver_sql('PRAGMA table_info(attempts)')}:
            db.exec_driver_sql('ALTER TABLE attempts ADD COLUMN observed_card TEXT')
