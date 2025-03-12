from flask import session, redirect
from functools import wraps
import sqlite3
import os

DB_PATH = os.path.join(os.getcwd(), "database_files", "sangeet_database_main.db")

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or 'session_token' not in session:
            return redirect('/login')
            
        # Verify session is still valid in database
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        c.execute("""
            SELECT 1 FROM active_sessions 
            WHERE user_id = ? AND session_token = ? 
            AND expires_at > CURRENT_TIMESTAMP
        """, (session['user_id'], session['session_token']))
        
        valid_session = c.fetchone()
        conn.close()
        
        if not valid_session:
            # Clear invalid session
            session.clear()
            return redirect("/login")
            
        return f(*args, **kwargs)
    return decorated_function