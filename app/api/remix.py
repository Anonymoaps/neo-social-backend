from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from .. import models, database, schemas_remix, schemas
from ..services.ai_generator import ai_service
import uuid

router = APIRouter()

@router.post("/", response_model=schemas.VideoResponse, status_code=status.HTTP_201_CREATED)
async def create_remix(
    request: schemas_remix.RemixRequest,
    db: Session = Depends(database.get_db)
):
    """
    Creates an AI Remix of an existing video.
    1. Fetches original video.
    2. Calls AI Service to generate new video.
    3. Saves new video.
    4. Creates Royalty Chain (RemixChain) linking new video to original.
    """
    
    # 1. Fetch Original Video
    original_video = db.query(models.Video).filter(models.Video.id == request.original_video_id).first()
    if not original_video:
        raise HTTPException(status_code=404, detail="Original video not found")
        
    # 2. Call AI Service
    # Note: In production, this might be a background task (Celery/BullMQ) because it's slow.
    new_video_url = await ai_service.generate_remix(original_video.video_url, request.prompt)
    
    # 3. Create New Video Record
    new_video = models.Video(
        id=uuid.uuid4(),
        user_id=request.user_id,
        title=f"Remix of {original_video.title}",
        description=f"AI Remix with prompt: {request.prompt}",
        video_url=new_video_url,
        is_ai_generated=True,
        ai_prompt_used=request.prompt,
        ai_model_used="stable-video-diffusion-mock"
    )
    
    db.add(new_video)
    db.commit()
    db.refresh(new_video)
    
    # 4. Create Remix Chain (Royalty Tracking)
    # This is critical for the monetization model.
    remix_link = models.RemixChain(
        id=uuid.uuid4(),
        parent_video_id=original_video.id,
        child_video_id=new_video.id,
        remix_type="ai_style_transfer",
        royalty_percentage=10.00 # 10% of future revenue goes to parent
    )
    
    db.add(remix_link)
    db.commit()
    
    return new_video
