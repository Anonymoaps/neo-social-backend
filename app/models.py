from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Text, DateTime, Numeric, DECIMAL
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func, text
from sqlalchemy.dialects.postgresql import UUID
import uuid
from .database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    avatar_url = Column(Text)
    bio = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    videos = relationship("Video", back_populates="owner")
    wallet = relationship("Wallet", back_populates="owner", uselist=False)
    comments = relationship("Comment", back_populates="author")

class Wallet(Base):
    __tablename__ = "wallets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), unique=True)
    balance = Column(DECIMAL(18, 4), default=0.0000)
    currency = Column(String(3), default='BRL')
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    owner = relationship("User", back_populates="wallet")

class Video(Base):
    __tablename__ = "videos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    title = Column(String(255))
    description = Column(Text)
    video_url = Column(Text, nullable=False)
    thumbnail_url = Column(Text)
    duration_seconds = Column(Integer)
    view_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # AI Metadados
    is_ai_generated = Column(Boolean, default=False)
    ai_prompt_used = Column(Text)
    ai_model_used = Column(String(100))

    owner = relationship("User", back_populates="videos")
    comments = relationship("Comment", back_populates="video")
    
    # Relationships for remixes could be complex, omitting for brevity in initial setup but can be added if needed

class RemixChain(Base):
    __tablename__ = "remix_chain"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    parent_video_id = Column(UUID(as_uuid=True), ForeignKey("videos.id"))
    child_video_id = Column(UUID(as_uuid=True), ForeignKey("videos.id"))
    remix_type = Column(String(50), default='ai_remix')
    royalty_percentage = Column(DECIMAL(5, 2), default=10.00)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Comment(Base):
    __tablename__ = "comments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    video_id = Column(UUID(as_uuid=True), ForeignKey("videos.id"))
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    author = relationship("User", back_populates="comments")
    video = relationship("Video", back_populates="comments")
