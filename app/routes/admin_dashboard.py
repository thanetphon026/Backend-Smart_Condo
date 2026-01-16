from flask import Blueprint, jsonify
from ..utils.db import parcels_col, users_col

dashboard_bp = Blueprint('dashboard', __name__)

def get_bkk_time():
    import datetime
    import pytz
    tz = pytz.timezone('Asia/Bangkok')
    return datetime.datetime.now(tz)

@dashboard_bp.route('/api/admin/dashboard/stats', methods=['GET'])
def get_stats():
    try:
        total_parcels = parcels_col.count_documents({})
        
        in_time_all = parcels_col.count_documents({"is_after_hours": False})
        in_time_received = parcels_col.count_documents({"is_after_hours": False, "status": "received"})
        
        outside_all = parcels_col.count_documents({"is_after_hours": True})
        outside_received = parcels_col.count_documents({"is_after_hours": True, "status": "received"})
        
        total_received = parcels_col.count_documents({"status": "received"})
        total_users = users_col.count_documents({})
        
        # System Status
        now = get_bkk_time()
        # Open 08:00 - 16:30
        start_time = now.replace(hour=8, minute=0, second=0, microsecond=0)
        end_time = now.replace(hour=16, minute=30, second=0, microsecond=0)
        is_registration_open = start_time <= now <= end_time
        
        return jsonify({
            "status": "success",
            "data": {
                "total_users": total_users,
                "total_parcels": total_parcels,
                "in_time_all": in_time_all,
                "in_time_received": in_time_received,
                "outside_all": outside_all,
                "outside_received": outside_received,
                "total_received": total_received,
                "system_status": {
                    "registration_open": is_registration_open,
                    "server_time": now.isoformat()
                }
            }
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
