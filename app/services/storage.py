import boto3
from botocore.exceptions import NoCredentialsError, ClientError
from fastapi import UploadFile, HTTPException
import uuid
import shutil
import os
from ..core.config import settings

class StorageService:
    def __init__(self):
        # Initialize boto3 client for S3/R2
        # In a real scenario, we would use the credentials from settings
        # self.s3_client = boto3.client(
        #     's3',
        #     endpoint_url=settings.R2_ENDPOINT_URL,
        #     aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        #     aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY
        # )
        self.upload_dir = "uploads_mock"
        os.makedirs(self.upload_dir, exist_ok=True)

    async def upload_video(self, file: UploadFile) -> str:
        """
        Uploads a video file.
        In this mock implementation, it saves to a local folder but simulates the S3 interface interface.
        Returns the public URL of the uploaded video.
        """
        
        # 1. Validate File Type
        if file.content_type not in ["video/mp4", "video/quicktime"]:
            raise HTTPException(status_code=400, detail="Invalid file format. Only MP4 and MOV are allowed.")
        
        # 2. Rename file with UUID
        file_extension = file.filename.split(".")[-1]
        new_filename = f"{uuid.uuid4()}.{file_extension}"
        
        # 3. Simulate S3 Upload (Saving locally for now)
        try:
            file_path = os.path.join(self.upload_dir, new_filename)
            
            # Using shutil to save the file
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
                
            # Simulate public URL generation
            # In production this would be: f"https://{settings.R2_BUCKET_NAME}.r2.cloudflarestorage.com/{new_filename}" 
            return f"/static/{new_filename}"

        except Exception as e:
            print(f"Error uploading file: {e}")
            raise HTTPException(status_code=500, detail="Could not upload video.")
        finally:
            file.file.close()

storage = StorageService()
