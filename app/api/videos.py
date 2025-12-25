from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text
from .. import models, schemas, database
from ..services.storage import storage
import uuid

router = APIRouter()

@router.post("/upload", response_model=schemas.VideoResponse, status_code=status.HTTP_201_CREATED)
async def upload_video(
    file: UploadFile = File(...),
    title: str = Form(...),
    description: str = Form(None),
    user_id: str = Form(...), # In real auth, this would come from the token
    db: Session = Depends(database.get_db)
):
    # 1. Upload to Storage (Simulated S3/R2)
    video_url = await storage.upload_video(file)
    
    # 2. Create Video Record in DB
    new_video = models.Video(
        id=uuid.uuid4(),
        user_id=user_id,
        title=title,
        description=description,
        video_url=video_url,
        is_ai_generated=False
    )
    
    db.add(new_video)
    db.commit()
    db.refresh(new_video)
    
    return new_video

@router.get("/feed", response_model=list[schemas.VideoResponse])
def get_feed(skip: int = 0, limit: int = 10, db: Session = Depends(database.get_db)):
    """
    Get 'For You' Feed.
    Uses a Weighted algorithm to score videos:
    - Likes: 3 points
    - Remixes (Viral Factor): 5 points (High weight to encourage AI usage)
    - Recency: Boost for videos < 24h old
    """
    
    # Raw SQL for performance and complexity handling
    # We join with Likes and RemixChain to count interactions
    query = text("""
        SELECT 
            v.id, 
            v.user_id, 
            v.title, 
            v.description, 
            v.video_url, 
            v.thumbnail_url, 
            v.duration_seconds, 
            v.view_count, 
            v.created_at,
            v.is_ai_generated, 
            v.ai_prompt_used,
            
            -- SCORING ALGORITHM
            (
                (COALESCE(l_count.likes, 0) * 3) + 
                (COALESCE(r_count.remixes, 0) * 5) +
                (CASE WHEN v.created_at > NOW() - INTERVAL '24 hours' THEN 50 ELSE 0 END)
            ) as score
            
        FROM videos v
        
        -- Count Likes Efficiently
        LEFT JOIN (
            SELECT video_id, COUNT(*) as likes 
            FROM likes 
            GROUP BY video_id
        ) l_count ON v.id = l_count.video_id
        
        -- Count Remixes (Children videos created from this one)
        LEFT JOIN (
            SELECT parent_video_id, COUNT(*) as remixes 
            FROM remix_chain 
            GROUP BY parent_video_id
        ) r_count ON v.id = r_count.parent_video_id
        
        ORDER BY score DESC, v.created_at DESC
        OFFSET :skip LIMIT :limit;
    """)
    
    result = db.execute(query, {"skip": skip, "limit": limit})
    
    # Map raw result to Pydantic models
    videos = []
    for row in result:
        # We need to map the row explicitly because it's a raw result
        # Note: In a larger app we might use an ORM mapping or a helper
        videos.append({
            "id": row.id,
            "user_id": row.user_id,
            "title": row.title,
            "description": row.description,
            "video_url": row.video_url,
            "thumbnail_url": row.thumbnail_url,
            "duration_seconds": row.duration_seconds,
            "view_count": row.view_count,
            "created_at": row.created_at,
            "is_ai_generated": row.is_ai_generated,
            "ai_prompt_used": row.ai_prompt_used
        })
        
    return videos
