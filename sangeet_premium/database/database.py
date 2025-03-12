import sqlite3
import os
import logging

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

DB_PATH = os.path.join(os.getcwd() , "database_files" , "sangeet_database_main.db")
PLAYLIST_DB_PATH = os.path.join(os.getcwd(), "database_files", "playlists.db")





# Initialize SQLite database for caching
def init_lyrics_db():
    conn = sqlite3.connect(os.path.join(os.getcwd() , "database_files" , "lyrics_cache.db"))
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS lyrics_cache (
        song_id TEXT PRIMARY KEY,
        lyrics TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    conn.commit()
    conn.close()



def init_db():
    """Master database initialization function."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    try:
        # User Authentication Tables
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                full_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                totp_secret TEXT,
                twofa_method TEXT DEFAULT 'none',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Core History Table (for backward compatibility)
        c.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                song_id TEXT NOT NULL,
                played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                session_id TEXT NOT NULL,
                sequence_number INTEGER NOT NULL
            )
        """)
        
        # User-specific History
        c.execute("""
            CREATE TABLE IF NOT EXISTS user_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                song_id TEXT NOT NULL,
                played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                session_id TEXT NOT NULL,
                sequence_number INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        
        # Core Downloads Table (for backward compatibility)
        c.execute("""
            CREATE TABLE IF NOT EXISTS downloads (
                video_id TEXT PRIMARY KEY,
                title TEXT,
                artist TEXT,
                album TEXT,
                path TEXT,
                downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # User-specific Downloads
        c.execute("""
            CREATE TABLE IF NOT EXISTS user_downloads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                video_id TEXT NOT NULL,
                title TEXT,
                artist TEXT,
                album TEXT,
                path TEXT,
                downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS song_metadata (
                song_id TEXT PRIMARY KEY,
                title TEXT,
                artist TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
                
        # Listening History
        c.execute("""
            CREATE TABLE IF NOT EXISTS listening_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                song_id TEXT NOT NULL,
                title TEXT,
                artist TEXT,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ended_at TIMESTAMP,
                duration INTEGER,
                listened_duration INTEGER,
                completion_rate FLOAT,
                session_id TEXT,
                listen_type TEXT CHECK(listen_type IN ('full', 'partial', 'skip')) DEFAULT 'partial'
            )
        """)
        
        # User Statistics
        c.execute("""
            CREATE TABLE IF NOT EXISTS user_stats (
                user_id INTEGER PRIMARY KEY,
                total_plays INTEGER DEFAULT 0,
                total_listened_time INTEGER DEFAULT 0,
                favorite_song_id TEXT,
                favorite_artist TEXT,
                last_played TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        
        # Analytics Tables
        c.execute("""
            CREATE TABLE IF NOT EXISTS daily_stats (
                date TEXT PRIMARY KEY,
                total_songs INTEGER DEFAULT 0,
                total_time INTEGER DEFAULT 0,
                unique_artists INTEGER DEFAULT 0,
                favorite_song_id TEXT,
                favorite_artist TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        c.execute("""
            CREATE TABLE IF NOT EXISTS artist_stats (
                artist TEXT PRIMARY KEY,
                total_plays INTEGER DEFAULT 0,
                total_time INTEGER DEFAULT 0,
                first_played TIMESTAMP,
                last_played TIMESTAMP,
                favorite_song_id TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Session Management
        c.execute("""
            CREATE TABLE IF NOT EXISTS active_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                session_token TEXT UNIQUE NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        
        # OTP Management
        c.execute("""
            CREATE TABLE IF NOT EXISTS pending_otps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                otp TEXT NOT NULL,
                purpose TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL
            )
        """)
        
        # Create indexes for better performance
        c.execute("CREATE INDEX IF NOT EXISTS idx_history_session ON history(session_id, sequence_number)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_user_history_user ON user_history(user_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_user_downloads_user ON user_downloads(user_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_listening_history_user ON listening_history(user_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_listening_dates ON listening_history(started_at)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_listening_song ON listening_history(song_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_listening_completion ON listening_history(completion_rate)")
        
        conn.commit()
        logger.info("Database initialized successfully")
        
    except Exception as e:
        logger.error(f"Database initialization error: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()



def init_auth_db():
    """Initialize authentication-related database tables"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Users table
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            full_name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            totp_secret TEXT,
            twofa_method TEXT DEFAULT 'none',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Modify existing tables to include user_id
    c.execute("""
        CREATE TABLE IF NOT EXISTS user_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            song_id TEXT NOT NULL,
            played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            session_id TEXT NOT NULL,
            sequence_number INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    
    c.execute("""
        CREATE TABLE IF NOT EXISTS user_downloads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            video_id TEXT NOT NULL,
            title TEXT,
            artist TEXT,
            album TEXT,
            path TEXT,
            downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    
    # Session management
    c.execute("""
        CREATE TABLE IF NOT EXISTS active_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            session_token TEXT UNIQUE NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    
    # OTP storage for verification
    c.execute("""
        CREATE TABLE IF NOT EXISTS pending_otps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            otp TEXT NOT NULL,
            purpose TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL
        )
    """)
    
    conn.commit()
    conn.close()




def init_playlist_db():
    conn = sqlite3.connect(PLAYLIST_DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS playlists (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        name TEXT NOT NULL,
        is_public INTEGER DEFAULT 0,
        share_id TEXT UNIQUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS playlist_songs (
        playlist_id INTEGER,
        song_id TEXT,
        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (playlist_id) REFERENCES playlists(id)
    )''')
    conn.commit()
    conn.close()

