from flask import Blueprint, jsonify, request
from ..utils.db import audit_logs_col, parcels_col, users_col, chat_history_col
from ..utils.helpers import token_required
from ..utils.cloudinary_utils import delete_resource # Assuming this helper exists or needs to be created
import csv
import io
import datetime

maintenance_bp = Blueprint('maintenance', __name__)

@maintenance_bp.route('/api/maintenance/cleanup', methods=['POST'])
@token_required
def cleanup_old_data():
    """
    Deletes data older than 90 days.
    Trigger this via Cron Job (e.g. call this endpoint daily).
    """
    try:
        days = 90
        cutoff_date = datetime.datetime.utcnow() - datetime.timedelta(days=days)
        
        # 1. Cleanup Parcels
        # Find parcels to delete (status="received" AND older than 90 days)
        old_parcels = list(parcels_col.find({
            "status": "received",
            "timestamp": {"$lt": cutoff_date}
        }))
        
        deleted_parcels_count = 0
        for p in old_parcels:
            # Delete image from Cloudinary if exists
            if 'image_url' in p and p['image_url']:
                try:
                    # Extract public_id from URL: e.g. "http://.../folder/public_id.jpg"
                    # Cloudinary URLs usually have public_id between last "/" and "."
                    url_parts = p['image_url'].split('/')
                    if len(url_parts) > 0:
                        file_part = url_parts[-1]
                        public_id_with_ext = file_part.split('.')[0]
                        # If you use folders, you might need more complex logic. 
                        # Assuming 'smart_condo/public_id' format based on config.py
                        # Let's try to find if it's in the smart_condo folder
                        folder = "smart_condo" # Default from Config.CLOUDINARY_UPLOAD_PRESET
                        full_public_id = f"{folder}/{public_id_with_ext}"
                        delete_resource(full_public_id)
                except Exception as img_err:
                    print(f"Failed to delete image for parcel {p.get('_id')}: {img_err}")
            
            parcels_col.delete_one({"_id": p['_id']})
            deleted_parcels_count += 1
            
        # 2. Cleanup Chat History
        chat_result = chat_history_col.delete_many({
            "timestamp": {"$lt": cutoff_date}
        })
        
        # 3. Cleanup Audit Logs (Optional but good practice)
        log_result = audit_logs_col.delete_many({
            "timestamp": {"$lt": cutoff_date}
        })
        
        return jsonify({
            "status": "success",
            "message": f"Cleanup complete. Deleted {deleted_parcels_count} parcels, {chat_result.deleted_count} chats, {log_result.deleted_count} logs."
        })
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
