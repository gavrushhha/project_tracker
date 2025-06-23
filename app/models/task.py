from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime

from app.db.base_class import Base


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    issue_key = Column(String, unique=True, index=True, nullable=False)
    queue_key = Column(String, nullable=False)
    assignee = Column(String, index=True, nullable=False)
    summary = Column(String, nullable=False)
    form_type = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow) 