from pydantic import BaseModel, UUID4

class RemixRequest(BaseModel):
    original_video_id: UUID4
    prompt: str
    user_id: UUID4 # The user creating the remix
