from sqlalchemy import Column, Integer, String, Boolean
from app.db.base_class import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    login = Column(String, unique=True, index=True, nullable=False)
    is_admin = Column(Boolean, default=False) 