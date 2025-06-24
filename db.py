# db.py
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from config import DATABASE_URL

Base = declarative_base()

class Task(Base):
    __tablename__ = 'tasks'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    task_text = Column(String, nullable=False)
    due_date = Column(DateTime, nullable=True)
    status = Column(String, default='pending') # pending, completed, overdue, cancelled
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    notes = Column(Text, nullable=True)
    priority = Column(String, default='medium')
    category = Column(String, nullable=True) # <-- ДОБАВЬТЕ ЭТУ СТРОКУ

    def __repr__(self):
        return (f"<Task(id={self.id}, user_id={self.user_id}, task_text='{self.task_text[:20]}...', "
                f"status='{self.status}', priority='{self.priority}', category='{self.category}')>")

engine = create_engine(DATABASE_URL)
Base.metadata.create_all(engine)

Session = sessionmaker(bind=engine)

def get_session():
    return Session()