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

def levenshtein_distance(s1, s2):
    """
    Simple Levenshtein distance for fuzzy matching.
    """
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)

    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]

def similarity_ratio(s1, s2):
    """
    Returns a similarity ratio between 0 and 1.
    """
    if not s1 or not s2:
        return 0
    distance = levenshtein_distance(s1, s2)
    max_len = max(len(s1), len(s2))
    return 1.0 - (distance / max_len)
