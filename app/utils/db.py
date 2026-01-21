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
        
        # Knowledge Base (Text Search)
        try:
            for index in kb_col.list_indexes():
                if any(v == 'text' for v in index['key'].values()):
                    if index['name'] != "rag_text_index":
                        print(f"🗑️ Dropping old text index: {index['name']}")
                        kb_col.drop_index(index['name'])
            
            kb_col.create_index([
                ("topic", "text"),
                ("content", "text"),
                ("tags", "text")
            ], name="rag_text_index", weights={"topic": 3, "content": 2, "tags": 1})
        except Exception as ie:
            print(f"⚠️ KB Index Note: {ie}")

        # Chat History
        chat_history_col.create_index([("line_user_id", 1), ("timestamp", -1)])
        
        print("✅ MongoDB Indexes ensured.")
    except Exception as e:
        print(f"⚠️ Failed to create indexes: {e}")

def log_audit(action, performed_by, target=None, details=None, metadata=None):
    """
    Enhanced audit logging with metadata and context.
    """
    import datetime
    from flask import request
    try:
        # Try to capture IP if in request context
        ip_address = None
        try:
            ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
        except:
            pass

        log_entry = {
            "action": action,
            "performed_by": performed_by,
            "target": target,
            "timestamp": datetime.datetime.utcnow(),
            "details": details or "",
            "metadata": metadata or {},
            "ip_address": ip_address
        }
        audit_logs_col.insert_one(log_entry)
        print(f"📝 Audit Log: {action} (IP: {ip_address})")
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
            "timestamp": datetime.datetime.now(datetime.timezone.utc)
        }
        
        # 1. Archive in full chat history
        chat_history_col.insert_one(entry)
        
        # 2. Update User's active context (Keep last 10 interactions)
        # We use $push with $slice -10 to keep only the last 10 elements.
        try:
            users_col.update_one(
                {"line_user_id": line_user_id},
                {
                    "$push": {
                        "history": {
                            "$each": [entry],
                            "$slice": -10
                        }
                    }
                }
            )
        except Exception as ue:
            print(f"⚠️ Failed to update user context history: {ue}")
            
    except Exception as e:
        print(f"❌ Chat History Error: {e}")
