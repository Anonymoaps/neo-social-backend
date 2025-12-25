from fastapi import FastAPI, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from typing import List

from . import models, schemas, database
from .api import videos, remix

# Create tables on startup (for development simplicity)
models.Base.metadata.create_all(bind=database.engine)

app = FastAPI(title="Super App Video API", description="Backend for the next-gen video social network", version="0.1.0")

# Enable CORS for local testing
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allows all origins for testing
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount 'static' directory to serve uploaded files (Mock Storage)
import os
os.makedirs("uploads_mock", exist_ok=True)
app.mount("/static", StaticFiles(directory="uploads_mock"), name="static")

# Include Routers
app.include_router(videos.router, prefix="/videos", tags=["Videos"])
app.include_router(remix.router, prefix="/remix", tags=["AI Remix"])

# Dependency
def get_db():
    return database.get_db()

@app.get("/", tags=["Health"])
def read_root():
    return {"message": "Super App API is running 🚀"}

@app.get("/users/", response_model=List[schemas.UserResponse], tags=["Users"])
def read_users(skip: int = 0, limit: int = 100, db: Session = Depends(database.get_db)):
    users = db.query(models.User).offset(skip).limit(limit).all()
    return users
