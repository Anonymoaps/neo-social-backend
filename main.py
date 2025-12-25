import shutil
import os
import uuid
import sqlite3
import random
from typing import Optional
from datetime import datetime

from fastapi import FastAPI, UploadFile, File, Form, Request, HTTPException, Response, Cookie
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# --- CONFIGURAÇÃO INICIAL (V-PWA) ---
app = FastAPI(title="NEO Social Engine V6", version="14.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pastas
os.makedirs("uploads", exist_ok=True)
os.makedirs("templates", exist_ok=True)
os.makedirs("static", exist_ok=True)

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# --- DATABASE SETUP (SQLITE) ---
DB_NAME = "neo.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # Tabela de Usuários
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                 username TEXT PRIMARY KEY,
                 created_at TEXT,
                 profile_pic TEXT
                 )''')

    # Tabela de Vídeos
    c.execute('''CREATE TABLE IF NOT EXISTS videos (
                 id TEXT PRIMARY KEY,
                 title TEXT,
                 url TEXT,
                 likes INTEGER DEFAULT 0,
                 filter_type TEXT,
                 author TEXT,
                 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                 FOREIGN KEY(author) REFERENCES users(username)
                 )''')

    # Tabela de Likes
    c.execute('''CREATE TABLE IF NOT EXISTS likes (
                 user_id TEXT,
                 video_id TEXT,
                 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                 PRIMARY KEY (user_id, video_id),
                 FOREIGN KEY(user_id) REFERENCES users(username),
                 FOREIGN KEY(video_id) REFERENCES videos(id)
                 )''')
                 
    # Tabela de Comentários
    c.execute('''CREATE TABLE IF NOT EXISTS comments (
                 id TEXT PRIMARY KEY,
                 user_id TEXT,
                 video_id TEXT,
                 text TEXT,
                 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                 FOREIGN KEY(user_id) REFERENCES users(username),
                 FOREIGN KEY(video_id) REFERENCES videos(id)
                 )''')
                 
    # Tabela de Follows (Quem segue quem)
    c.execute('''CREATE TABLE IF NOT EXISTS follows (
                 follower_id TEXT,
                 followed_id TEXT,
                 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                 PRIMARY KEY (follower_id, followed_id),
                 FOREIGN KEY(follower_id) REFERENCES users(username),
                 FOREIGN KEY(followed_id) REFERENCES users(username)
                 )''')
    
    conn.commit()
    conn.close()

# Inicializa o banco ao rodar
init_db()

# --- SESSIONS ---
active_sessions = {}

# --- HELPER ---
def get_user_from_session(token):
    return active_sessions.get(token)

# --- ENDPOINTS DE AUTH ---

@app.post("/login")
async def login(response: Response, username: str = Form(...)):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username=?", (username,))
    if not c.fetchone():
        c.execute("INSERT INTO users (username, created_at, profile_pic) VALUES (?, ?, ?)", 
                  (username, str(datetime.now()), None))
        conn.commit()
    conn.close()

    session_token = str(uuid.uuid4())
    active_sessions[session_token] = username
    response.set_cookie(key="neo_session", value=session_token)
    
    return {"message": "Logged in", "user": username}

@app.get("/me")
async def get_current_user(neo_session: Optional[str] = Cookie(None)):
    user = get_user_from_session(neo_session)
    if not user:
        return JSONResponse(content={"user": None}, status_code=401)
        
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT profile_pic FROM users WHERE username=?", (user,))
    row = c.fetchone()
    conn.close()
    
    profile_pic = row['profile_pic'] if row else None
    return {"user": user, "profile_pic": profile_pic}

# --- ENDPOINTS GERAIS ---

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/feed")
async def get_feed(type: str = "foryou", neo_session: Optional[str] = Cookie(None)):
    current_user = get_user_from_session(neo_session)
    
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    if type == "following" and current_user:
        query = """
            SELECT 
                v.*,
                u.profile_pic as author_pic,
                (SELECT COUNT(*) FROM likes WHERE video_id = v.id) as total_likes,
                (SELECT COUNT(*) FROM likes WHERE video_id = v.id AND user_id = ?) as user_liked,
                (SELECT COUNT(*) FROM comments WHERE video_id = v.id) as total_comments,
                (SELECT COUNT(*) FROM follows WHERE follower_id = ? AND followed_id = v.author) as is_following
            FROM videos v
            LEFT JOIN users u ON v.author = u.username
            WHERE v.author IN (SELECT followed_id FROM follows WHERE follower_id = ?)
            ORDER BY v.created_at DESC
        """
        c.execute(query, (current_user, current_user, current_user))
        
    else:
        # Default 'foryou'
        query = """
            SELECT 
                v.*,
                u.profile_pic as author_pic,
                (SELECT COUNT(*) FROM likes WHERE video_id = v.id) as total_likes,
                (SELECT COUNT(*) FROM likes WHERE video_id = v.id AND user_id = ?) as user_liked,
                (SELECT COUNT(*) FROM comments WHERE video_id = v.id) as total_comments,
                (SELECT COUNT(*) FROM follows WHERE follower_id = ? AND followed_id = v.author) as is_following
            FROM videos v
            LEFT JOIN users u ON v.author = u.username
            ORDER BY v.created_at DESC
        """
        c.execute(query, (current_user, current_user))
    
    rows = c.fetchall()
    conn.close()
    
    videos = []
    is_admin = (current_user == "@admin")
    for row in rows:
        videos.append({
            "id": row["id"],
            "title": row["title"],
            "url": row["url"],
            "likes": row["total_likes"],
            "comments": row["total_comments"],
            "user_has_liked": row["user_liked"] > 0,
            "filter_type": row["filter_type"],
            "author": row["author"],
            "author_pic": row["author_pic"],
            "is_following": row["is_following"] > 0,
            "is_own_video": (row["author"] == current_user) if current_user else False,
            "can_delete": (row["author"] == current_user) or is_admin if current_user else False
        })

    return JSONResponse(content=videos)

@app.get("/profile/{username}")
async def get_profile(username: str, neo_session: Optional[str] = Cookie(None)):
    current_user = get_user_from_session(neo_session)
    
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # Busca User Info
    c.execute("SELECT * FROM users WHERE username=?", (username,))
    user_data = c.fetchone()
    if not user_data:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")

    # Estatísticas
    c.execute("SELECT COUNT(*) FROM follows WHERE followed_id=?", (username,))
    followers_count = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM follows WHERE follower_id=?", (username,))
    following_count = c.fetchone()[0]

    c.execute("""
        SELECT COUNT(*) 
        FROM likes l
        JOIN videos v ON l.video_id = v.id
        WHERE v.author = ?
    """, (username,))
    total_likes_count = c.fetchone()[0]

    is_following = False
    if current_user:
        c.execute("SELECT * FROM follows WHERE follower_id=? AND followed_id=?", (current_user, username))
        if c.fetchone():
            is_following = True

    # Busca vídeos
    c.execute("""
        SELECT 
            v.*,
            u.profile_pic as author_pic,
            (SELECT COUNT(*) FROM likes WHERE video_id = v.id) as total_likes,
            (SELECT COUNT(*) FROM likes WHERE video_id = v.id AND user_id = ?) as user_liked,
            (SELECT COUNT(*) FROM comments WHERE video_id = v.id) as total_comments
        FROM videos v
        LEFT JOIN users u ON v.author = u.username
        WHERE v.author = ?
        ORDER BY v.created_at DESC
    """, (current_user, username))
    
    rows = c.fetchall()
    conn.close()
    
    videos = []
    is_admin = (current_user == "@admin")
    for row in rows:
        videos.append({
            "id": row["id"],
            "title": row["title"],
            "url": row["url"],
            "likes": row["total_likes"],
            "comments": row["total_comments"],
            "user_has_liked": row["user_liked"] > 0,
            "filter_type": row["filter_type"],
            "author": row["author"],
            "author_pic": row["author_pic"],
            "can_delete": (row["author"] == current_user) or is_admin if current_user else False
        })
        
    return JSONResponse(content={
        "username": username, 
        "profile_pic": user_data['profile_pic'],
        "followers_count": followers_count,
        "following_count": following_count,
        "total_likes": total_likes_count,
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

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT * FROM follows WHERE follower_id=? AND followed_id=?", (follower, target_username))
    existing = c.fetchone()
    
    is_following = False
    if existing:
        c.execute("DELETE FROM follows WHERE follower_id=? AND followed_id=?", (follower, target_username))
        is_following = False
    else:
        c.execute("INSERT INTO follows (follower_id, followed_id) VALUES (?, ?)", (follower, target_username))
        is_following = True
        
    c.execute("SELECT COUNT(*) FROM follows WHERE followed_id=?", (target_username,))
    count = c.fetchone()[0]
    conn.commit()
    conn.close()
    return {"following": is_following, "followers_count": count}


# --- SOCIAL ACTIONS ---

@app.post("/upload_avatar")
async def upload_avatar(file: UploadFile = File(...), neo_session: Optional[str] = Cookie(None)):
    user = get_user_from_session(neo_session)
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
        
    file_ext = file.filename.split(".")[-1]
    filename = f"avatar_{user}_{uuid.uuid4()}.{file_ext}"
    file_path = f"uploads/{filename}"
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE users SET profile_pic = ? WHERE username = ?", (f"/uploads/{filename}", user))
    conn.commit()
    conn.close()
    
    return {"message": "Avatar updated", "url": f"/uploads/{filename}"}

@app.post("/toggle_like/{video_id}")
async def toggle_like(video_id: str, neo_session: Optional[str] = Cookie(None)):
    user = get_user_from_session(neo_session)
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
        
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT * FROM likes WHERE user_id=? AND video_id=?", (user, video_id))
    existing_like = c.fetchone()
    
    liked = False
    if existing_like:
        c.execute("DELETE FROM likes WHERE user_id=? AND video_id=?", (user, video_id))
        liked = False
    else:
        c.execute("INSERT INTO likes (user_id, video_id) VALUES (?, ?)", (user, video_id))
        liked = True
    conn.commit()
    c.execute("SELECT COUNT(*) FROM likes WHERE video_id=?", (video_id,))
    count = c.fetchone()[0]
    conn.close()
    return {"liked": liked, "count": count}

# --- COMMENTS ---

@app.get("/comments/{video_id}")
async def get_comments(video_id: str):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT c.*, u.profile_pic 
        FROM comments c
        LEFT JOIN users u ON c.user_id = u.username
        WHERE c.video_id = ?
        ORDER BY c.created_at ASC
    """, (video_id,))
    rows = c.fetchall()
    conn.close()
    
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
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO comments (id, user_id, video_id, text) VALUES (?, ?, ?, ?)", 
              (comment_id, user, video_id, text))
    conn.commit()
    conn.close()
    
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT profile_pic FROM users WHERE username=?", (user,))
    u_row = c.fetchone()
    conn.close()
    
    return {
        "id": comment_id,
        "user_id": user,
        "text": text,
        "profile_pic": u_row['profile_pic'] if u_row else None
    }


# --- UPLOAD & REMIX ---

@app.post("/upload")
async def upload_video(
    file: UploadFile = File(...), 
    title: str = Form(...),
    neo_session: Optional[str] = Cookie(None)
):
    author = get_user_from_session(neo_session) or "Anonymous"
    try:
        file_ext = file.filename.split(".")[-1]
        video_id = str(uuid.uuid4())
        filename = f"{video_id}.{file_ext}"
        file_path = f"uploads/{filename}"
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("INSERT INTO videos (id, title, url, likes, filter_type, author) VALUES (?, ?, ?, ?, ?, ?)", 
                  (video_id, title, f"/uploads/{filename}", 0, None, author))
        conn.commit()
        conn.close()
        new_video = {
            "id": video_id,
            "title": title,
            "url": f"/uploads/{filename}",
            "likes": 0,
            "comments": 0,
            "user_has_liked": False,
            "filter_type": None,
            "author": author,
            "author_pic": None,
            # Defaults for upload response
            "is_following": False,
            "is_own_video": True
        }
        return JSONResponse(content={"message": "Upload success", "video": new_video}, status_code=200)
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)

@app.post("/remix/{video_id}")
async def remix_video(video_id: str, style: str = "cyberpunk", neo_session: Optional[str] = Cookie(None)):
    author = get_user_from_session(neo_session) or "VisualEngine"
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM videos WHERE id=?", (video_id,))
    original = c.fetchone()
    if not original:
        conn.close()
        raise HTTPException(status_code=404, detail="Video not found")
    new_id = str(uuid.uuid4())
    new_title = f"[{style.upper()}] {original['title']}"
    c.execute("INSERT INTO videos (id, title, url, likes, filter_type, author) VALUES (?, ?, ?, ?, ?, ?)", 
              (new_id, new_title, original['url'], 0, style, str(author)))
    conn.commit()
    conn.close()
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT profile_pic FROM users WHERE username=?", (author,))
    pic = c.fetchone()
    conn.close()

    new_video = {
        "id": new_id,
        "title": new_title,
        "url": original['url'],
        "likes": 0,
        "comments": 0,
        "user_has_liked": False,
        "filter_type": style,
        "author": str(author),
        "author_pic": pic[0] if pic else None,
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
        
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT author, url FROM videos WHERE id=?", (video_id,))
    video = c.fetchone()
    
    if not video:
        conn.close()
        raise HTTPException(status_code=404, detail="Video not found")
        
    if video['author'] != user and user != "@admin":
        conn.close()
        raise HTTPException(status_code=403, detail="Not authorized")
        
    # Deletar do banco
    c.execute("DELETE FROM likes WHERE video_id=?", (video_id,))
    c.execute("DELETE FROM comments WHERE video_id=?", (video_id,))
    c.execute("DELETE FROM videos WHERE id=?", (video_id,))
    conn.commit()
    conn.close()
    
    # Deletar arquivo (opcional, cuidado se for remix que compartilha arquivo)
    # Na implementação atual, remixes copiam a URL, mas não duplicam o arquivo físico.
    # Então deletar o arquivo físico pode quebrar outros remixes se eles apontarem pro mesmo arquivo.
    # Vamos manter simples: Deletamos o registro. Se quiser deletar arquivo, teria que checar uso.
    # Pra esse MVP, deletar o registro é suficiente pra sumir do app.
    
    return {"message": "Video deleted"}

from pyngrok import ngrok
import uvicorn

@app.on_event("startup")
async def startup_event():
    # Encerra túneis anteriores para evitar conflitos
    ngrok.kill()
    
    # FORÇA a autenticação com o token fornecido
    # (Isso resolve problemas de PATH ou config file não encontrado)
    ngrok.set_auth_token("37JzD4nOOK0mtW7NS8eb5DDLjhE_4sCu3RoUSVLB5Z9CpnCa4")
    
    try:
        # Abre um túnel HTTP na porta 8000
        public_url = ngrok.connect(8000).public_url
        print("\n\n" + "⭐"*30)
        print(f"🚀 LINK PÚBLICO GERADO: {public_url}")
        print("📲 Abra este link no seu celular para instalar o PWA!")
        print("⭐"*30 + "\n\n")
    except Exception as e:
        print("\n\n" + "!"*60)
        print(f"⚠️ NGROK FALHOU: {e}")
        print("O servidor continuará rodando localmente.")
        print("🚀 ACESSO LOCAL: http://10.0.0.189:8000")
        print("!"*60 + "\n\n")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
