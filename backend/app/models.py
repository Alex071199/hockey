from sqlalchemy import JSON, Boolean, Column, DateTime, Integer, String, func

from app.database import Base


class Match(Base):
    __tablename__ = "matches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    match_uid = Column(String, unique=True, index=True)
    league = Column(String, index=True)
    team_home = Column(String)
    team_away = Column(String)
    datetime_utc = Column(DateTime, index=True)
    status = Column(String, default="pre_game")
    added_live = Column(Boolean, default=False)
    stream_urls = Column(JSON, default=list)
    home_score = Column(Integer, nullable=True)
    away_score = Column(Integer, nullable=True)
    current_period = Column(String, nullable=True)
    sp_match_id = Column(Integer, nullable=True)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class Reminder(Base):
    __tablename__ = "reminders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String, index=True)
    chat_id = Column(String, index=True, nullable=True)
    match_id = Column(Integer, index=True, nullable=True)
    league = Column(String, nullable=True)
    team_home = Column(String)
    team_away = Column(String)
    datetime_utc = Column(DateTime, nullable=True)
    soon_sent = Column(Boolean, default=False)
    live_sent = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())


class Subscriber(Base):
    __tablename__ = "subscribers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chat_id = Column(String, unique=True, index=True)
    username = Column(String, nullable=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())


class Donation(Base):
    __tablename__ = "donations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    match_id = Column(Integer, index=True)
    team = Column(String)
    amount = Column(Integer)
    donor_name = Column(String, default="Аноним")
    tx_id = Column(String, nullable=True, index=True)
    message = Column(String, nullable=True)
    created_at = Column(DateTime, default=func.now())


class News(Base):
    __tablename__ = "news"

    id = Column(Integer, primary_key=True, autoincrement=True)
    text = Column(String)
    created_at = Column(DateTime, default=func.now())
