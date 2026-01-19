import datetime
import pytz
from flask import request, jsonify
from functools import wraps
from ..config import Config

def get_bkk_time():
    """Returns current time in Bangkok timezone."""
    tz = pytz.timezone('Asia/Bangkok')
    return datetime.datetime.now(tz)

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        # Check Authorization header
        if 'Authorization' in request.headers:
            token = request.headers['Authorization']
            if token.startswith('Bearer '):
                token = token.split(' ')[1]
        
        # Check Custom header
        if not token and 'X-API-Token' in request.headers:
            token = request.headers['X-API-Token']
            
        # Check Query String (for Export URLs)
        if not token:
            token = request.args.get('token')

        if not token or token != Config.API_TOKEN:
            return jsonify({
                "status": "error", 
                "message": "Unauthorized: Invalid or missing API Token"
            }), 401
            
        return f(*args, **kwargs)
    return decorated
