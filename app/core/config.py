from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Super App Video"
    
    # Database
    DATABASE_URL: str = "postgresql://postgres:password@localhost/superapp_db"
    
    # Storage (Cloudflare R2 / S3)
    R2_ENDPOINT_URL: str = "https://<ACCOUNT_ID>.r2.cloudflarestorage.com"
    R2_ACCESS_KEY_ID: str = "mock_access_key"
    R2_SECRET_ACCESS_KEY: str = "mock_secret_key"
    R2_BUCKET_NAME: str = "superapp-videos"
    
    class Config:
        env_file = ".env"

settings = Settings()
