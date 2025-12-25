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
    allow_credentials=True, # Permitir credenciais para cookies
)

os.makedirs("templates", exist_ok=True)
os.makedirs("static", exist_ok=True)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# --- DATABASE SETUP (POSTGRES OR SQLITE) ---
DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL:
    # Fix para Render/Heroku que usam postgres:// antigo
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    engine = create_engine(DATABASE_URL)
else:
    # Fallback local
    DATABASE_URL = "sqlite:///neo.db"
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

# --- SUPER BLINDAGEM DE BANCO ---
# Garante que a coluna existe antes de QUALQUER coisa
try:
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_pioneer BOOLEAN DEFAULT FALSE;"))
        conn.commit()
    print("✅ Coluna 'is_pioneer' verificada/criada com sucesso.")
except Exception as e:
    print(f"⚠️ Aviso de verificação de tabela (pode ser SQLite ou erro de permissão): {e}")

# --- CLOUDINARY SETUP ---
# Não remover nem alterar credenciais conforme solicitado
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
    is_pioneer = Column(Boolean, default=False) # Lógica de Pioneiro

class Video(Base):
    __tablename__ = "videos"
    id = Column(String, primary_key=True)
    title = Column(String)
    url = Column(String)
    likes = Column(Integer, default=0)
    filter_type = Column(String, nullable=True)
    author = Column(String, ForeignKey("users.username"))
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
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

# Init ORM
Base.metadata.create_all(bind=engine)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- SESSIONS (Cookie) ---
active_sessions = {}

def get_user_from_session(token):
    return active_sessions.get(token)

# --- ENDPOINTS ---

