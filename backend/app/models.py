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
    # True if the match was first discovered already live
    # (never seen as pre_game) — such matches are hidden from the calendar
    added_live = Column(Boolean, default=False)
    stream_urls = Column(JSON, default=list)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
