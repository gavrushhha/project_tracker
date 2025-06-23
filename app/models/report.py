from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime

from app.db.base_class import Base


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, index=True, nullable=True)
    programs_supported = Column(Integer, nullable=True)
    projects_in_program = Column(Integer, nullable=True)
    new_scientists_employed = Column(Integer, nullable=True)
    file_path = Column(String, nullable=True)
    issue_key = Column(String, nullable=True)
    attachment_id = Column(String, nullable=True)
    attachment_name = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow) 