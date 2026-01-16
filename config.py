"""
Configuration Module - Smart Condo Backend
Handles environment variables and service configurations
"""
import os
from dotenv import load_dotenv
import cloudinary
from google import genai
from linebot.v3 import WebhookHandler
from linebot.v3.messaging import Configuration

# Load environment variables
load_dotenv()

# ================= ENVIRONMENT VARIABLES =================
MONGO_URI = os.getenv("MONGO_URI")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")

CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME")
CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY")
CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET")
CLOUDINARY_UPLOAD_PRESET = os.getenv("CLOUDINARY_UPLOAD_PRESET", "smart_condo")

API_TOKEN = os.getenv("API_TOKEN")

# ================= IMAGE VALIDATION SETTINGS =================
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'heic', 'heif'}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB

# ================= EXTERNAL SERVICE INITIALIZATION =================

# Gemini AI Client
gemini_client = genai.Client(api_key=GEMINI_API_KEY)

# LINE Bot Configuration
line_configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
line_handler = WebhookHandler(LINE_CHANNEL_SECRET)

# Cloudinary Configuration
cloudinary.config(
    cloud_name=CLOUDINARY_CLOUD_NAME,
    api_key=CLOUDINARY_API_KEY,
    api_secret=CLOUDINARY_API_SECRET,
    secure=True
)

# ================= HELPER FUNCTIONS =================

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def validate_image(file):
    """
    Validate image file (extension and size)
    Returns: (bool, str) - (is_valid, message)
    """
    if not file:
        return False, "ไม่มีไฟล์"
    
    if not allowed_file(file.filename):
        return False, f"นามสกุลไฟล์ไม่รองรับ (รองรับ: {', '.join(ALLOWED_EXTENSIONS)})"
    
    # Check file size
    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)  # Reset pointer
    
    if size > MAX_FILE_SIZE:
        return False, f"ไฟล์มีขนาดใหญ่เกินไป (สูงสุด {MAX_FILE_SIZE // (1024*1024)}MB)"
        
    return True, "OK"
