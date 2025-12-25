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

from starlette.middleware.sessions import SessionMiddleware

# --- CONFIGURAÇÃO INICIAL (V-CLOUD) ---
app = FastAPI(title="NEO Social Engine V-Cloud", version="15.5.0")

# SECURITY: Secret Key for Session persistence
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "chave-super-secreta-fixa-neo-2025-v1"), https_only=True, same_site="lax", max_age=3600*24*7)

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
    likes = Column(Integer, default=0) # Legacy column, verify with Like table count
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

def update_db_schema():
    try:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_pioneer BOOLEAN DEFAULT FALSE;"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS bio TEXT;"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_pic TEXT;"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS followers_count INTEGER DEFAULT 0;"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS following_count INTEGER DEFAULT 0;"))
            
            conn.execute(text("ALTER TABLE comments ADD COLUMN IF NOT EXISTS username TEXT;"))
            conn.execute(text("ALTER TABLE comments ADD COLUMN IF NOT EXISTS timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP;"))
            
            conn.execute(text("CREATE TABLE IF NOT EXISTS follows (follower_id TEXT, followed_id TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (follower_id, followed_id));"))
            conn.commit()
        print("✅ Schema verificado: bio, profile_pic, counts, pioneer, comments, follows.")
    except Exception as e:
        print(f"⚠️ Aviso SQL Schema Update: {e}")

update_db_schema()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- SESSIONS (REFACTORED TO COOKIE SESSION) ---
# Removed active_sessions dict to depend on SessionMiddleware
    
def get_user_from_session(request: Request):
    return request.session.get("user")

# --- ENDPOINTS ---

@app.post("/login")
async def login(request: Request, response: Response, username: str = Form(...)): 
    print(f"Tentativa de login: {username}")
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
            print(f"Novo usuário criado: {username}")
        else:
            print(f"Usuário existente logado: {username}")
        
        # KEY FIX: Store user in persistent session cookie
        request.session["user"] = username
        print("Login SUCESSO - Sessão persistente criada")
        return RedirectResponse(url="/", status_code=303)
    except Exception as e:
        print(f"Erro no login: {e}")
        return RedirectResponse(url="/?error=server_error", status_code=303)
    finally:
        db.close()

@app.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return {"message": "Logged out"}

@app.get("/api/me")
async def get_current_user_api(request: Request):
    user_name = get_user_from_session(request)
    if not user_name:
        return JSONResponse(content={"user": None}, status_code=200) # Return null user instead of 401 for frontend check
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == user_name).first()
        if not user: return JSONResponse(content={"user": None})
        return {
            "user": user.username, "profile_pic": user.profile_pic,
            "is_pioneer": user.is_pioneer, "bio": user.bio,
            "followers": user.followers_count, "following": user.following_count
        }
    finally:
        db.close()

@app.get("/feed")
async def get_feed(request: Request, type: str = "foryou"):
    current_user = get_user_from_session(request) or ""
    
    with engine.connect() as conn:
        if type == "following" and current_user:
            # Check if following anyone
            following_check = conn.execute(text("SELECT COUNT(*) FROM follows WHERE follower_id = :cu"), {"cu": current_user}).scalar()
            if following_check == 0:
                print("Returning emtpy feed for no following")
                # Return empty list to trigger 'Siga pessoas' message on frontend
                return JSONResponse(content=[]) 

            query = text("""
                SELECT v.id, v.title, v.url, v.author, v.created_at,
                    u.profile_pic as author_pic, u.is_pioneer as author_is_pioneer,
                    (SELECT COUNT(*) FROM likes WHERE video_id = v.id) as total_likes,
                    (SELECT COUNT(*) FROM likes WHERE video_id = v.id AND user_id = :cu) as user_liked,
                    (SELECT COUNT(*) FROM comments WHERE video_id = v.id) as total_comments
                FROM videos v
                JOIN follows f ON v.author = f.followed_id
                LEFT JOIN users u ON v.author = u.username
                WHERE f.follower_id = :cu
                ORDER BY v.created_at DESC
            """)
        else: # For You (All videos)
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

# --- PROFILE ROUTES (HTML + API) ---

def get_profile_data(db, username, current_user_name):
    # Helper to get complete profile data + video stats
    user = db.query(User).filter(User.username == username).first()
    if not user: return None
    
    videos = db.query(Video).filter(Video.author == username).order_by(Video.created_at.desc()).all()
    
    # Calculate real likes count for each video
    video_list = []
    total_received_likes = 0
    for v in videos:
        likes_cnt = db.query(Like).filter(Like.video_id == v.id).count()
        total_received_likes += likes_cnt
        video_list.append({"id": v.id, "url": v.url, "likes": likes_cnt})
    
    is_following = False
    if current_user_name and current_user_name != username:
        is_following = db.query(Follow).filter(Follow.follower_id == current_user_name, Follow.followed_id == username).count() > 0

    return {
        "user": user,
        "videos": video_list,
        "likes_count": total_received_likes,
        "is_me": (username == current_user_name),
        "is_following": is_following
    }