@app.post("/login")
async def login(response: Response, username: str = Form(...)): # Suporta Google Login enviando username = email
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        if not user:
            # Check for Pioneer status (First 1000 users)
            user_count = db.query(User).count()
            is_pioneer = True if user_count < 1000 else False
            
            new_user = User(
                username=username, 
                created_at=str(datetime.now()), 
                profile_pic=None,
                is_pioneer=is_pioneer
            )
            db.add(new_user)
            db.commit()
            print(f"New user {username} created. Pioneer: {is_pioneer}")
        
        session_token = str(uuid.uuid4())
        active_sessions[session_token] = username
        
        # Cookie seguro
        response.set_cookie(
            key="neo_session", 
            value=session_token, 
            httponly=True, 
            samesite='lax', 
            max_age=3600*24*7 # 7 dias
        )
        
        return {"message": "Logged in", "user": username}
    except Exception as e:
        print(f"Login error: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
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
        if user:
            return {
                "user": user.username, 
                "profile_pic": user.profile_pic,
                "is_pioneer": user.is_pioneer # Agora seguro pois a coluna existe
            }
        return {"user": user_name, "profile_pic": None}
    finally:
        db.close()

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/feed")
async def get_feed(type: str = "foryou", neo_session: Optional[str] = Cookie(None)):
    current_user = get_user_from_session(neo_session)
    # Garante que None seja tratado explicitamente, embora SQL 'user_id = NULL' já retorne 0
    user_param = current_user if current_user else "" 
    
    with engine.connect() as conn:
        # Simplifiquei a query para garantir compatibilidade
        query = text("""
            SELECT 
                v.id, v.title, v.url, v.filter_type, v.author, v.created_at,
                u.profile_pic as author_pic, u.is_pioneer as author_is_pioneer,
                (SELECT COUNT(*) FROM likes WHERE video_id = v.id) as total_likes,
                (SELECT COUNT(*) FROM likes WHERE video_id = v.id AND user_id = :cu) as user_liked,
                (SELECT COUNT(*) FROM comments WHERE video_id = v.id) as total_comments
            FROM videos v
            LEFT JOIN users u ON v.author = u.username
            ORDER BY v.created_at DESC
        """)
        # Passa parâmetro seguro
        result = conn.execute(query, {"cu": user_param})
        rows = result.mappings().all()

    videos = []
    is_admin = (current_user == "@admin")
    
    db = SessionLocal()
    for row in rows:
        # Fetch Top 3 Comments for preview
        c_objs = db.query(Comment).filter(Comment.video_id == row["id"]).order_by(Comment.timestamp.desc()).limit(3).all()
        preview_comments = [{"text": c.text, "username": c.username} for c in c_objs]

        videos.append({
            "id": row["id"],
            "title": row["title"],
            "url": row["url"],
            "likes": row["total_likes"],
            "comments_count": row["total_comments"],
            "preview_comments": preview_comments,
            "user_has_liked": row["user_liked"] > 0 if row["user_liked"] else False, 
            "filter_type": row["filter_type"],
            "author": row["author"],
            "author_pic": row["author_pic"],
            "author_is_pioneer": row["author_is_pioneer"], # Exibir selo no front
            "is_own_video": (row["author"] == current_user) if current_user else False,
            "can_delete": (row["author"] == current_user) or is_admin if current_user else False
        })
    db.close()

    return JSONResponse(content=videos)

# Rota Unificada de Upload
@app.post("/upload")
async def upload_video(
    file: UploadFile = File(...), 
    title: str = Form(...),
    neo_session: Optional[str] = Cookie(None)
):
    author = get_user_from_session(neo_session)
    if not author:
        raise HTTPException(status_code=401, detail="Por favor, faça login para postar.")
    
    try:
        # Upload para Cloudinary
        print(f"Iniciando upload para Cloudinary: {title}")
        upload_result = cloudinary.uploader.upload(file.file, resource_type="video", folder="neo_videos")
        secure_url = upload_result["secure_url"]
        
        video_id = str(uuid.uuid4())
        
        db = SessionLocal()
        new_video = Video(
            id=video_id,
            title=title,
            url=secure_url,
            author=author
        )
        db.add(new_video)
        db.commit()
        db.close()
        
        return JSONResponse(content={"message": "Upload realizado com sucesso!", "url": secure_url})
    except Exception as e:
        print(f"Erro no upload: {str(e)}")
        return JSONResponse(content={"error": f"Falha no upload: {str(e)}"}, status_code=500)

@app.post("/video/{video_id}/comment")
async def comment_video(
    video_id: str, 
    text: str = Form(...), 
    neo_session: Optional[str] = Cookie(None)
):
    user = get_user_from_session(neo_session)
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
        
    db = SessionLocal()
    try:
        new_comment = Comment(
            text=text,
            username=user,
            video_id=video_id
        )
        db.add(new_comment)
        db.commit()
        return {"message": "Comentário adicionado", "user": user, "text": text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.get("/comments/{video_id}")
async def get_comments(video_id: str):
    db = SessionLocal()
    try:
        comments = db.query(Comment).filter(Comment.video_id == video_id).order_by(Comment.timestamp.asc()).all()
        result = []
        for c in comments:
            # Buscar info extra do usuário (pic, pioneer) se quiser
            u = db.query(User).filter(User.username == c.username).first()
            result.append({
                "id": c.id,
                "text": c.text,
                "username": c.username,
                "profile_pic": u.profile_pic if u else None,
                "is_pioneer": u.is_pioneer if u else False
            })
        return JSONResponse(content=result)
    finally:
        db.close()

# Rota para deletar vídeo (Admin ou Dono)
@app.delete("/delete_video/{video_id}")
async def delete_video(video_id: str, neo_session: Optional[str] = Cookie(None)):
    user = get_user_from_session(neo_session)
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
        
    db = SessionLocal()
    try:
        video = db.query(Video).filter(Video.id == video_id).first()
        if not video:
             raise HTTPException(status_code=404, detail="Video not found")
        
        if video.author != user and user != "@admin":
             raise HTTPException(status_code=403, detail="Not authorized")
             
        db.delete(video)
        db.commit()
        return {"message": "Video deleted"}
    finally:
        db.close()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
