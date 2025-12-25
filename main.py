import shutil
import os
import uuid
import random
from typing import Optional, List
from datetime import datetime

# --- CLOUDINARY & DB IMPORTS ---
import cloudinary
import cloudinary.uploader
from sqlalchemy import create_engine, text, Column, Integer, String, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import sessionmaker, declarative_base, relationship

from fastapi import FastAPI, UploadFile, File, Form, Request, HTTPException, Response, Cookie, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# --- CONFIGURAÇÃO INICIAL (V-CLOUD) ---
app = FastAPI(title="NEO Social Engine V-Cloud", version="15.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True, 
)

os.makedirs("templates", exist_ok=True)
os.makedirs("static", exist_ok=True)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# --- DATABASE SETUP (POSTGRES OR SQLITE) ---
DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL:
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    engine = create_engine(DATABASE_URL)
else:
    DATABASE_URL = "sqlite:///neo.db"
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

# --- SUPER BLINDAGEM DE BANCO (SQL FIX) ---
try:
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_pioneer BOOLEAN DEFAULT FALSE;"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS bio TEXT;"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_pic TEXT;"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS followers_count INTEGER DEFAULT 0;"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS following_count INTEGER DEFAULT 0;"))
        
        conn.execute(text("ALTER TABLE comments ADD COLUMN IF NOT EXISTS username TEXT;"))
        conn.execute(text("ALTER TABLE comments ADD COLUMN IF NOT EXISTS timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP;"))
        conn.commit()
    print("✅ Schema verificado: bio, profile_pic, counts, pioneer, comments.")
except Exception as e:
    print(f"⚠️ Aviso SQL Startup: {e}")

# --- CLOUDINARY SETUP ---
cloudinary.config( 
  cloud_name = os.getenv("CLOUD_NAME", ""), 
  api_key = os.getenv("CLOUD_API_KEY", ""), 
  api_secret = os.getenv("CLOUD_API_SECRET", ""),
  secure = True
)

# --- DATABASE & ORM SETUP ---
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    username = Column(String, primary_key=True)
    created_at = Column(String)
    profile_pic = Column(String)
    bio = Column(String, nullable=True)
    is_pioneer = Column(Boolean, default=False)
    followers_count = Column(Integer, default=0)
    following_count = Column(Integer, default=0)

class Video(Base):
    __tablename__ = "videos"
    id = Column(String, primary_key=True)
    title = Column(String)
    url = Column(String)
    likes = Column(Integer, default=0)
    filter_type = Column(String, nullable=True)
    author = Column(String, ForeignKey("users.username"))
    created_at = Column(DateTime, default=datetime.utcnow)
    comments = relationship("Comment", back_populates="video", cascade="all, delete-orphan")

class Comment(Base):
    __tablename__ = "comments"
    id = Column(Integer, primary_key=True, autoincrement=True)
    text = Column(String)
    username = Column(String, ForeignKey("users.username"))
    timestamp = Column(DateTime, default=datetime.utcnow)
    video_id = Column(String, ForeignKey("videos.id"))
    video = relationship("Video", back_populates="comments")

