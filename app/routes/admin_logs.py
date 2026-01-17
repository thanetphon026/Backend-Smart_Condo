from flask import Blueprint, request, jsonify, Response
from ..utils.db import audit_logs_col, log_audit
from ..utils.helpers import token_required
import csv
import io

logs_bp = Blueprint('logs', __name__)

@logs_bp.route('/api/admin/logs', methods=['GET'])
@token_required
def get_logs():
    log_type = request.args.get('type', 'admin') # admin or user
    limit = int(request.args.get('limit', 20))
    
    query = {}
    if log_type == 'user':
        # Sync with webhook.py and admin_parcels actions
        query['action'] = {"$in": ["Register Outside", "User Scan", "Self Pickup Success", "Cancel Outside"]}
    else:
        # Admin Actions
        query['action'] = {"$nin": ["Register Outside", "User Scan", "Self Pickup Success", "Cancel Outside"]}

    logs = list(audit_logs_col.find(query).sort("timestamp", -1).limit(limit))
    for l in logs:
        l['_id'] = str(l['_id'])
        
    return jsonify({"status": "success", "data": logs})
    
@logs_bp.route('/api/admin/logs/export', methods=['GET'])
@token_required
def export_logs():
    log_type = request.args.get('type', 'admin')
    admin_name = request.headers.get('X-Admin-Name', 'Admin')
    
    query = {}
    if log_type == 'user':
        query['action'] = {"$in": ["User Register Outside Hours", "User Scan", "User Confirm Receive", "Self Pickup Success"]}
    else:
        query['action'] = {"$nin": ["User Register Outside Hours", "User Scan", "User Confirm Receive", "Self Pickup Success"]}
        
    logs = list(audit_logs_col.find(query).sort("timestamp", -1))
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Date', 'Performed By', 'Action', 'Target', 'Details'])
    
    for l in logs:
        dt = l.get('timestamp')
        date_str = dt.strftime('%Y-%m-%d %H:%M:%S') if dt else '-'
        
        writer.writerow([
            date_str,
            l.get('performed_by'),
            l.get('action'),
            l.get('target'),
            l.get('details')
        ])
        
    log_audit("Export Logs", admin_name, target="System", details=f"Exported {log_type} logs")

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename={log_type}_logs.csv"}
    )
