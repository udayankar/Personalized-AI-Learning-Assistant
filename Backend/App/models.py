from sqlalchemy import String , func , TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from .database import Base

class User(Base):
    __tablename__ = "users"
    ID : Mapped[int] = mapped_column(primary_key=True, index=True)
    Name : Mapped[str] = mapped_column(String(100), nullable=False)
    Email : Mapped[str] = mapped_column(String(255) , unique=True , index=True , nullable=False)
    Password : Mapped[str] = mapped_column(String(255) , nullable=False)
    Created_at : Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True),nullable=False,server_default=func.now())