@app.get("/me", response_class=HTMLResponse)
async def my_profile(request: Request):
    user_name = get_user_from_session(request)
    if not user_name: return RedirectResponse(url="/")
        
    db = SessionLocal()
    try:
        data = get_profile_data(db, user_name, user_name)
        if not data: return RedirectResponse(url="/")
        
        return templates.TemplateResponse("profile.html", {
            "request": request,
            "user": data["user"],
            "videos": data["videos"],
            "likes_count": data["likes_count"],
            "is_me": True,
            "is_following": False # Always false for self
        })
    finally:
        db.close()

@app.get("/user/{username}", response_class=HTMLResponse)
async def get_public_profile_page(request: Request, username: str):
    current_user_name = get_user_from_session(request)
    if current_user_name == username: return RedirectResponse(url="/me")

    db = SessionLocal()
    try:
        data = get_profile_data(db, username, current_user_name)
        if not data: return templates.TemplateResponse("index.html", {"request": request}) # Fallback
        
        return templates.TemplateResponse("profile.html", {
            "request": request,
            "user": data["user"],
            "videos": data["videos"],
            "likes_count": data["likes_count"],
            "is_me": False,
            "is_following": data["is_following"]
        })
    finally:
        db.close()

@app.get("/api/user/{username}")
async def get_public_profile_api(username: str):
    # API Endpoint for AJAX lookups if needed
    db = SessionLocal()
    try:
        data = get_profile_data(db, username, "")
        if not data: raise HTTPException(404)
        return {
            "username": data["user"].username,
            "profile_pic": data["user"].profile_pic,
            "bio": data["user"].bio,
            "is_pioneer": data["user"].is_pioneer,
            "stats": {
                "videos": len(data["videos"]),
                "likes": data["likes_count"],
                "followers": data["user"].followers_count,
                "following": data["user"].following_count
            },
            "videos": data["videos"]
        }
    finally:
        db.close()


@app.post("/update_profile")
async def update_profile(
    request: Request,
    bio: Optional[str] = Form(None),
    profile_pic: Optional[str] = Form(None)
):
    user_name = get_user_from_session(request)
    if not user_name: raise HTTPException(status_code=401)
    
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == user_name).first()
        if user:
            # Flexible Update Logic - Allow clearing fields
            if bio is not None:
                user.bio = bio # Empty string clears it
            if profile_pic is not None:
                user.profile_pic = profile_pic # Empty string clears it
            db.commit()
            return {"message": "Updated"}
    finally:
        db.close()

@app.post("/user/{username}/follow")
async def toggle_follow(request: Request, username: str):
    current_user = get_user_from_session(request)
    if not current_user: raise HTTPException(status_code=401)
    if current_user == username: return {"message": "Cannot follow self", "following": False}

    db = SessionLocal()
    try:
        existing = db.query(Follow).filter(Follow.follower_id == current_user, Follow.followed_id == username).first()
        if existing:
            db.delete(existing)
            user_target = db.query(User).filter(User.username == username).first()
            if user_target: user_target.followers_count = max(0, user_target.followers_count - 1)
            me = db.query(User).filter(User.username == current_user).first()
            if me: me.following_count = max(0, me.following_count - 1)
            following = False
        else:
            db.add(Follow(follower_id=current_user, followed_id=username))
            user_target = db.query(User).filter(User.username == username).first()
            if user_target: user_target.followers_count += 1
            me = db.query(User).filter(User.username == current_user).first()
            if me: me.following_count += 1
            following = True
        
        db.commit()
        return {"following": following, "followers_count": user_target.followers_count if user_target else 0}
    finally:
        db.close()

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# Upload / Comments / Like
@app.post("/upload")
async def upload_video(request: Request, file: UploadFile = File(...), title: str = Form(...)):
    author = get_user_from_session(request)
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

from pydantic import BaseModel

class CommentModel(BaseModel):
    video_id: str
    text: str

@app.post("/comment")
async def comment_video(request: Request, comment: CommentModel):
    user = get_user_from_session(request)
    if not user: raise HTTPException(status_code=401)
    
    db = SessionLocal()
    vid = db.query(Video).filter(Video.id == comment.video_id).first()
    if not vid:
        db.close()
        raise HTTPException(404, "Video not found")
        
    db.add(Comment(text=comment.text, username=user, video_id=comment.video_id))
    db.commit()
    db.close()
    return {"status": "success", "user": user, "text": comment.text}

@app.get("/comments/{video_id}")
async def get_comments(video_id: str):
    db = SessionLocal()
    res = db.execute(text("SELECT c.text, c.username, u.profile_pic, u.is_pioneer FROM comments c LEFT JOIN users u ON c.username=u.username WHERE c.video_id=:v ORDER BY c.timestamp ASC"), {"v":video_id}).mappings().all()
    db.close()
    return [{"text":r["text"], "username":r["username"], "profile_pic":r["profile_pic"], "is_pioneer":r["is_pioneer"]} for r in res]

@app.post("/toggle_like/{video_id}")
async def toggle_like(request: Request, video_id: str):
    user = get_user_from_session(request)
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
