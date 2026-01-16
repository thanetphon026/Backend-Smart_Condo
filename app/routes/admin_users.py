from flask import Blueprint, jsonify
from ..utils.db import users_col

users_bp = Blueprint('users', __name__)

@users_bp.route('/api/admin/users', methods=['GET'])
def get_users():
    users = list(users_col.find().limit(50))
    for u in users:
        u['_id'] = str(u['_id'])
    return jsonify({"status": "success", "data": users})
