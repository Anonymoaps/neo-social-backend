from pydantic import BaseModel, UUID4, Field
from typing import Optional, List
from datetime import datetime

# User Schemas
class UserBase(BaseModel):
    username: str
    email: str
    avatar_url: Optional[str] = None
    bio: Optional[str] = None

class UserCreate(UserBase):
    password: str

class UserResponse(UserBase):
    id: UUID4
    created_at: datetime
    
    class Config:
        from_attributes = True

# Video Schemas
class VideoBase(BaseModel):
    title: str
    description: Optional[str] = None
    video_url: str
    thumbnail_url: Optional[str] = None
    duration_seconds: Optional[int] = None
    is_ai_generated: bool = False
    ai_prompt_used: Optional[str] = None

class VideoCreate(VideoBase):
    pass

class VideoResponse(VideoBase):
    id: UUID4
    user_id: UUID4
    view_count: int
    created_at: datetime

    class Config:
        from_attributes = True
