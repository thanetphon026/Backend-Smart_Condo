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

def validate_image(file):
    if not file:
        return False, "No file"
    if '.' not in file.filename or \
       file.filename.rsplit('.', 1)[1].lower() not in ALLOWED_EXTENSIONS:
        return False, "Invalid extension"
    return True, "OK"

def upload_image(file):
    try:
        res = cloudinary.uploader.upload(file, folder=Config.CLOUDINARY_UPLOAD_PRESET)
        return res.get('secure_url')
    except Exception as e:
        print(f"Upload Error: {e}")
        return None
