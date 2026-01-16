import os
import cloudinary
import cloudinary.uploader
from ..config import Config

cloudinary.config(
    cloud_name=Config.CLOUDINARY_CLOUD_NAME,
    api_key=Config.CLOUDINARY_API_KEY,
    api_secret=Config.CLOUDINARY_API_SECRET,
    secure=True
)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'heic', 'heif'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

def validate_image(file):
    if not file:
        return False, "No file uploaded"
    
    # Check extension
    filename = file.filename.lower()
    if '.' not in filename or \
       filename.rsplit('.', 1)[1] not in ALLOWED_EXTENSIONS:
        return False, f"Invalid file type. Supported: {', '.join(ALLOWED_EXTENSIONS).upper()}"
    
    # Check size
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0) # Reset pointer
    
    if file_size > MAX_FILE_SIZE:
        return False, f"File too large. Maximum size is 10MB (Current: {file_size / (1024*1024):.1f}MB)"
        
    return True, "OK"

def upload_image(file):
    try:
        res = cloudinary.uploader.upload(file, folder=Config.CLOUDINARY_UPLOAD_PRESET)
        return res.get('secure_url')
    except Exception as e:
        print(f"Upload Error: {e}")
        return None

def delete_resource(public_id):
    """
    Delete resource from Cloudinary by Public ID.
    """
    try:
        if public_id:
            cloudinary.uploader.destroy(public_id)
            return True
        return False
    except Exception as e:
        print(f"Delete Error: {e}")
        return False
