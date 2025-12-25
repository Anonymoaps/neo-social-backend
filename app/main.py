import os
import uuid
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, status, Request, Form, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text

# Import local modules
# Assuming 'app' is the package if running from root as 'python -m app.main' or 'uvicorn app.main:app'
from . import models, schemas, database
from .api import videos, remix

# 1. Criação de Tabelas
# Garanta que a classe User e a classe Video existam e estejam vinculadas corretamente.
models.Base.metadata.create_all(bind=database.engine)
print("Tabelas criadas com sucesso!")

app = FastAPI(title="Super App Video API", description="Backend updated for PostgreSQL", version="0.2.0")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static & Templates
# Determine paths relative to this file or CWD
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# If templates are in Neo Projeto/templates and main.py is in Neo Projeto/app/
TEMPLATES_DIR = os.path.join(BASE_DIR, "..", "templates")
STATIC_DIR = os.path.join(BASE_DIR, "..", "static")
UPLOADS_DIR = os.path.join(BASE_DIR, "..", "uploads_mock")
os.makedirs(UPLOADS_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=UPLOADS_DIR), name="static") # Using mock uploads as static for now
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Dependency
def get_db():
    return database.get_db()

# --- ROUTES ---

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# 1. SISTEMA DE LOGIN
# Routes: /login, /signup, /auth/google
# The frontend sends 'username' to /login via POST.

@app.post("/login", tags=["Auth"])
async def login(username: str = Form(...), db: Session = Depends(database.get_db)):
    """
    Simplified login/signup flow for the 'Fake Social' frontend.
    If user exists, log them in. If not, create them.
    NOTE: Since User model requires email/pass, we generate dummies for this 'fake' flow.
    """
    user_query = db.query(models.User).filter(models.User.username == username)
    user = user_query.first()

    if not user:
        # Create new user (Sign Up logic included here/auto-provision)
        dummy_email = f"{username}@neo.network"
        dummy_password = "social_login_dummy_password" # In prod, use hashing!
        
        new_user = models.User(
            username=username,
            email=dummy_email,
            password_hash=dummy_password,
            bio="New to NEO Network",
            avatar_url=f"https://api.dicebear.com/7.x/avataaars/svg?seed={username}"
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return {"message": "User created and logged in", "user": new_user.username, "id": str(new_user.id)}
    
    return {"message": "Logged in", "user": user.username, "id": str(user.id)}

@app.post("/signup", tags=["Auth"])
async def signup(username: str = Form(...), email: str = Form(...), password: str = Form(...), db: Session = Depends(database.get_db)):
    # Legacy/Explicit Signup if needed
    existing = db.query(models.User).filter((models.User.username == username) | (models.User.email == email)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username or Email already registered")
    
    new_user = models.User(
        username=username,
        email=email,
        password_hash=password, # Use hashing in real app
        avatar_url=f"https://api.dicebear.com/7.x/avataaars/svg?seed={username}"
    )
    db.add(new_user)
    db.commit()
    return {"message": "User created"}

@app.get("/me", tags=["Auth"])
async def read_users_me(db: Session = Depends(database.get_db)):
    # For this demo, we mock 'me' as a hardcoded demo user or the last one.
    # ideally, we read a cookie/token. 
    # To keep simple and consistent with the existing frontend which doesn't seem to send tokens:
    # We will return a dummy response or try to infer from session.
    # Since existing JS 'finishOnboarding' just waits for OK response, 
    # we'll assume the client manages state or we return a generic 'me'.
    # *Correction*: The JS 'openProfile' fetches '/me' to compare username.
    # We can mock this to return the username from a cookie if we set one, 
    # or just return a default for the prototype.
    return {"user": "current_user_placeholder", "id": "uuid"}

# Google Login Mock
@app.get("/auth/google", tags=["Auth"])
async def google_login():
    return {"message": "Google Login Endpoint (Placeholder)"}


# --- API ---
# Including routers for Videos and Remixes
app.include_router(videos.router, prefix="/videos", tags=["Videos"])
app.include_router(remix.router, prefix="/remix", tags=["AI Remix"])

# Passthrough for templates to fetch feed (linking to API)
@app.get("/feed", tags=["Feed"])
async def get_feed(type: str = "foryou", db: Session = Depends(database.get_db)):
    # Redirecting to videos logic or implementing here
    # Reuse videos.read_videos logic
    v = db.query(models.Video).all()
    # Serialize manually or use Pydantic
    results = []
    for video in v:
        results.append({
            "id": str(video.id),
            "url": video.video_url,
            "title": video.title,
            "likes": 0, # Implement Like counts in model if needed
            "comments_count": 0,
            "author": video.owner.username if video.owner else "Unknown",
            "author_pic": video.owner.avatar_url if video.owner else "",
            "is_following": False,
            "is_own_video": False,
            "filter_type": "cyberpunk" # Default or stored
        })
    return results

# Comment Endpoints (Directly here to ensure they exist as requested)
@app.get("/comments/{video_id}", tags=["Comments"])
async def get_comments(video_id: str, db: Session = Depends(database.get_db)):
    try:
        vid_uuid = uuid.UUID(video_id)
    except:
        return []
    
    comments = db.query(models.Comment).filter(models.Comment.video_id == vid_uuid).all()
    res = []
    for c in comments:
        res.append({
            "id": str(c.id),
            "user_id": c.author.username if c.author else "Anon",
            "text": c.content,
            "profile_pic": c.author.avatar_url if c.author else ""
        })
    return res

@app.post("/comment", tags=["Comments"])
async def post_comment(video_id: str = Form(...), text: str = Form(...), db: Session = Depends(database.get_db)):
    # Need a user. In this stateless mode, we pick the first user or create a guest.
    # Ideally use dependency to get current user.
    user = db.query(models.User).first()
    if not user:
        # Create a fallback user if DB empty
        user = models.User(username="Guest", email="guest@neo.network", password_hash="guest", avatar_url="")
        db.add(user)
        db.commit()
    
    try:
        vid_uuid = uuid.UUID(video_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid Video ID")

    new_comment = models.Comment(
        video_id=vid_uuid,
        user_id=user.id,
        content=text
    )
    db.add(new_comment)
    db.commit()
    db.refresh(new_comment)
    
    return {
        "id": str(new_comment.id),
        "user_id": user.username,
        "text": new_comment.content,
        "profile_pic": user.avatar_url
    }

# Upload Mock
@app.post("/upload", tags=["Upload"])
async def upload_video(title: str = Form(...), file: UploadFile = File(...), db: Session = Depends(database.get_db)):
    file_location = f"uploads_mock/{file.filename}"
    with open(file_location, "wb+") as file_object:
        file_object.write(file.file.read())
    
    # Create DB entry
    # Get user
    user = db.query(models.User).first()
    if not user:
        user = models.User(username="Creator", email="creator@neo.example", password_hash="123")
        db.add(user)
        db.commit()

    new_video = models.Video(
        user_id=user.id,
        title=title,
        video_url=f"/static/{file.filename}",
        is_ai_generated=False
    )
    db.add(new_video)
    db.commit()
    
    return {"info": f"file '{file.filename}' saved"}

