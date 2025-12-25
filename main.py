import shutil
import os
import uuid
import random
from typing import Optional
from datetime import datetime

# --- CLOUDINARY & DB IMPORTS ---
import cloudinary
import cloudinary.uploader
from sqlalchemy import create_engine, text

from fastapi import FastAPI, UploadFile, File, Form, Request, HTTPException, Response, Cookie
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# --- CONFIGURAÇÃO INICIAL (V-CLOUD) ---
app = FastAPI(title="NEO Social Engine V-Cloud", version="15.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("templates", exist_ok=True)
os.makedirs("static", exist_ok=True)
# Pasta uploads removida da lógica principal (agora é tudo nuvem)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# --- DATABASE SETUP (POSTGRES OR SQLITE) ---
DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL:
    # Fix para Render/Heroku que usam postgres:// antigo
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
else:
    # Fallback local
    DATABASE_URL = "sqlite:///neo.db"

# Cria engine do SQLAlchemy
engine = create_engine(DATABASE_URL)

def init_db():
    with engine.connect() as conn:
        # Tabela de Usuários
        conn.execute(text('''CREATE TABLE IF NOT EXISTS users (
                     username TEXT PRIMARY KEY,
                     created_at TEXT,
                     profile_pic TEXT
                     )'''))

        # Tabela de Vídeos
        conn.execute(text('''CREATE TABLE IF NOT EXISTS videos (
                     id TEXT PRIMARY KEY,
                     title TEXT,
                     url TEXT,
                     likes INTEGER DEFAULT 0,
                     filter_type TEXT,
                     author TEXT,
                     created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                     FOREIGN KEY(author) REFERENCES users(username)
                     )'''))

        # Tabela de Likes
        conn.execute(text('''CREATE TABLE IF NOT EXISTS likes (
                     user_id TEXT,
                     video_id TEXT,
                     created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                     PRIMARY KEY (user_id, video_id),
                     FOREIGN KEY(user_id) REFERENCES users(username),
                     FOREIGN KEY(video_id) REFERENCES videos(id)
                     )'''))
                     
        # Tabela de Comentários
        conn.execute(text('''CREATE TABLE IF NOT EXISTS comments (
                     id TEXT PRIMARY KEY,
                     user_id TEXT,
                     video_id TEXT,
                     text TEXT,
                     created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                     FOREIGN KEY(user_id) REFERENCES users(username),
                     FOREIGN KEY(video_id) REFERENCES videos(id)
                     )'''))
                     
        # Tabela de Follows
        conn.execute(text('''CREATE TABLE IF NOT EXISTS follows (
                     follower_id TEXT,
                     followed_id TEXT,
                     created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                     PRIMARY KEY (follower_id, followed_id),
                     FOREIGN KEY(follower_id) REFERENCES users(username),
                     FOREIGN KEY(followed_id) REFERENCES users(username)
                     )'''))
        conn.commit()

init_db()

# --- CLOUDINARY SETUP ---
cloudinary.config( 
  cloud_name = os.getenv("CLOUD_NAME", ""), 
  api_key = os.getenv("CLOUD_API_KEY", ""), 
  api_secret = os.getenv("CLOUD_API_SECRET", ""),
  secure = True
)

# --- SESSIONS ---
active_sessions = {}

def get_user_from_session(token):
    return active_sessions.get(token)

# --- ENDPOINTS ---

@app.post("/login")
async def login(response: Response, username: str = Form(...)):
    with engine.connect() as conn:
        result = conn.execute(text("SELECT * FROM users WHERE username=:u"), {"u": username})
        if not result.fetchone():
            conn.execute(text("INSERT INTO users (username, created_at, profile_pic) VALUES (:u, :cat, :p)"), 
                         {"u": username, "cat": str(datetime.now()), "p": None})
            conn.commit()

    session_token = str(uuid.uuid4())
    active_sessions[session_token] = username
    response.set_cookie(key="neo_session", value=session_token)
    
    return {"message": "Logged in", "user": username}

@app.get("/me")
async def get_current_user(neo_session: Optional[str] = Cookie(None)):
    user = get_user_from_session(neo_session)
    if not user:
        return JSONResponse(content={"user": None}, status_code=401)
        
    with engine.connect() as conn:
        result = conn.execute(text("SELECT profile_pic FROM users WHERE username=:u"), {"u": user})
        row = result.fetchone()
    
    profile_pic = row[0] if row else None 
    return {"user": user, "profile_pic": profile_pic}

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/feed")
async def get_feed(type: str = "foryou", neo_session: Optional[str] = Cookie(None)):
    current_user = get_user_from_session(neo_session)
    
    with engine.connect() as conn:
        if type == "following" and current_user:
            query = text("""
                SELECT 
                    v.id, v.title, v.url, v.likes, v.filter_type, v.author, v.created_at,
                    u.profile_pic as author_pic,
                    (SELECT COUNT(*) FROM likes WHERE video_id = v.id) as total_likes,
                    (SELECT COUNT(*) FROM likes WHERE video_id = v.id AND user_id = :cu) as user_liked,
                    (SELECT COUNT(*) FROM comments WHERE video_id = v.id) as total_comments,
                    (SELECT COUNT(*) FROM follows WHERE follower_id = :cu AND followed_id = v.author) as is_following
                FROM videos v
                LEFT JOIN users u ON v.author = u.username
                WHERE v.author IN (SELECT followed_id FROM follows WHERE follower_id = :cu)
                ORDER BY v.created_at DESC
            """)
            result = conn.execute(query, {"cu": current_user})
        else:
            query = text("""
                SELECT 
                    v.id, v.title, v.url, v.likes, v.filter_type, v.author, v.created_at,
                    u.profile_pic as author_pic,
                    (SELECT COUNT(*) FROM likes WHERE video_id = v.id) as total_likes,
                    (SELECT COUNT(*) FROM likes WHERE video_id = v.id AND user_id = :cu) as user_liked,
                    (SELECT COUNT(*) FROM comments WHERE video_id = v.id) as total_comments,
                    (SELECT COUNT(*) FROM follows WHERE follower_id = :cu AND followed_id = v.author) as is_following
                FROM videos v
                LEFT JOIN users u ON v.author = u.username
                ORDER BY v.created_at DESC
            """)
            result = conn.execute(query, {"cu": current_user})
        
        rows = result.mappings().all()

    videos = []
    is_admin = (current_user == "@admin")
    for row in rows:
        videos.append({
            "id": row["id"],
            "title": row["title"],
            "url": row["url"],
            "likes": row["total_likes"],
            "comments": row["total_comments"],
            "user_has_liked": row["user_liked"] > 0 if row["user_liked"] else False, # handle none
            "filter_type": row["filter_type"],
            "author": row["author"],
            "author_pic": row["author_pic"],
            "is_following": row["is_following"] > 0 if row["is_following"] else False,
            "is_own_video": (row["author"] == current_user) if current_user else False,
            "can_delete": (row["author"] == current_user) or is_admin if current_user else False
        })

    return JSONResponse(content=videos)

@app.get("/profile/{username}")
async def get_profile(username: str, neo_session: Optional[str] = Cookie(None)):
    current_user = get_user_from_session(neo_session)
    
    with engine.connect() as conn:
        # Check user
        user_res = conn.execute(text("SELECT * FROM users WHERE username=:u"), {"u": username}).mappings().fetchone()
        if not user_res:
             raise HTTPException(status_code=404, detail="User not found")
        
        # Follower counts
        f1 = conn.execute(text("SELECT COUNT(*) FROM follows WHERE followed_id=:u"), {"u": username}).scalar()
        f2 = conn.execute(text("SELECT COUNT(*) FROM follows WHERE follower_id=:u"), {"u": username}).scalar()
        
        # Total Likes
        query_likes = text("""
            SELECT COUNT(*) 
            FROM likes l
            JOIN videos v ON l.video_id = v.id
            WHERE v.author = :u
        """)
        total_likes = conn.execute(query_likes, {"u": username}).scalar()
        
        # Is Following
        is_following = False
        if current_user:
            check = conn.execute(text("SELECT * FROM follows WHERE follower_id=:cu AND followed_id=:u"), 
                                 {"cu": current_user, "u": username}).fetchone()
            if check:
                is_following = True

        # Videos
        v_query = text("""
            SELECT 
                v.id, v.title, v.url, v.likes, v.filter_type, v.author, v.created_at,
                u.profile_pic as author_pic,
                (SELECT COUNT(*) FROM likes WHERE video_id = v.id) as total_likes,
                (SELECT COUNT(*) FROM likes WHERE video_id = v.id AND user_id = :cu) as user_liked,
                (SELECT COUNT(*) FROM comments WHERE video_id = v.id) as total_comments
            FROM videos v
            LEFT JOIN users u ON v.author = u.username
            WHERE v.author = :u
            ORDER BY v.created_at DESC
        """)
        v_rows = conn.execute(v_query, {"cu": current_user, "u": username}).mappings().all()

    videos = []
    is_admin = (current_user == "@admin")
    for row in v_rows:
        videos.append({
            "id": row["id"],
            "title": row["title"],
            "url": row["url"],
            "likes": row["total_likes"],
            "comments": row["total_comments"],
            "user_has_liked": row["user_liked"] > 0 if row["user_liked"] else False,
            "filter_type": row["filter_type"],
            "author": row["author"],
            "author_pic": row["author_pic"],
            "can_delete": (row["author"] == current_user) or is_admin if current_user else False
        })
        
    return JSONResponse(content={
        "username": username, 
        "profile_pic": user_res['profile_pic'],
        "followers_count": f1,
        "following_count": f2,
        "total_likes": total_likes,
        "is_following": is_following,
        "videos": videos
    })

@app.post("/toggle_follow/{target_username}")
async def toggle_follow(target_username: str, neo_session: Optional[str] = Cookie(None)):
    follower = get_user_from_session(neo_session)
    if not follower:
        raise HTTPException(status_code=401, detail="Login required")
    if follower == target_username:
         return {"following": False, "message": "Cannot follow self"}

    with engine.connect() as conn:
        check = conn.execute(text("SELECT * FROM follows WHERE follower_id=:f AND followed_id=:t"), 
                             {"f": follower, "t": target_username}).fetchone()
        
        is_following = False
        if check:
            conn.execute(text("DELETE FROM follows WHERE follower_id=:f AND followed_id=:t"), 
                         {"f": follower, "t": target_username})
            is_following = False
        else:
            conn.execute(text("INSERT INTO follows (follower_id, followed_id) VALUES (:f, :t)"), 
                         {"f": follower, "t": target_username})
            is_following = True
        
        conn.commit()
        count = conn.execute(text("SELECT COUNT(*) FROM follows WHERE followed_id=:t"), 
                             {"t": target_username}).scalar()

    return {"following": is_following, "followers_count": count}

@app.post("/upload_avatar")
async def upload_avatar(file: UploadFile = File(...), neo_session: Optional[str] = Cookie(None)):
    user = get_user_from_session(neo_session)
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
    
    # Cloudinary Upload (Avatar = Image)
    try:
        upload_result = cloudinary.uploader.upload(file.file, resource_type="image", folder="neo_avatars")
        secure_url = upload_result["secure_url"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cloudinary error: {str(e)}")

    with engine.connect() as conn:
        conn.execute(text("UPDATE users SET profile_pic = :url WHERE username = :u"), 
                     {"url": secure_url, "u": user})
        conn.commit()
    
    return {"message": "Avatar updated", "url": secure_url}

@app.post("/toggle_like/{video_id}")
async def toggle_like(video_id: str, neo_session: Optional[str] = Cookie(None)):
    user = get_user_from_session(neo_session)
    if not user:
        raise HTTPException(status_code=401, detail="Login required")

    with engine.connect() as conn:
        check = conn.execute(text("SELECT * FROM likes WHERE user_id=:u AND video_id=:v"), 
                             {"u": user, "v": video_id}).fetchone()
        liked = False
        if check:
            conn.execute(text("DELETE FROM likes WHERE user_id=:u AND video_id=:v"), 
                         {"u": user, "v": video_id})
            liked = False
        else:
            conn.execute(text("INSERT INTO likes (user_id, video_id) VALUES (:u, :v)"), 
                         {"u": user, "v": video_id})
            liked = True
        conn.commit()
        
        count = conn.execute(text("SELECT COUNT(*) FROM likes WHERE video_id=:v"), 
                             {"v": video_id}).scalar()

    return {"liked": liked, "count": count}

@app.get("/comments/{video_id}")
async def get_comments(video_id: str):
    with engine.connect() as conn:
        query = text("""
            SELECT c.id, c.user_id, c.text, u.profile_pic 
            FROM comments c
            LEFT JOIN users u ON c.user_id = u.username
            WHERE c.video_id = :v
            ORDER BY c.created_at ASC
        """)
        rows = conn.execute(query, {"v": video_id}).mappings().all()

    comments = []
    for row in rows:
        comments.append({
            "id": row['id'],
            "user_id": row['user_id'],
            "text": row['text'],
            "profile_pic": row['profile_pic']
        })
    return JSONResponse(content=comments)

@app.post("/comment")
async def post_comment(video_id: str = Form(...), text: str = Form(...), neo_session: Optional[str] = Cookie(None)):
    user = get_user_from_session(neo_session)
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
        
    comment_id = str(uuid.uuid4())
    
    with engine.connect() as conn:
        conn.execute(text("INSERT INTO comments (id, user_id, video_id, text) VALUES (:id, :u, :v, :t)"), 
                     {"id": comment_id, "u": user, "v": video_id, "t": text})
        conn.commit()
        
        # Get author pic
        pic = conn.execute(text("SELECT profile_pic FROM users WHERE username=:u"), {"u": user}).scalar()

    return {
        "id": comment_id,
        "user_id": user,
        "text": text,
        "profile_pic": pic
    }

@app.post("/upload")
async def upload_video(
    file: UploadFile = File(...), 
    title: str = Form(...),
    neo_session: Optional[str] = Cookie(None)
):
    author = get_user_from_session(neo_session) or "Anonymous"
    
    try:
        # Upload direto para Cloudinary (Video)
        upload_result = cloudinary.uploader.upload(file.file, resource_type="video", folder="neo_videos")
        secure_url = upload_result["secure_url"]
        
        video_id = str(uuid.uuid4())
        
        with engine.connect() as conn:
            conn.execute(text("INSERT INTO videos (id, title, url, likes, filter_type, author) VALUES (:id, :t, :url, 0, NULL, :author)"), 
                         {"id": video_id, "t": title, "url": secure_url, "author": author})
            conn.commit()

        new_video = {
            "id": video_id,
            "title": title,
            "url": secure_url,
            "likes": 0,
            "comments": 0,
            "user_has_liked": False,
            "filter_type": None,
            "author": author,
            "author_pic": None,
            "is_following": False,
            "is_own_video": True,
            "can_delete": True
        }
        return JSONResponse(content={"message": "Upload success", "video": new_video}, status_code=200)
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)

@app.post("/remix/{video_id}")
async def remix_video(video_id: str, style: str = "cyberpunk", neo_session: Optional[str] = Cookie(None)):
    author = get_user_from_session(neo_session) or "VisualEngine"
    
    with engine.connect() as conn:
        original = conn.execute(text("SELECT * FROM videos WHERE id=:v"), {"v": video_id}).mappings().fetchone()
        if not original:
             raise HTTPException(status_code=404, detail="Video not found")
        
        new_id = str(uuid.uuid4())
        new_title = f"[{style.upper()}] {original['title']}"
        
        # O Remix cria um novo registro apontando para a MESMA url (economiza storage)
        conn.execute(text("INSERT INTO videos (id, title, url, likes, filter_type, author) VALUES (:id, :t, :url, 0, :s, :a)"), 
                     {"id": new_id, "t": new_title, "url": original['url'], "s": style, "a": str(author)})
        conn.commit()
        
        pic = conn.execute(text("SELECT profile_pic FROM users WHERE username=:u"), {"u": author}).scalar()

    new_video = {
        "id": new_id,
        "title": new_title,
        "url": original['url'],
        "likes": 0,
        "comments": 0,
        "user_has_liked": False,
        "filter_type": style,
        "author": str(author),
        "author_pic": pic,
        "is_following": False,
        "is_own_video": True,
        "can_delete": True
    }
    return JSONResponse(content={"message": "Filter Applied", "video": new_video})

@app.delete("/delete_video/{video_id}")
async def delete_video(video_id: str, neo_session: Optional[str] = Cookie(None)):
    user = get_user_from_session(neo_session)
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
        
    with engine.connect() as conn:
        video = conn.execute(text("SELECT author FROM videos WHERE id=:v"), {"v": video_id}).mappings().fetchone()
        
        if not video:
             raise HTTPException(status_code=404, detail="Video not found")
        
        if video['author'] != user and user != "@admin":
             raise HTTPException(status_code=403, detail="Not authorized")
             
        # Cascading deletes
        conn.execute(text("DELETE FROM likes WHERE video_id=:v"), {"v": video_id})
        conn.execute(text("DELETE FROM comments WHERE video_id=:v"), {"v": video_id})
        conn.execute(text("DELETE FROM videos WHERE id=:v"), {"v": video_id})
        conn.commit()
    
    return {"message": "Video deleted from DB"}

# --- NGROK / STARTUP ---
from pyngrok import ngrok

@app.on_event("startup")
async def startup_event():
    # Only use ngrok if NOT in cloud env (checked by presence of DATABASE_URL)
    # This prevents Render from trying to use ngrok which might fail due to no token in env or simple redundancy
    pass

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
