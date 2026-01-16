from pymongo import MongoClient
from ..config import Config

mongo_client = MongoClient(Config.MONGO_URI)
db = mongo_client["smart_condo"]

# Collections
users_col = db["users"]
parcels_col = db["parcels"]
kb_col = db["knowledge_base"]
admins_col = db["admins"]
audit_logs_col = db["audit_logs"]
chat_history_col = db["chat_history"]

def ensure_indexes():
    """Create MongoDB Indexes."""
    try:
        # Users
        users_col.create_index([("line_user_id", 1)], unique=True)
        users_col.create_index([("room_number", 1)])
        
        # Parcels
        parcels_col.create_index([("tracking_number", 1)])
        parcels_col.create_index([("pin", 1)], unique=True)
        parcels_col.create_index([("status", 1)])
        parcels_col.create_index([("is_after_hours", 1)])
        parcels_col.create_index([("timestamp", -1)])
        parcels_col.create_index([("room_number", 1)])
        
        # Knowledge Base (Vector/Text Search)
        kb_col.create_index([
            ("topic", "text"),
            ("content", "text"),
            ("tags", "text")
        ])
        
        print("✅ MongoDB Indexes ensured.")
    except Exception as e:
        print(f"⚠️ Failed to create indexes: {e}")

def log_audit(action, performed_by, target=None, details=None):
    """
    Log an audit event.
    """
    import datetime
    try:
        log_entry = {
            "action": action,
            "performed_by": performed_by,
            "target": target,
            "timestamp": datetime.datetime.utcnow(),
            "details": details or ""
        }
        audit_logs_col.insert_one(log_entry)
        print(f"📝 Audit Log: {action} by {performed_by}")
    except Exception as e:
        print(f"❌ Audit Log Error: {e}")

def save_chat_history(line_user_id, role, message, platform="line", image_url=None):
    import datetime
    try:
        if role in ['assistant', 'model']:
            role = 'assistant'
            
        entry = {
            "line_user_id": line_user_id,
            "role": role,
            "message": message,
            "platform": platform,
            "image_url": image_url,
            "timestamp": datetime.datetime.utcnow()
        }
        chat_history_col.insert_one(entry)
    except Exception as e:
        print(f"❌ Chat History Error: {e}")