class Like(Base):
    __tablename__ = "likes"
    user_id = Column(String, ForeignKey("users.username"), primary_key=True)
    video_id = Column(String, ForeignKey("videos.id"), primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Follow(Base):
    __tablename__ = "follows"
    follower_id = Column(String, ForeignKey("users.username"), primary_key=True)
    followed_id = Column(String, ForeignKey("users.username"), primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- SESSIONS ---
active_sessions = {}
def get_user_from_session(token):
    return active_sessions.get(token)

# --- ENDPOINTS ---

@app.post("/login")
async def login(response: Response, username: str = Form(...)): 
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        if not user:
            user_count = db.query(User).count()
            is_pioneer = True if user_count < 1000 else False
            new_user = User(
                username=username, 
                created_at=str(datetime.now()), 
                profile_pic=f"https://ui-avatars.com/api/?name={username}&background=random", 
                is_pioneer=is_pioneer
            )
            db.add(new_user)
            db.commit()
        
        session_token = str(uuid.uuid4())
        active_sessions[session_token] = username
        response.set_cookie(key="neo_session", value=session_token, httponly=True, samesite='lax', max_age=3600*24*7)
        return {"message": "Logged in", "user": username}
    finally:
        db.close()

@app.get("/me")
async def get_current_user(neo_session: Optional[str] = Cookie(None)):
    user_name = get_user_from_session(neo_session)
    if not user_name:
        return JSONResponse(content={"user": None}, status_code=401)
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == user_name).first()
        return {
            "user": user.username, "profile_pic": user.profile_pic,
            "is_pioneer": user.is_pioneer, "bio": user.bio,
            "followers": user.followers_count, "following": user.following_count
        }
    finally:
        db.close()

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/feed")
async def get_feed(type: str = "foryou", neo_session: Optional[str] = Cookie(None)):
    current_user = get_user_from_session(neo_session) or ""
    with engine.connect() as conn:
        query = text("""
            SELECT v.id, v.title, v.url, v.author, v.created_at,
                u.profile_pic as author_pic, u.is_pioneer as author_is_pioneer,
                (SELECT COUNT(*) FROM likes WHERE video_id = v.id) as total_likes,
                (SELECT COUNT(*) FROM likes WHERE video_id = v.id AND user_id = :cu) as user_liked,
                (SELECT COUNT(*) FROM comments WHERE video_id = v.id) as total_comments
            FROM videos v
            LEFT JOIN users u ON v.author = u.username
            ORDER BY v.created_at DESC
        """)
        rows = conn.execute(query, {"cu": current_user}).mappings().all()

    videos = [{
        "id": r["id"], "title": r["title"], "url": r["url"],
        "likes": r["total_likes"], "comments_count": r["total_comments"],
        "user_has_liked": r["user_liked"] > 0, "author": r["author"],
        "author_pic": r["author_pic"], "author_is_pioneer": r["author_is_pioneer"]
    } for r in rows]
    return JSONResponse(content=videos)

# Nova Rota: Perfil Público
@app.get("/user/{username}")
async def get_public_profile(username: str):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Recalcular counts "real-time" se quiser, ou usar colunas cacheadas
        # Para MVP: usar colunas cacheadas + query videos
        videos = db.query(Video).filter(Video.author == username).order_by(Video.created_at.desc()).all()
        # Likes recebidos
        likes_recv = db.execute(text("SELECT COUNT(*) FROM likes l JOIN videos v ON l.video_id=v.id WHERE v.author=:u"), {"u":username}).scalar()

        return {
            "username": user.username,
            "profile_pic": user.profile_pic,
            "bio": user.bio or "Sem descrição.",
            "is_pioneer": user.is_pioneer,
            "stats": {
                "videos": len(videos),
                "likes": likes_recv or 0,
                "followers": user.followers_count or 0,
                "following": user.following_count or 0
            },
            "videos": [{"id": v.id, "url": v.url} for v in videos]
        }
    finally:
        db.close()

# Rota de Edição
@app.post("/update_profile")
async def update_profile(
    bio: str = Form(...),
    profile_pic: str = Form(...),
    neo_session: Optional[str] = Cookie(None)
):
    user_name = get_user_from_session(neo_session)
    if not user_name: raise HTTPException(status_code=401)
    
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == user_name).first()
        if user:
            user.bio = bio
            user.profile_pic = profile_pic
            db.commit()
            return {"message": "Updated"}
    finally:
        db.close()

# Upload / Comments / Like
@app.post("/upload")
async def upload_video(file: UploadFile = File(...), title: str = Form(...), neo_session: Optional[str] = Cookie(None)):
    author = get_user_from_session(neo_session)
    if not author: raise HTTPException(status_code=401)
    try:
        res = cloudinary.uploader.upload(file.file, resource_type="video", folder="neo_videos")
        db = SessionLocal()
        db.add(Video(id=str(uuid.uuid4()), title=title, url=res["secure_url"], author=author))
        db.commit()
        db.close()
        return {"message": "Success"}
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)

@app.post("/video/{video_id}/comment")
async def comment_video(video_id: str, text: str = Form(...), neo_session: Optional[str] = Cookie(None)):
    user = get_user_from_session(neo_session)
    if not user: raise HTTPException(status_code=401)
    db = SessionLocal()
    db.add(Comment(text=text, username=user, video_id=video_id))
    db.commit()
    db.close()
    return {"message": "Success"}

@app.get("/comments/{video_id}")
async def get_comments(video_id: str):
    db = SessionLocal()
    res = db.execute(text("SELECT c.text, c.username, u.profile_pic, u.is_pioneer FROM comments c LEFT JOIN users u ON c.username=u.username WHERE c.video_id=:v ORDER BY c.timestamp ASC"), {"v":video_id}).mappings().all()
    db.close()
    return [{"text":r["text"], "username":r["username"], "profile_pic":r["profile_pic"], "is_pioneer":r["is_pioneer"]} for r in res]

@app.post("/toggle_like/{video_id}")
async def toggle_like(video_id: str, neo_session: Optional[str] = Cookie(None)):
    user = get_user_from_session(neo_session)
    if not user: raise HTTPException(status_code=401)
    db = SessionLocal()
    like = db.query(Like).filter(Like.user_id==user, Like.video_id==video_id).first()
    if like: db.delete(like); liked=False
    else: db.add(Like(user_id=user, video_id=video_id)); liked=True
    db.commit()
    db.close()
    return {"liked": liked}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
