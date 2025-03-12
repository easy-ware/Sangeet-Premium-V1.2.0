# Flask Imports
from flask import (
    Blueprint, session, jsonify, send_file, url_for, render_template, 
    request, redirect, render_template_string, make_response, current_app
)

# External Libraries
from ytmusicapi import YTMusic
import sqlite3
import logging
import random
import time
import concurrent.futures
import json
import requests
import bcrypt
import yt_dlp
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timedelta
from threading import Thread
from functools import wraps, partial
from concurrent.futures import ThreadPoolExecutor

# Internal Imports
from ..utils import util
from sangeet_premium import var_templates

# Standard Library
import os
import secrets
import re
from flask import session, jsonify, request
import sqlite3
import secrets


local_songs = {}
bp = Blueprint('playback', __name__)  # Create a blueprint


PLAYLIST_DB_PATH = os.path.join(os.getcwd(), "database_files", "playlists.db")
ytmusic =YTMusic()
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)
DB_PATH = os.path.join(os.getcwd() , "database_files" , "sangeet_database_main.db")


# Load local JSON data once at startup
LOCAL_JSON_PATH = os.path.join(os.getcwd() , "locals" , "local.json")
try:
    with open(LOCAL_JSON_PATH, 'r', encoding='utf-8') as f:
        local_data = json.load(f)
except Exception as e:
    print(f"Error reading the JSON file: {e}")
    local_data = {}


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
def load_local_songs_from_file():
    """Load songs from a JSON file and append them to the local_songs dictionary."""
    global local_songs  # Make sure we're modifying the global dictionary
    
    # Generate the file path
    json_file_path = os.path.join(os.getcwd(), "locals", "local.json")
    
    # Check if the file exists
    if not os.path.isfile(json_file_path):
        print(f"JSON file not found at: {json_file_path}")
        return
    
    try:
        # Read the JSON file
        with open(json_file_path, "r", encoding="utf-8") as file:
            data = json.load(file)
        
        # Clear existing local songs to prevent duplicates
        local_songs.clear()
        
        # Validate and append the data
        if isinstance(data, dict):
            for key, song in data.items():
                if isinstance(song, dict) and {"id", "title", "artist", "album", "path", "thumbnail", "duration"}.issubset(song.keys()):
                    # Verify file exists before adding
                    if os.path.exists(song["path"]):
                        local_songs[key] = song
                    else:
                        print(f"Skipped missing file for key: {key}")
                else:
                    print(f"Skipped invalid song format for key: {key}")
                    
            print(f"Loaded {len(data)} songs from {json_file_path}.")
            
            # Update search cache to include local songs
            if "" in search_cache:
                # Get the timestamp from cache
                _, timestamp = search_cache[""]
                # Update cache with new local songs included
                search_cache[""] = (list(local_songs.values()), timestamp)
        else:
            print("Invalid JSON structure. Expected a dictionary.")
    except Exception as e:
        print(f"Error reading JSON file: {e}")

    return local_songs

from functools import lru_cache

@lru_cache(maxsize=1)
def get_default_songs():
    """Generate a cached list of default songs for empty queries."""
    # Load local songs (this assumes local_songs is already populated at startup)
    local_songs = load_local_songs_from_file()
    combined = []
    seen_ids = set()

    # Add local songs first
    for song in local_songs.values():
        if song["id"] not in seen_ids:
            combined.append(song)
            seen_ids.add(song["id"])

    return combined

CACHE_DURATION = 3600
search_cache = {}
song_cache = {}
lyrics_cache = {}

SERVER_DOMAIN = os.getenv('sangeet_backend', f'http://127.0.0.1:{os.getenv("port")}')
@bp.route('/')
@login_required
def home():
    return render_template("index.html")




@bp.route("/api/play-sequence/<song_id>/<action>")
@login_required
def api_play_sequence(song_id, action):
    """Enhanced previous/next handling with proper sequence tracking."""
    local_songs = load_local_songs_from_file()
    try:
        # Get current song's session and sequence info
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute("""
                SELECT session_id, sequence_number 
                FROM user_history
                WHERE song_id = ? AND user_id = ?
                ORDER BY played_at DESC
                LIMIT 1
            """, (song_id, session['user_id']))
            
            current = c.fetchone()
            if not current:
                return jsonify({"error": "Current song not found"}), 404
                
            session_id, seq_num = current

            if action == "previous":
                # Get previous song in sequence
                c.execute("""
                    SELECT song_id 
                    FROM user_history
                    WHERE session_id = ? 
                    AND sequence_number < ? 
                    AND user_id = ?
                    ORDER BY sequence_number DESC 
                    LIMIT 1
                """, (session_id, seq_num, session['user_id']))
                
                prev_song = c.fetchone()
                if not prev_song:
                    return jsonify({"error": "No previous song"}), 404
                    
                prev_id = prev_song[0]
                if prev_id.startswith("local-"):
                    meta = local_songs.get(prev_id)
                    if meta:
                        return jsonify(meta)
                    return jsonify({"error": "Local song not found"}), 404
                
                return util.get_song_info(prev_id)
                
            elif action == "next":
                # Get next song in sequence
                c.execute("""
                    SELECT song_id 
                    FROM user_history
                    WHERE session_id = ? 
                    AND sequence_number > ?
                    AND user_id = ? 
                    ORDER BY sequence_number ASC
                    LIMIT 1
                """, (session_id, seq_num, session['user_id']))
                
                next_song = c.fetchone()
                if next_song:
                    next_id = next_song[0]
                    if next_id.startswith("local-"):
                        meta = local_songs.get(next_id)
                        if meta:
                            return jsonify(meta)
                        return jsonify({"error": "Local song not found"}), 404
                    return util.get_song_info(next_id)
                else:
                    # If no next song in history, get recommendations
                    try:
                        # Get song info first for better recommendations
                        song_info = None
                        if song_id.startswith("local-"):
                            song_info = local_songs.get(song_id)
                        else:
                            song_info = ytmusic.get_song(song_id)

                        if not song_info:
                            return jsonify({"error": "Failed to get song info"}), 404

                        # Get recommendations based on song info
                        recommendations = ytmusic.get_watch_playlist(
                            videoId=song_id,
                            limit=5
                        )
                        
                        if recommendations and "tracks" in recommendations:
                            recs = []
                            for track in recommendations["tracks"]:
                                if track.get("videoId") == song_id:
                                    continue
                                    
                                recs.append({
                                    "id": track["videoId"],
                                    "title": track["title"],
                                    "artist": track["artists"][0]["name"] if track.get("artists") else "Unknown",
                                    "thumbnail": f"https://i.ytimg.com/vi/{track['videoId']}/hqdefault.jpg"
                                })
                                
                                if len(recs) >= 5:
                                    break
                                    
                            return jsonify(recs)

                    except Exception as e:
                        logger.error(f"Recommendation error: {e}")
                        
                    # Fallback to searching
                    return util.get_fallback_recommendations()
        
        return jsonify({"error": "Invalid action"}), 400
        
    except Exception as e:
        logger.error(f"Sequence error: {e}")
        return jsonify({"error": str(e)}), 500




@bp.route("/api/download/<song_id>")
@login_required
def api_download2(song_id):
    """Smart download handler that tries YouTube first for video ID-like names."""
    try:
        # Extract potential video ID
        potential_vid = song_id[6:] if song_id.startswith("local-") else song_id
        
        # First try YouTube if it looks like a video ID
        if util.is_potential_video_id(potential_vid):
            try:
                # Check if already downloaded
                existing_path = util.get_download_info(potential_vid)
                if existing_path and os.path.exists(existing_path):
                    # Get title from database
                    conn = sqlite3.connect(DB_PATH)
                    c = conn.cursor()
                    c.execute("SELECT title FROM downloads WHERE video_id = ?", (potential_vid,))
                    row = c.fetchone()
                    conn.close()
                    
                    if row and row[0]:
                        safe_title = util.sanitize_filename(row[0])
                        download_name = f"{safe_title}.flac"
                    else:
                        download_name = f"{potential_vid}.flac"
                        
                    return send_file(
                        existing_path,
                        as_attachment=True,
                        download_name=download_name,
                    )
                
                # Try getting YouTube metadata
                info = ytmusic.get_song(potential_vid)
                title = info.get("videoDetails", {}).get("title", "Unknown")
                safe_title = util.sanitize_filename(title)
                
                # Download the file
                flac_path = util.download_flac(potential_vid , session.get('user_id') )
                if not flac_path:
                    raise Exception("Download failed")
                    
                # Send file with proper name
                download_name = f"{safe_title}.flac" if safe_title else f"{potential_vid}.flac"
                return send_file(
                    flac_path,
                    as_attachment=True,
                    download_name=download_name
                )
                
            except Exception as yt_error:
                logger.info(f"YouTube attempt failed for {potential_vid}: {yt_error}")
                # If YouTube fails, continue to local file handling
        
        # Handle as local file
        if song_id.startswith("local-"):
            meta = local_songs.get(song_id)
            if not meta:
                return jsonify({"error": "File not found"}), 404
                
            # Get original filename
            original_name = os.path.basename(meta["path"])
            
            # Try to get a clean name from metadata
            if meta.get("title") and meta.get("artist"):
                clean_name = util.sanitize_filename(f"{meta['artist']} - {meta['title']}")
                # Keep original extension
                _, ext = os.path.splitext(original_name)
                download_name = f"{clean_name}{ext}"
            else:
                download_name = original_name
                
            return send_file(
                meta["path"],
                as_attachment=True,
                download_name=download_name
            )
            
        # If not local- prefix, treat as direct YouTube ID
        try:
            info = ytmusic.get_song(song_id)
            title = info.get("videoDetails", {}).get("title", "Unknown")
            safe_title = util.sanitize_filename(title)
            
            flac_path = util.download_flac(song_id , session.get('user_id'))
            if not flac_path:
                return jsonify({"error": "Download failed"}), 500
                
            download_name = f"{safe_title}.flac" if safe_title else f"{song_id}.flac"
            return send_file(
                flac_path,
                as_attachment=True,
                download_name=download_name
            )
            
        except Exception as e:
            logger.error(f"Download error for {song_id}: {e}")
            # Try to send file with ID if it exists
            if os.path.exists(f"music/{song_id}.flac"):
                return send_file(
                    f"music/{song_id}.flac",
                    as_attachment=True,
                    download_name=f"{song_id}.flac"
                )
            return jsonify({"error": "Download failed"}), 500
            
    except Exception as e:
        logger.error(f"Download route error: {e}")
        return jsonify({"error": str(e)}), 500

@bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint that returns a success message"""
    return jsonify({"status": "healthy", "message": "Server is running"}), 200

@bp.route('/api/artist-info/<artist_name>')
@login_required
def get_artist_info(artist_name):
    try:
        # Split multiple artists and try to get info for the primary artist
        primary_artist = artist_name.split(',')[0].strip()
        
        # Search for artist
        results = ytmusic.search(primary_artist, filter='artists')
        if not results:
            # Try a more lenient search
            results = ytmusic.search(primary_artist)
            # Filter for artist results
            results = [r for r in results if r.get('category') == 'Artists']
            
            if not results:
                logger.warning(f"No artist found for: {primary_artist}")
                # Return minimal info to prevent UI errors
                return jsonify({
                    'name': primary_artist,
                    'thumbnail': '',
                    'description': 'Artist information not available',
                    'genres': [],
                    'year': None,
                    'stats': {
                        'subscribers': '0',
                        'views': '0',
                        'monthlyListeners': '0'
                    },
                    'topSongs': [],
                    'links': {}
                })
            
        artist = results[0]
        artist_id = artist.get('browseId')
        
        if not artist_id:
            logger.warning(f"No artist ID found for: {primary_artist}")
            return jsonify({
                'name': primary_artist,
                'thumbnail': '',
                'description': 'Artist information not available',
                'genres': [],
                'year': None,
                'stats': {
                    'subscribers': '0',
                    'views': '0',
                    'monthlyListeners': '0'
                },
                'topSongs': [],
                'links': {}
            })

        # Get detailed artist info
        artist_data = ytmusic.get_artist(artist_id)
        if not artist_data:
            raise Exception("Failed to fetch artist details")

        # Rest of the processing remains same
        description = util.process_description(artist_data.get('description', ''))
        thumbnail_url = util.get_best_thumbnail(artist_data.get('thumbnails', []))
        genres = util.process_genres(artist_data)
        stats = util.get_artist_stats(artist_data)
        top_songs = util.process_top_songs(artist_data)
        links = util.process_artist_links(artist_data, artist_id)

        response = {
            'name': artist_data.get('name', primary_artist),
            'thumbnail': thumbnail_url,
            'description': description,
            'genres': genres,
            'year': util.extract_year(artist_data),
            'stats': stats,
            'topSongs': top_songs,
            'links': links
        }

        return jsonify(response)

    except Exception as e:
        logger.error(f"Error in get_artist_info: {str(e)}")
        # Return minimal info to prevent UI errors
        return jsonify({
            'name': artist_name.split(',')[0].strip(),
            'thumbnail': '',
            'description': 'Failed to load artist information',
            'genres': [],
            'year': None,
            'stats': {
                'subscribers': '0',
                'views': '0',
                'monthlyListeners': '0'
            },
            'topSongs': [],
            'links': {}
        })
    


# First add this helper function to extract playlist info
def extract_playlist_info(url, max_workers=4):
    """Extract playlist information using yt-dlp"""
    try:
        ydl_opts = {
            'quiet': True,
            'extract_flat': True,
            'force_generic_extractor': False
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info and 'entries' in info:
                # Process entries in parallel
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    # Create a partial function with ydl options
                    extract_func = partial(extract_video_info, ydl_opts=ydl_opts)
                    # Map the extraction function over all video URLs
                    video_urls = [entry['url'] if 'url' in entry else f"https://youtube.com/watch?v={entry['id']}" 
                                for entry in info['entries'] if entry]
                    results = list(executor.map(extract_func, video_urls))
                    return [r for r in results if r]  # Filter out None results
            return []
    except Exception as e:
        logger.error(f"Error extracting playlist info: {e}")
        return []

def extract_video_info(url, ydl_opts):
    """Extract single video information"""
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info:
                return {
                    "id": info.get('id', ''),
                    "title": info.get('title', 'Unknown'),
                    "artist": info.get('artist', info.get('uploader', 'Unknown Artist')),
                    "album": info.get('album', ''),
                    "duration": int(info.get('duration', 0)),
                    "thumbnail": get_best_thumbnail(info.get('thumbnails', [])),
                }
    except Exception as e:
        logger.error(f"Error extracting video info: {e}")
    return None

def get_best_thumbnail(thumbnails):
    """Get the best quality thumbnail URL"""
    if not thumbnails:
        return ""
    # Sort by resolution if available
    sorted_thumbs = sorted(thumbnails, 
                         key=lambda x: x.get('height', 0) * x.get('width', 0),
                         reverse=True)
    return sorted_thumbs[0].get('url', '')
@bp.route("/api/search")
@login_required
def api_search():
    """
    Enhanced search endpoint that handles:
    - Regular text search
    - YouTube/YouTube Music URLs (songs, playlists, albums)
    - Direct video IDs
    - Empty queries with cached default songs
    """
    local_songs = load_local_songs_from_file()
    q = request.args.get("q", "").strip()
    page = int(request.args.get("page", 0))
    limit = int(request.args.get("limit", 20))

    # === 1. Process if input is a YouTube link ===
    if "youtube.com" in q or "youtu.be" in q:
        try:
            # Handle as a playlist if the URL contains "playlist" or "list="
            if "playlist" in q or "list=" in q:
                ydl_opts = {
                    'quiet': True,
                    'extract_flat': True,
                    'force_generic_extractor': False
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(q, download=False)
                    if info and 'entries' in info:
                        results = []
                        seen_ids = set()
                        for entry in info['entries']:
                            if not entry:
                                continue
                            video_id = entry.get('id')
                            if not video_id or video_id in seen_ids:
                                continue
                            result = {
                                "id": video_id,
                                "title": entry.get('title', 'Unknown'),
                                "artist": entry.get('artist', entry.get('uploader', 'Unknown Artist')),
                                "album": entry.get('album', ''),
                                "duration": int(entry.get('duration', 0)),
                                "thumbnail": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
                            }
                            results.append(result)
                            seen_ids.add(video_id)
                            if len(results) >= limit:
                                break
                        start = page * limit
                        end = start + limit
                        return jsonify(results[start:end])

            # Handle as a single video/song
            parsed = urlparse(q)
            params = parse_qs(parsed.query)
            video_id = None
            if "youtu.be" in q:
                video_id = q.split("/")[-1].split("?")[0]
            elif "v" in params:
                video_id = params["v"][0]

            if video_id:
                ydl_opts = {
                    'quiet': True,
                    'extract_flat': False,
                    'force_generic_extractor': False
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(f"https://youtube.com/watch?v={video_id}", download=False)
                    if info:
                        result = [{
                            "id": video_id,
                            "title": info.get('title', 'Unknown'),
                            "artist": info.get('artist', info.get('uploader', 'Unknown Artist')),
                            "album": info.get('album', ''),
                            "duration": int(info.get('duration', 0)),
                            "thumbnail": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
                        }]
                        return jsonify(result)
        except Exception as e:
            logger.error(f"Error processing link '{q}': {e}")
            # Fall through to regular search if link processing fails

    # === 2. Process if input is a direct YouTube video ID ===
    if re.match(r'^[a-zA-Z0-9_-]{11}$', q):
        try:
            ydl_opts = {
                'quiet': True,
                'extract_flat': False,
                'force_generic_extractor': False
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"https://youtube.com/watch?v={q}", download=False)
                if info:
                    result = [{
                        "id": q,
                        "title": info.get('title', 'Unknown'),
                        "artist": info.get('artist', info.get('uploader', 'Unknown Artist')),
                        "album": info.get('album', ''),
                        "duration": int(info.get('duration', 0)),
                        "thumbnail": f"https://i.ytimg.com/vi/{q}/hqdefault.jpg"
                    }]
                    return jsonify(result)
        except Exception as e:
            logger.error(f"Error processing video ID '{q}': {e}")
            return jsonify([])

    # === 3. Process empty query: Use cached default songs ===
    if not q:
        default_songs = get_default_songs()
        start = page * limit
        end = start + limit
        return jsonify(default_songs[start:end])

    # === 4. Regular text search ===
    seen_ids = set()
    combined_res = []

    # Add local songs matching the query
    local_res = util.filter_local_songs(q)
    for song in local_res:
        if song["id"] not in seen_ids:
            combined_res.append(song)
            seen_ids.add(song["id"])

    # Define helper function to search using yt-dlp
    def search_ytdlp():
        try:
            ydl_opts = {
                'quiet': True,
                'extract_flat': True,
                'force_generic_extractor': False
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"ytsearch{limit}:{q}", download=False)
                results = []
                if info and 'entries' in info:
                    for entry in info['entries']:
                        if not entry:
                            continue
                        video_id = entry.get('id')
                        if not video_id:
                            continue
                        results.append({
                            "id": video_id,
                            "title": entry.get('title', 'Unknown'),
                            "artist": entry.get('artist', entry.get('uploader', 'Unknown Artist')),
                            "album": entry.get('album', ''),
                            "duration": int(entry.get('duration', 0)),
                            "thumbnail": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
                        })
                return results
        except Exception as e:
            logger.error(f"Error in YouTube search via yt-dlp: {e}")
            return []

    # Run both search methods concurrently
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future_utmusic = executor.submit(util.search_songs, q)
        future_yt = executor.submit(search_ytdlp)
        utmusic_results = future_utmusic.result()
        yt_results = future_yt.result()

    # Merge results with YTMusic results first, then yt-dlp results
    for song in (utmusic_results + yt_results):
        if song["id"] not in seen_ids:
            combined_res.append(song)
            seen_ids.add(song["id"])

    start = page * limit
    end = start + limit
    return jsonify(combined_res[start:end])
@bp.route("/api/song-info/<song_id>")
@login_required
def api_song_info(song_id):
    """Fetch metadata for a single song (local or YouTube)."""
    local_songs = load_local_songs_from_file()
    if song_id.startswith("local-"):
        meta = local_songs.get(song_id)
        if not meta:
            return jsonify({"error": "Local song not found"}), 404
        return jsonify(meta)

    try:
        if song_id not in song_cache:
            data = ytmusic.get_song(song_id)
            song_cache[song_id] = data
        else:
            data = song_cache[song_id]

        vd = data.get("videoDetails", {})
        title = vd.get("title", "Unknown")
        length = int(vd.get("lengthSeconds", 0))
        artist = vd.get("author", "Unknown Artist")
        if data.get("artists"):
            artist = data["artists"][0].get("name", "Unknown Artist")
        album = data.get("album", {}).get("name", "")
        thumb = f"https://i.ytimg.com/vi/{song_id}/hqdefault.jpg"

        return jsonify({
            "id": song_id,
            "title": title,
            "artist": artist,
            "album": album,
            "thumbnail": thumb,
            "duration": length
        })
    except Exception as e:
        logger.error(f"api_song_info error: {e}")
        return jsonify({"error": str(e)}), 400

@bp.route("/api/random-song")
@login_required
def api_random_song():
    """Return a random song from downloads or recent history."""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # First try to get from downloads
        c.execute("""
            SELECT video_id, title, artist, album 
            FROM downloads 
            ORDER BY RANDOM() 
            LIMIT 1
        """)
        
        row = c.fetchone()
        if row:
            video_id, title, artist, album = row
            thumb = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
            return jsonify({
                "id": video_id,
                "title": title,
                "artist": artist,
                "album": album,
                "thumbnail": thumb
            })
            
        # If no downloads, try history
        c.execute("""
            SELECT DISTINCT song_id 
            FROM history 
            ORDER BY RANDOM() 
            LIMIT 1
        """)
        
        row = c.fetchone()
        if row:
            song_id = row[0]
            if song_id.startswith("local-"):
                meta = local_songs.get(song_id)
                if meta:
                    return jsonify(meta)
            else:
                # Get from YouTube
                try:
                    info = ytmusic.get_song(song_id)
                    vd = info.get("videoDetails", {})
                    return jsonify({
                        "id": song_id,
                        "title": vd.get("title", "Unknown"),
                        "artist": vd.get("author", "Unknown Artist"),
                        "album": "",
                        "thumbnail": f"https://i.ytimg.com/vi/{song_id}/hqdefault.jpg"
                    })
                except Exception as e:
                    logger.error(f"Error getting YouTube song info: {e}")
        
        # If no history, return a default popular song
        default_songs = ["dQw4w9WgXcQ", "kJQP7kiw5Fk", "9bZkp7q19f0"]  # Some popular songs
        random_id = random.choice(default_songs)
        info = ytmusic.get_song(random_id)
        vd = info.get("videoDetails", {})
        
        return jsonify({
            "id": random_id,
            "title": vd.get("title", "Unknown"),
            "artist": vd.get("author", "Unknown Artist"),
            "album": "",
            "thumbnail": f"https://i.ytimg.com/vi/{random_id}/hqdefault.jpg"
        })
        
    except Exception as e:
        logger.error(f"Random song error: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


@bp.route('/api/get-recommendations/<song_id>')
@login_required
def api_get_recommendations(song_id):
    """Get recommendations using available YTMusic methods."""
    try:
        if song_id.startswith("local-"):
            return util.get_local_song_recommendations(song_id)

        recommendations = []
        seen_songs = set()

        # 1. Get current song info
        song_info = ytmusic.get_song(song_id)
        if not song_info:
            return util.fallback_recommendations()

        # 2. Get related songs from watch playlist (most reliable method)
        try:
            watch_playlist = ytmusic.get_watch_playlist(videoId=song_id, limit=25)
            if watch_playlist and "tracks" in watch_playlist:
                for track in watch_playlist["tracks"]:
                    if util.add_recommendation(track, recommendations, seen_songs, song_id):
                        if len(recommendations) >= 5:
                            logger.info(f"Found recommendations from watch playlist for {song_id}")
                            return jsonify(recommendations)
        except Exception as e:
            logger.warning(f"Watch playlist error: {e}")

        # 3. If not enough recommendations, try artist's songs
        if len(recommendations) < 5 and "artists" in song_info:
            try:
                artist_id = song_info["artists"][0].get("id")
                if artist_id:
                    artist_data = ytmusic.get_artist(artist_id)
                    if artist_data and "songs" in artist_data:
                        artist_songs = list(artist_data["songs"])
                        random.shuffle(artist_songs)
                        for track in artist_songs[:10]:
                            if util.add_recommendation(track, recommendations, seen_songs, song_id):
                                if len(recommendations) >= 5:
                                    break
            except Exception as e:
                logger.warning(f"Artist recommendations error: {e}")

        # 4. If still not enough, search for similar songs
        if len(recommendations) < 5:
            try:
                # Get current song details for search
                title = song_info.get("videoDetails", {}).get("title", "")
                artist = song_info.get("videoDetails", {}).get("author", "")
                if title and artist:
                    # Search with song title and artist
                    search_results = ytmusic.search(f"{title} {artist}", filter="songs", limit=10)
                    for track in search_results:
                        if util.add_recommendation(track, recommendations, seen_songs, song_id):
                            if len(recommendations) >= 5:
                                break
            except Exception as e:
                logger.warning(f"Search recommendations error: {e}")

        # 5. Last resort: get popular songs
        if len(recommendations) < 5:
            try:
                popular_songs = ytmusic.search("popular songs", filter="songs", limit=10)
                for track in popular_songs:
                    if util.add_recommendation(track, recommendations, seen_songs, song_id):
                        if len(recommendations) >= 5:
                            break
            except Exception as e:
                logger.warning(f"Popular songs error: {e}")

        # Ensure we have at least some recommendations
        if not recommendations:
            return util.fallback_recommendations()

        # Shuffle for variety and return
        random.shuffle(recommendations)
        return jsonify(recommendations[:5])

    except Exception as e:
        logger.error(f"Recommendations error: {e}")
        return util.fallback_recommendations()
    


@bp.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'POST':
        if 'step' not in session:
            # Initial email submission
            email = request.form.get('email')
            if not email:
                return render_template_string(
                    var_templates.RESET_PASSWORD_HTML,
                    step='email',
                    error='Email is required'
                )
                
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute('SELECT id FROM users WHERE email = ?', (email,))
            user = c.fetchone()
            conn.close()
            
            if not user:
                return render_template_string(
                    var_templates.RESET_PASSWORD_HTML,
                    step='email',
                    error='No account found with this email'
                )
                
            # Send verification code
            otp = util.generate_otp()
            util.store_otp(email, otp, 'reset')
            var_templates.send_forgot_password_email(email , otp)
            
            session['reset_email'] = email
            session['step'] = 'verify'
            
            return render_template_string(
                var_templates.RESET_PASSWORD_HTML,
                step='verify',
                email=email
            )
            
        elif session['step'] == 'verify':
            # OTP verification
            email = session.get('reset_email')
            otp = request.form.get('otp')
            
            if not util.verify_otp(email, otp, 'reset'):
                return render_template_string(
                    var_templates.RESET_PASSWORD_HTML,
                    step='verify',
                    email=email,
                    error='Invalid or expired code'
                )
                
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute('SELECT id FROM users WHERE email = ?', (email,))
            user_id = c.fetchone()[0]
            conn.close()
            
            session['step'] = 'new_password'
            session['user_id_reset'] = user_id
            
            return render_template_string(
                var_templates.RESET_PASSWORD_HTML,
                step='new_password',
                user_id=user_id
            )
            
        elif session['step'] == 'new_password':
            # Password update
            new_password = request.form.get('new_password')
            user_id = session.get('user_id_reset')
            if not new_password:
                session.pop('step', None)
                session.pop('reset_email', None)
                session.pop('user_id_reset', None)
            
            if len(new_password) < 6:
                return render_template_string(
                    var_templates.RESET_PASSWORD_HTML,
                    step='new_password',
                    user_id=user_id,
                    error='Password must be at least 6 characters'
                )
                
            password_hash = bcrypt.hashpw(
                new_password.encode(),
                bcrypt.gensalt()
            ).decode()
            
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute(
                'UPDATE users SET password_hash = ? WHERE id = ?',
                (password_hash, user_id)
            )
            conn.commit()
            conn.close()
            
            # Clear session
            session.pop('step', None)
            session.pop('reset_email', None)
            session.pop('user_id_reset', None)
            
            return redirect(url_for('playback.login'))
            
    return render_template_string(var_templates.RESET_PASSWORD_HTML, step='email')



@bp.route('/forgot_username', methods=['GET', 'POST'])
def forgot_username():
    if request.method == 'POST':
        if 'step' not in session:
            email = request.form.get('email')
            if not email:
                return render_template_string(
                    var_templates.FORGOT_USERNAME_HTML,
                    step='email',
                    error='Email is required'
                )
                
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute('SELECT username FROM users WHERE email = ?', (email,))
            user = c.fetchone()
            conn.close()
            
            if not user:
                return render_template_string(
                    var_templates.FORGOT_USERNAME_HTML,
                    step='email',
                    error='No account found with this email'
                )
                
            # Send username directly to email
            var_templates.send_forgot_username_email(email , user)
            
            return render_template_string(
                var_templates.LOGIN_HTML,
                login_step='initial',
                success='Username has been sent to your email'
            )
            
    return render_template_string(var_templates.FORGOT_USERNAME_HTML, step='email')




@bp.route('/logout')
def logout():
    if 'user_id' in session and 'session_token' in session:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            DELETE FROM active_sessions 
            WHERE user_id = ? AND session_token = ?
        """, (session['user_id'], session['session_token']))
        conn.commit()
        conn.close()
    
    session.clear()
    return redirect(url_for('playback.login'))


@bp.route('/login', methods=['GET', 'POST'])
def login():
    # First check if user is already logged in with valid session
    if 'user_id' in session and 'session_token' in session:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        try:
            c.execute("""
                SELECT 1 FROM active_sessions 
                WHERE user_id = ? AND session_token = ? 
                AND expires_at > CURRENT_TIMESTAMP
            """, (session['user_id'], session['session_token']))
            valid_session = c.fetchone()
            
            if valid_session:
                return redirect(url_for('playback.home'))
            else:
                # Clear invalid session
                session.clear()
        except Exception as e:
            logger.error(f"Session check error: {e}")
            session.clear()
        finally:
            conn.close()
    
    if request.method == 'POST':
        login_id = request.form.get('login_id')
        password = request.form.get('password')
        
        # Input validation
        if not login_id or not password:
            return render_template_string(
                var_templates.LOGIN_HTML,
                login_step='initial',
                error='Both login ID and password are required'
            )
        
        # Clear any existing temporary login data
        if 'temp_login' in session:
            session.pop('temp_login')
            
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        try:
            # Check if login_id is email or username
            c.execute("""
                SELECT id, password_hash, twofa_method, email,
                       (SELECT COUNT(*) FROM active_sessions 
                        WHERE user_id = users.id 
                        AND expires_at > CURRENT_TIMESTAMP) as active_sessions
                FROM users 
                WHERE email = ? OR username = ?
            """, (login_id, login_id))
            
            user = c.fetchone()
            
            if user and bcrypt.checkpw(password.encode(), user[1].encode()):
                user_id, password_hash, twofa_method, email, active_sessions = user
                
                # Check for existing active sessions
                if active_sessions > 0:
                    # Terminate other sessions
                    c.execute("""
                        DELETE FROM active_sessions 
                        WHERE user_id = ? 
                    """, (user_id,))
                    conn.commit()
                    logger.info(f"Terminated existing sessions for user {user_id}")
                
                if twofa_method != 'none':  # 2FA enabled
                    # Generate temporary login token
                    token = secrets.token_urlsafe(32)
                    session['temp_login'] = {
                        'token': token,
                        'user_id': user_id,
                        'twofa_method': twofa_method
                    }
                    
                    if twofa_method == 'email':
                        # Generate and send OTP
                        otp = util.generate_otp()
                        util.store_otp(email, otp, 'login')
                        util.send_email(
                            email, 
                            'Login Verification', 
                            f'Your verification code is: {otp}'
                        )
                    
                    return render_template_string(
                        var_templates.LOGIN_HTML,
                        login_step='2fa',
                        login_token=token,
                        twofa_method=twofa_method
                    )
                
                # No 2FA - direct login
                session_token = secrets.token_urlsafe(32)
                expires_at = datetime.now() + timedelta(days=7)
                
                # Create new session
                c.execute("""
                    INSERT INTO active_sessions (user_id, session_token, expires_at)
                    VALUES (?, ?, ?)
                """, (user_id, session_token, expires_at))
                
                conn.commit()
                
                # Set session cookies
                session.clear()
                session['user_id'] = user_id
                session['session_token'] = session_token
                session['last_session_check'] = int(time.time())
                
                return redirect(url_for('playback.home'))
            else:
                # Invalid credentials - add small delay to prevent brute force
                time.sleep(random.uniform(0.1, 0.3))
                return render_template_string(
                    var_templates.LOGIN_HTML,
                    login_step='initial',
                    error='Invalid credentials'
                )
                
        except Exception as e:
            logger.error(f"Login error: {e}")
            return render_template_string(
                var_templates.LOGIN_HTML,
                login_step='initial',
                error='An error occurred during login'
            )
        finally:
            conn.close()
            
    # GET request - show login form
    return render_template_string(
        var_templates.LOGIN_HTML, 
        login_step='initial'
    )

@bp.route("/favicon.ico")
def set_fake():
    return "not there..."
@bp.route('/login_verify', methods=['POST'])
def login_verify():
    if 'temp_login' not in session:
        return redirect(url_for('playback.login'))
        
    temp = session['temp_login']
    otp = request.form.get('otp')
    token = request.form.get('login_token')
    
    if token != temp['token']:
        return render_template_string(
            var_templates.LOGIN_HTML,
            login_step='2fa',
            error='Invalid session'
        )
    
    if temp['twofa_method'] == 'email':
        # Verify email OTP
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT email FROM users WHERE id = ?', (temp['user_id'],))
        email = c.fetchone()[0]
        conn.close()
        
        if not util.verify_otp(email, otp, 'login'):
            return render_template_string(
                var_templates.LOGIN_HTML,
                login_step='2fa',
                login_token=token,
                twofa_method=temp['twofa_method'],
                error='Invalid or expired code'
            )
    
    # Create new session after successful 2FA
    session_token = secrets.token_urlsafe(32)
    expires_at = datetime.now() + timedelta(days=7)
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO active_sessions (user_id, session_token, expires_at)
        VALUES (?, ?, ?)
    """, (temp['user_id'], session_token, expires_at))
    conn.commit()
    conn.close()
    
    # Clear temporary login data and set permanent session
    session.clear()
    session['user_id'] = temp['user_id']
    session['session_token'] = session_token
    
    return redirect(url_for('playback.home'))

# Add this to your Flask routes file

@bp.route('/terms-register', methods=['GET'])
def terms_register():
    """Route to get terms and conditions for the registration page."""
    try:
        # Read terms from a file
        with open(os.path.join(os.getcwd() , "terms" , "terms_register.txt"), 'r') as file:
            terms_content = file.read()
            
        # Format the content with HTML for better display
        formatted_terms = f"""
        <div class="space-y-4">
            <h4 class="text-xl font-semibold mb-3">Sangeet Premium Terms of Service</h4>
            {terms_content}
        </div>
        """
        return formatted_terms
    except FileNotFoundError:
        # Fallback to default terms if file not found
        print("terms file not found...")
        return "Something missing our side cant load terms right now please dont register if you aren't sure.."
        


@bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        username = request.form.get('username')
        full_name = request.form.get('full_name')
        password = request.form.get('password')
        
        # Basic validation
        if not all([email, username, full_name, password]):
            return render_template_string(
                var_templates.REGISTER_HTML,
                register_step='initial',
                error='All fields are required'
            )
            
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Check if email/username exists
        c.execute("""
            SELECT 1 FROM users 
            WHERE email = ? OR username = ?
        """, (email, username))
        
        if c.fetchone():
            conn.close()
            return render_template_string(
                var_templates.REGISTER_HTML,
                register_step='initial',
                error='Email or username already exists'
            )
            
        # Generate verification OTP
        otp = util.generate_otp()
        util.store_otp(email, otp, 'register')
        
        # Store registration data in session
        token = secrets.token_urlsafe(32)
        session['register_data'] = {
            'token': token,
            'email': email,
            'username': username,
            'full_name': full_name,
            'password': password
        }
        
        # Send verification email
        var_templates.send_register_otp_email(email , otp)
        
        return render_template_string(
            var_templates.REGISTER_HTML,
            register_step='verify',
            email=email,
            register_token=token
        )
        
    return render_template_string(var_templates.REGISTER_HTML, register_step='initial')



@bp.route('/register/verify', methods=['POST'])
def register_verify():
    if 'register_data' not in session:
        return redirect(url_for('playback.register'))
        
    data = session['register_data']
    otp = request.form.get('otp')
    token = request.form.get('register_token')
    
    if token != data['token']:
        return render_template_string(
            var_templates.REGISTER_HTML,
            register_step='verify',
            error='Invalid session'
        )
        
    if not util.verify_otp(data['email'], otp, 'register'):
        return render_template_string(
            var_templates.REGISTER_HTML,
            register_step='verify',
            email=data['email'],
            register_token=token,
            error='Invalid or expired code'
        )
        
    # Create user account
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    password_hash = bcrypt.hashpw(
        data['password'].encode(), 
        bcrypt.gensalt()
    ).decode()
    
    c.execute("""
        INSERT INTO users (email, username, full_name, password_hash)
        VALUES (?, ?, ?, ?)
    """, (data['email'], data['username'], data['full_name'], password_hash))
    
    user_id = c.lastrowid
    
    # Generate session token and create active session
    session_token = secrets.token_urlsafe(32)
    expires_at = datetime.now() + timedelta(days=7)
    
    c.execute("""
        INSERT INTO active_sessions (user_id, session_token, expires_at)
        VALUES (?, ?, ?)
    """, (user_id, session_token, expires_at))
    
    conn.commit()
    conn.close()
    
    # Set both required session variables
    session.pop('register_data')
    session['user_id'] = user_id
    session['session_token'] = session_token
    
    return redirect(url_for('playback.home'))

@bp.route("/api/insights")
@login_required
def get_insights():
    """Get comprehensive listening insights for the current user."""
    user_id = session['user_id']
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    try:
        insights = {
            "overview": util.get_overview_stats(c, user_id),
            "recent_activity": util.get_recent_activity(c, user_id),
            "top_artists": util.get_top_artists(c, user_id),
            "listening_patterns": util.get_listening_patterns(c, user_id),
            "completion_rates": util.get_completion_rates(c, user_id)
        }
        
        return jsonify(insights)
    finally:
        conn.close()


@bp.route("/api/listen/start", methods=["POST"])
@login_required
def api_listen_start():
    """Start a new listening session for the current user."""
    try:
        user_id = session['user_id']
        data = request.json
        if not data or not all(k in data for k in ["songId", "title", "artist"]):
            return jsonify({"error": "Missing required fields"}), 400

        session_id = util.generate_session_id()
        listen_id = util.record_listen_start(
            user_id=user_id,
            song_id=data["songId"],
            title=data["title"],
            artist=data["artist"],
            session_id=session_id
        )

        return jsonify({
            "status": "success",
            "listenId": listen_id,
            "sessionId": session_id
        })
    except Exception as e:
        logger.error(f"Listen start error: {e}")
        return jsonify({"error": str(e)}), 500

@bp.route("/api/listen/end", methods=["POST"])
@login_required
def api_listen_end():
    """End a listening session for the current user."""
    try:
        user_id = session['user_id']
        data = request.json
        if not data or "listenId" not in data:
            return jsonify({"error": "Missing listenId"}), 400
            
        listen_id = int(data["listenId"])
        
        # Verify the listen_id belongs to the user
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT user_id FROM listening_history WHERE id = ?", (listen_id,))
        row = c.fetchone()
        if not row or row[0] != user_id:
            return jsonify({"error": "Invalid listen ID"}), 403
        
        duration = data.get("duration", 0)
        listened_duration = data.get("listenedDuration", 0)

        util.record_listen_end(
            listen_id=listen_id,
            duration=duration,
            listened_duration=listened_duration
        )

        return jsonify({"status": "success"})
    except Exception as e:
        logger.error(f"Listen end error: {e}")
        return jsonify({"error": str(e)}), 500


@bp.route("/api/proxy/image")
@login_required
def proxy_image():
    """Proxy endpoint for fetching images with CORS headers."""
    url = request.args.get('url')
    if not url:
        return "No URL provided", 400

    # Validate URL is from trusted domains
    allowed_domains = {'i.ytimg.com', 'img.youtube.com'}
    try:
        domain = urlparse(url).netloc
        if domain not in allowed_domains:
            return "Invalid domain", 403
    except:
        return "Invalid URL", 400

    content, content_type = util.fetch_image(url)
    if content:
        response = make_response(content)
        response.headers['Content-Type'] = content_type
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Cache-Control'] = 'public, max-age=31536000'
        return response

    return "Failed to fetch image", 500




@bp.route("/get-extension")
def get_extension():
    return render_template("extension.html")



@bp.route('/download/extension')
def download_extension():
    """
    Handle the download of the extension zip file.
    Replace 'extension.zip' with your actual file name.
    """
    try:
        return send_file(
            os.path.join(os.getcwd() , "payloads" , "extension" , "sangeet-premium.zip"),
            as_attachment=True,
            download_name='sangeet-premium.zip',
            mimetype='application/zip'
        )
    except Exception as e:
        return f"Error: File not found", 404
@bp.route('/sangeet-download/<video_id>')
def sangeet_download(video_id):
    user_id = session.get('user_id')  # Get user ID from session

    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401

    # Get metadata from ytmusicapi
    try:
        info = ytmusic.get_song(video_id)
        vd = info.get("videoDetails", {})
        title = vd.get("title", "Unknown")
        artist = vd.get("author", "Unknown Artist")
        album = info.get("album", {}).get("name", "")
        thumbnail = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"

        safe_title = util.sanitize_filename(title) or "Track"
        dl_name = f"{safe_title}.flac"

        return render_template('download.html', 
            title=title, 
            artist=artist, 
            album=album, 
            thumbnail=thumbnail,
            dl_name=dl_name,
            video_id=video_id
        )

    except Exception as e:
        logger.error(f"Download error: {e}")
        return jsonify({"error": "Failed to process download"}), 500
    


@bp.route('/download-file/<video_id>')
def download_file(video_id):
    user_id = session.get('user_id')  # Get user ID from session

    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401

    flac_path = util.download_flac(video_id, user_id)
    if not flac_path:
        return jsonify({"error": "Failed to process FLAC"}), 500
    
    # Get metadata for file name
    try:
        info = ytmusic.get_song(video_id)
        vd = info.get("videoDetails", {})
        title = vd.get("title", "Unknown")
        safe_title = util.sanitize_filename(title) or "Track"
        dl_name = f"{safe_title}.flac"

        return send_file(flac_path, as_attachment=True, download_name=dl_name)

    except Exception as e:
        logger.error(f"Download error: {e}")
        return jsonify({"error": "Failed to process download"}), 500
    





@bp.route("/data/download/icons/<type>")
def icons(type):
    if type == "download":
        with open(os.path.join(os.getcwd() , "assets" , "favicons" , "download" , "fav.txt") , "r") as fav:
         data = fav.read()
        fav.close()
        return jsonify({"base64": data})
    elif type == "sangeet-home":
        return send_file(os.path.join(os.getcwd() , "assets" , "gifs" , "sangeet" , "index.gif"))
    elif type == "get-extension":
        with open(os.path.join(os.getcwd() , "assets" , "favicons" , "get-extension" , "fav.txt") , "r") as fav:
         data = fav.read()
        fav.close()
        return jsonify({"base64": data})
    elif type == "login-system-login":
        with open(os.path.join(os.getcwd() , "assets" , "favicons" , "login-system" , "login.txt") , "r") as fav:
         data = fav.read()
        fav.close()
        return jsonify({"base64": data})
    elif type == "login-system-register":
        with open(os.path.join(os.getcwd() , "assets" , "favicons" , "login-system" , "register.txt") , "r") as fav:
         data = fav.read()
        fav.close()
        return jsonify({"base64": data})
    elif type == "login-system-forgot":
        with open(os.path.join(os.getcwd() , "assets" , "favicons" , "login-system" , "forgot.txt") , "r") as fav:
         data = fav.read()
        fav.close()
        return jsonify({"base64": data})
    else:
        with open(os.path.join(os.getcwd() , "assets" , "favicons" , "genric" , "fav.txt") , "r") as fav:
         data = fav.read()
        fav.close()
        return jsonify({"base64": data})
    

@bp.route("/embed/<song_id>")
def embed_player(song_id):
    """Serve an embeddable player for a specific song."""
    try:
        # Get customization options
        size = request.args.get("size", "normal")  # small, normal, large
        theme = request.args.get("theme", "default")  # default, purple, blue, dark
        autoplay = request.args.get("autoplay", "false").lower() == "true"
        
        # Get song info
        if song_id.startswith("local-"):
            meta = local_songs.get(song_id)
            if not meta:
                return jsonify({"error": "Song not found"}), 404
            song_info = {
                "id": song_id,
                "title": meta["title"],
                "artist": meta["artist"],
                "thumbnail": meta["thumbnail"] or url_for('playback.static', filename='images/default-cover.jpg'),
                "duration": meta["duration"]
            }
            # For local files, use the local stream endpoint
            stream_url = url_for('playback.api_stream_local', song_id=song_id)
        else:
            try:
                if song_id not in song_cache:
                    data = ytmusic.get_song(song_id)
                    song_cache[song_id] = data
                else:
                    data = song_cache[song_id]

                vd = data.get("videoDetails", {})
                song_info = {
                    "id": song_id,
                    "title": vd.get("title", "Unknown"),
                    "artist": vd.get("author", "Unknown Artist"),
                    "thumbnail": f"https://i.ytimg.com/vi/{song_id}/hqdefault.jpg",
                    "duration": int(vd.get("lengthSeconds", 0))
                }
                
                # Download/get FLAC stream URL
                flac_path = util.download_flac(song_id , session.get('user_id')  )
                if not flac_path:
                    return jsonify({"error": "Failed to process audio"}), 500
                
                stream_url = url_for('playback.stream_file', song_id=song_id)
                
            except Exception as e:
                logger.error(f"Error getting song info: {e}")
                return jsonify({"error": "Failed to get song info"}), 500

        # Generate the embed HTML
        return render_template(
            "embed.html",
            song=song_info,
            size=size,
            theme=theme,
            autoplay=autoplay,
            stream_url=stream_url,
            host_url=SERVER_DOMAIN
        )
        
    except Exception as e:
        logger.error(f"Embed error: {e}")
        return jsonify({"error": "Internal server error"}), 500

@bp.route("/play/<song_id>")
def play_song(song_id):
    """Redirect to main player with the selected song."""
    return redirect(url_for('playback.home', song=song_id))

@bp.before_request
def before_request():
    # Clear expired sessions
    util.cleanup_expired_sessions()
    
    # Check if current session is expired
    if 'user_id' in session and 'session_token' in session:
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
            session.clear()

@bp.route("/api/embed-code/<song_id>")
def get_embed_code(song_id):
    """Get the iframe code for embedding a song."""
    try:
        size = request.args.get("size", "normal")
        theme = request.args.get("theme", "default")
        autoplay = request.args.get("autoplay", "false")
        
        # Set dimensions based on size
        dimensions = {
            "small": (320, 160),
            "normal": (400, 200),
            "large": (500, 240)
        }
        width, height = dimensions.get(size, dimensions["normal"])
        
        # Generate iframe code
        embed_url = f"{request.host_url.rstrip('/')}/embed/{song_id}?size={size}&theme={theme}&autoplay={autoplay}"
        iframe_code = (
            f'<iframe src="{embed_url}" '
            f'width="{width}" height="{height}" '
            'frameborder="0" allowtransparency="true" '
            'allow="encrypted-media; autoplay" loading="lazy">'
            '</iframe>'
        )
        
        return jsonify({
            "code": iframe_code,
            "url": embed_url,
            "width": width,
            "height": height
        })
        
    except Exception as e:
        logger.error(f"Embed code error: {e}")
        return jsonify({"error": "Internal server error"}), 500
    
from flask import jsonify, request

@bp.route('/api/queue', methods=['GET'])
@login_required
def api_queue():
    user_id = session['user_id']
    limit = int(request.args.get('limit', 5))
    offset = int(request.args.get('offset', 0))
    history = util.get_play_history(user_id, limit, offset)
    return jsonify(history)

# Update stats route
@bp.route("/api/stats")
@login_required
def api_stats():
    """Return user-specific usage stats."""
    local_songs = load_local_songs_from_file()
    try:
        user_id = session['user_id']
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        # Get user's stats
        c.execute("""
            SELECT total_plays, total_listened_time, favorite_song_id, favorite_artist
            FROM user_stats 
            WHERE user_id = ?
        """, (user_id,))
        stats = c.fetchone() or (0, 0, None, None)
        
        # Get user's unique songs
        c.execute("""
            SELECT COUNT(DISTINCT song_id) 
            FROM user_history 
            WHERE user_id = ?
        """, (user_id,))
        unique_songs = c.fetchone()[0]

        # Get user's downloads
        c.execute("""
            SELECT COUNT(*) 
            FROM user_downloads 
            WHERE user_id = ?
        """, (user_id,))
        total_downloads = c.fetchone()[0]

        # Get download storage size
        download_size = 0
        c.execute("SELECT path FROM user_downloads WHERE user_id = ?", (user_id,))
        for (path,) in c.fetchall():
            try:
                if os.path.exists(path):
                    download_size += os.path.getsize(path)
            except:
                continue

        # Get top 5 most played
        c.execute("""
            SELECT song_id, COUNT(*) as play_count
            FROM user_history
            WHERE user_id = ?
            GROUP BY song_id
            ORDER BY play_count DESC
            LIMIT 5
        """, (user_id,))
        
        top_songs = []
        for sid, count in c.fetchall():
            try:
                if sid.startswith("local-"):
                    if sid in local_songs:
                        meta = local_songs[sid]
                        top_songs.append({
                            "id": sid,
                            "title": meta["title"],
                            "artist": meta["artist"],
                            "plays": count
                        })
                else:
                    if sid not in song_cache:
                        data = ytmusic.get_song(sid)
                        song_cache[sid] = data
                    else:
                        data = song_cache[sid]
                    vd = data.get("videoDetails", {})
                    title = vd.get("title", "Unknown")
                    artist = vd.get("author", "Unknown Artist")
                    if data.get("artists"):
                        artist = data["artists"][0].get("name", artist)
                    top_songs.append({
                        "id": sid,
                        "title": title,
                        "artist": artist,
                        "plays": count
                    })
            except:
                continue

        conn.close()

        return jsonify({
            "total_plays": stats[0],
            "total_listened_time": stats[1],
            "unique_songs": unique_songs,
            "total_downloads": total_downloads,
            "download_size": download_size,
            "top_songs": top_songs,
            "favorite_song": stats[2],
            "favorite_artist": stats[3],
            "local_songs_count": len(local_songs)
        })
    except Exception as e:
        logger.error(f"Stats error: {e}")
        return jsonify({"error": str(e)}), 500

@bp.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found"}), 404

@bp.errorhandler(500)
def internal_error(e):
    return jsonify({"error": "Internal server error"}), 500



@bp.route("/api/stream/<song_id>")
# @login_required
def api_stream(song_id):
    """Obtain a streaming URL for a given song_id (local or YouTube)."""
    user_id = session['user_id']
    if not user_id == None:
      util.record_song(song_id, user_id)

    if song_id.startswith("local-"):
        return jsonify({
            "local": True,
            "url": f"/api/stream-local/{song_id}"
        })

    flac_path = util.download_flac(song_id, user_id)
    if not flac_path:
        return jsonify({"error": "Download/FLAC conversion failed"}), 500

    return jsonify({
        "url": f"/api/stream-file/{song_id}",
        "local": False
    })

@bp.route("/api/download/<song_id>")
@login_required
def api_download(song_id):
    """Provide the FLAC file as a downloadable attachment."""
    local_songs = load_local_songs_from_file()
    user_id = session['user_id']
    
    if song_id.startswith("local-"):
        meta = local_songs.get(song_id)
        if not meta:
            return jsonify({"error": "Local file not found"}), 404
        filename = os.path.basename(meta["path"])
        return send_file(
            meta["path"],
            as_attachment=True,
            download_name=filename
        )

    flac_path = util.download_flac(song_id, user_id)
    if not flac_path:
        return jsonify({"error": "Failed to process FLAC"}), 500

    # Get metadata and record download
    try:
        info = ytmusic.get_song(song_id)
        vd = info.get("videoDetails", {})
        title = vd.get("title", "Unknown")
        artist = vd.get("author", "Unknown Artist")
        album = info.get("album", {}).get("name", "")
        
        # Note: download is already recorded in download_flac function
        
        safe_title = util.sanitize_filename(title) or "Track"
        dl_name = f"{safe_title}.flac"

        return send_file(
            flac_path,
            as_attachment=True,
            download_name=dl_name
        )
    except Exception as e:
        logger.error(f"Download error: {e}")
        return jsonify({"error": "Failed to process download"}), 500



@bp.route("/api/similar/<song_id>")
@login_required
def api_similar(song_id):
    """Get similar songs based on current song, fallback if local or error."""
    try:
        if song_id.startswith("local-"):
            return util.fallback_recommendations()

        song_info = ytmusic.get_song(song_id)
        if not song_info:
            return util.fallback_recommendations()

        similar_songs = []

        # 1) Radio-based suggestions
        try:
            radio = ytmusic.get_watch_playlist(song_id, limit=10)
            if radio and "tracks" in radio:
                for track in radio["tracks"]:
                    vid = track.get("videoId")
                    if vid and vid != song_id and track.get("isAvailable") != False:
                        title = track.get("title", "Unknown")
                        art = "Unknown Artist"
                        if "artists" in track and track["artists"]:
                            art = track["artists"][0].get("name", art)
                        alb = ""
                        if "album" in track and isinstance(track["album"], dict):
                            alb = track["album"].get("name", "")
                        thumb = f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
                        dur = track.get("duration_seconds", 0)
                        similar_songs.append({
                            "id": vid,
                            "title": title,
                            "artist": art,
                            "album": alb,
                            "thumbnail": thumb,
                            "duration": dur
                        })
        except Exception as e:
            logger.warning(f"Radio recommendations failed: {e}")

        # 2) Artist's other songs
        try:
            if "artists" in song_info and song_info["artists"]:
                artist_id = song_info["artists"][0].get("id")
                if artist_id:
                    artist_songs = ytmusic.get_artist(artist_id)
                    if artist_songs and "songs" in artist_songs:
                        random_songs = random.sample(
                            artist_songs["songs"], 
                            min(3, len(artist_songs["songs"]))
                        )
                        for track in random_songs:
                            vid = track.get("videoId")
                            if vid and vid != song_id:
                                title = track.get("title", "Unknown")
                                art = "Unknown Artist"
                                if "artists" in track and track["artists"]:
                                    art = track["artists"][0].get("name", art)
                                alb = ""
                                if "album" in track and isinstance(track["album"], dict):
                                    alb = track["album"].get("name", "")
                                thumb = f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
                                dur = track.get("duration_seconds", 0)
                                similar_songs.append({
                                    "id": vid,
                                    "title": title,
                                    "artist": art,
                                    "album": alb,
                                    "thumbnail": thumb,
                                    "duration": dur
                                })
        except Exception as e:
            logger.warning(f"Artist recommendations failed: {e}")

        # 3) If not enough, do a quick search
        if len(similar_songs) < 5:
            try:
                t = song_info.get("videoDetails", {}).get("title", "")
                a = song_info.get("videoDetails", {}).get("author", "")
                results = ytmusic.search(f"{t} {a}", filter="songs", limit=5)
                for track in results:
                    vid = track.get("videoId")
                    if vid and vid != song_id:
                        ttitle = track.get("title", "Unknown")
                        tartist = "Unknown Artist"
                        if "artists" in track and track["artists"]:
                            tartist = track["artists"][0].get("name", tartist)
                        talbum = ""
                        if "album" in track and isinstance(track["album"], dict):
                            talbum = track["album"].get("name", "")
                        thumb = f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
                        dur = track.get("duration_seconds", 0)
                        similar_songs.append({
                            "id": vid,
                            "title": ttitle,
                            "artist": tartist,
                            "album": talbum,
                            "thumbnail": thumb,
                            "duration": dur
                        })
            except Exception as e:
                logger.warning(f"Search recommendations failed: {e}")

        random.shuffle(similar_songs)
        return jsonify(similar_songs[:5])

    except Exception as e:
        logger.error(f"Similar songs error: {e}")
        return util.fallback_recommendations()


@bp.route("/api/history/clear", methods=["POST"])
@login_required
def api_clear_history():
    """Clear play history."""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM history")
        conn.commit()
        conn.close()
        return jsonify({"status": "success"})
    except Exception as e:
        logger.error(f"Clear history error: {e}")
        return jsonify({"error": str(e)}), 500


@bp.route("/api/downloads/clear", methods=["POST"])
@login_required
def api_clear_downloads():
    """Clear all downloads in DB and remove files from disk."""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT path FROM downloads")
        paths = [row[0] for row in c.fetchall()]

        for path in paths:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception as e:
                logger.warning(f"Failed to delete file {path}: {e}")

        c.execute("DELETE FROM downloads")
        conn.commit()
        conn.close()
        return jsonify({"status": "success"})
    except Exception as e:
        logger.error(f"Clear downloads error: {e}")
        return jsonify({"error": str(e)}), 500



@bp.route("/api/stream-file/<song_id>")
# @login_required
def stream_file(song_id):
    """Serve the FLAC file with range requests for seeking."""
    flac_path = os.path.join(os.getenv("music_path"), f"{song_id}.flac")
    if not os.path.exists(flac_path):
        return jsonify({"error": "File not found"}), 404

    try:
        return send_file(flac_path)

    except Exception as e:
        logger.error(f"stream_file error: {e}")
        return jsonify({"error": str(e)}), 500


@bp.route("/api/stream-local/<song_id>")
# @login_required
def api_stream_local(song_id):
    """Serve a local file with range requests."""
    local_songs = load_local_songs_from_file()
    meta = local_songs.get(song_id)
    if not meta:
        return jsonify({"error": "Local file not found"}), 404
    path = meta["path"]
    if not os.path.isfile(path):
        return jsonify({"error": "File not on disk"}), 404

    try:
       return send_file(path)
    except Exception as e:
        logger.error(f"stream_local error: {e}")
        return jsonify({"error": str(e)}), 500



# Function to get lyrics from cache
def get_cached_lyrics(song_id):
    conn = sqlite3.connect(os.path.join(os.getcwd() , "database_files" , "lyrics_cache.db"))
    cursor = conn.cursor()
    cursor.execute('SELECT lyrics FROM lyrics_cache WHERE song_id = ?', (song_id,))
    result = cursor.fetchone()
    conn.close()
    if result:
        return result[0].split('\n')
    return None

# Function to cache lyrics
def cache_lyrics(song_id, lyrics_lines):
    lyrics_text = '\n'.join(lyrics_lines)
    conn = sqlite3.connect(os.path.join(os.getcwd() , "database_files" , "lyrics_cache.db"))
    cursor = conn.cursor()
    cursor.execute('''
    INSERT OR REPLACE INTO lyrics_cache (song_id, lyrics, timestamp) 
    VALUES (?, ?, CURRENT_TIMESTAMP)
    ''', (song_id, lyrics_text))
    conn.commit()
    conn.close()

@bp.route("/api/lyrics/<song_id>")
def api_lyrics(song_id):
    """Return YTMusic lyrics array or [] for local/no lyrics."""
    
    # Handle local songs
    if song_id.startswith("local-"):
        try:
            # Load the locals.json file
            with open(os.path.join(os.getcwd() , "locals" , "local.json"), 'r') as f:
                locals_data = json.load(f)
            
            # Get the song data for this local ID
            song_data = locals_data.get(song_id)
            if not song_data or "path" not in song_data:
                logger.info(f"No path found for local song: {song_id}")
                return jsonify([])
            
            # Extract video ID from the filename
            path = song_data["path"]
            filename = path.split("/")[-1]
            video_id = filename.split(".")[0]  # Remove .flac extension
            
            # Use the extracted video ID instead of local-id
            song_id = video_id
            logger.info(f"Using video ID {video_id} from local song")
        except Exception as e:
            logger.error(f"Error extracting video ID from local song: {e}")
            return jsonify([])
    
    # Check if lyrics exist in SQLite cache
    cached_lyrics = get_cached_lyrics(song_id)
    if cached_lyrics:
        logger.info(f"Returning cached lyrics for {song_id}")
        return jsonify(cached_lyrics)
    
    # If not in cache, fetch from YTMusic
    try:
        watch_pl = ytmusic.get_watch_playlist(song_id)
        if not watch_pl or "lyrics" not in watch_pl:
            lbid = watch_pl.get("lyrics")
            if not lbid:
                return jsonify([])
        else:
            lbid = watch_pl["lyrics"]
        
        data = ytmusic.get_lyrics(lbid)
        if data and "lyrics" in data:
            lines = data["lyrics"].split("\n")
            lines.append("\n Sangeet Premium")
            
            # Save to SQLite cache
            cache_lyrics(song_id, lines)
            
            return jsonify(lines)
        return jsonify([])
    except Exception as e:
        logger.error(f"api_lyrics error: {e}")
        return jsonify([])
@bp.route("/api/downloads")
@login_required
def api_downloads():
    """Return all downloads that exist on disk."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT video_id, title, artist, album, downloaded_at
        FROM downloads
        ORDER BY downloaded_at DESC
    """)
    rows = c.fetchall()
    conn.close()

    items = []
    for vid, title, artist, album, ts in rows:
        flac_path = os.path.join(os.getenv("music_path"), f"{vid}.flac")
        if os.path.exists(flac_path):
            thumb = f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
            items.append({
                "id": vid,
                "title": title,
                "artist": artist,
                "album": album,
                "downloaded_at": ts,
                "thumbnail": thumb
            })
    return jsonify(items)






@bp.route('/api/resend-otp', methods=['POST'])
def resend_otp():
    try:
        data = request.json
        purpose = None
        email = None
        
        if 'login_token' in data:
            if 'temp_login' not in session:
                return jsonify({'error': 'Invalid session'}), 400
            temp = session['temp_login']
            
            if data['login_token'] != temp['token']:
                return jsonify({'error': 'Invalid token'}), 400
                
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute('SELECT email FROM users WHERE id = ?', (temp['user_id'],))
            email = c.fetchone()[0]
            conn.close()
            purpose = 'login'
            
        elif 'register_token' in data:
            if 'register_data' not in session:
                return jsonify({'error': 'Invalid session'}), 400
            reg = session['register_data']
            
            if data['register_token'] != reg['token']:
                return jsonify({'error': 'Invalid token'}), 400
                
            email = reg['email']
            purpose = 'register'
            
        else:
            return jsonify({'error': 'Invalid request'}), 400
            
        # Generate and send new OTP
        otp = util.generate_otp()
        util.store_otp(email, otp, purpose)
        util.send_email(
            email,
            'New Verification Code',
            f'Your new verification code is: {otp}'
        )
        
        return jsonify({'status': 'success'})
        
    except Exception as e:
        logger.error(f"Resend OTP error: {e}")
        return jsonify({'error': str(e)}), 500
@bp.route("/api/session-status")
def check_session_status():
    """Check if current session is still valid."""
    if 'user_id' not in session or 'session_token' not in session:
        return jsonify({
            "valid": False,
            "reason": "no_session"
        }), 401

    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        # Check if this specific session token is still valid
        c.execute("""
            SELECT COUNT(*) FROM active_sessions
            WHERE user_id = ? AND session_token = ?
            AND expires_at > CURRENT_TIMESTAMP
        """, (session['user_id'], session['session_token']))

        valid_session = c.fetchone()[0] > 0

        # Get total active sessions for this user
        c.execute("""
            SELECT COUNT(*) FROM active_sessions
            WHERE user_id = ?
            AND session_token != ?
            AND expires_at > CURRENT_TIMESTAMP
        """, (session['user_id'], session['session_token']))

        other_sessions = c.fetchone()[0] > 0

        conn.close()

        if not valid_session:
            reason = "logged_out_elsewhere" if other_sessions else "expired"
            return jsonify({
                "valid": False,
                "reason": reason
            }), 401

        return jsonify({"valid": True})

    except Exception as e:
        logger.error(f"Session check error: {e}")
        return jsonify({
            "valid": False,
            "reason": "error"
        }), 500
    
@bp.route("/design/<type>")
def design(type):
    css_dir = os.path.join(os.getcwd() , "design" , "css")
    if type == "index":
        return send_file(os.path.join(css_dir , "index.css") , mimetype="text/css")
    elif type == "embed":
        return send_file(os.path.join(css_dir , "embed.css") , mimetype="text/css")
    else:
        return 404





def get_video_info(video_id):
    try:
        # Retrieve song details via ytmusicapi
        song_info = ytmusic.get_song(video_id)
        details = song_info.get("videoDetails", {})
        title = details.get("title", "Unknown Title")
        artist = details.get("author", "Unknown Artist")
        thumbnails = details.get("thumbnail", {}).get("thumbnails", [])
        thumbnail = (max(thumbnails, key=lambda x: x.get("width", 0))["url"]
                     if thumbnails else f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg")
        return {"title": title, "artist": artist, "thumbnail": thumbnail, "video_id": video_id}
    except Exception:
        # Fallback: minimal extraction from YouTube page metadata
        url = f"https://www.youtube.com/watch?v={video_id}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            og_title = soup.find("meta", property="og:title")
            title = og_title["content"] if og_title else "Unknown Title"
            artist = "Unknown Artist"
            thumbnail = f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg"
            return {"title": title, "artist": artist, "thumbnail": thumbnail, "video_id": video_id}
    return {"title": "Unknown Title", "artist": "Unknown Artist",
            "thumbnail": f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg", "video_id": video_id}

def get_media_info(media_id):
    """
    Returns media details based on the given media_id.
    If media_id starts with 'local-', it fetches details from the local JSON file.
    Otherwise, it retrieves details using the YouTube Music API.
    """
    local_data = load_local_songs_from_file()
    if media_id.startswith("local-"):
        details = local_data.get(media_id)
        if details:
            # Ensure the returned dictionary has the keys expected by the template
            details["video_id"] = media_id
            return details
        else:
            return {"title": "Unknown Title", "artist": "Unknown Artist",
                    "thumbnail": "", "video_id": media_id}
    else:
        return get_video_info(media_id)

@bp.route('/share/open/<media_id>')
def share(media_id):
    info = get_media_info(media_id)
    share_url = request.url_root + f"?song={media_id}"
    return render_template('share.html', share_url=share_url, **info )







@bp.route('/stream2/open/<media_id>')
def stream2(media_id):
    local_data = load_local_songs_from_file()
    if media_id.startswith("local-"):
        # Stream local file using send_file
        details = local_data.get(media_id)
        if details and "path" in details:
            file_path = details["path"]
            print(file_path)
            return send_file(file_path)
        else:
            return "Local file not found", 404
    else:
        # For non-local videos, redirect to a streaming endpoint (replace with your logic)
        return redirect(f"/api/stream-file/{media_id}")




















# Get all playlists for the user
@bp.route('/api/playlists', methods=['GET'])
@login_required
def get_playlists():
    user_id = session['user_id']
    conn = sqlite3.connect(PLAYLIST_DB_PATH)
    c = conn.cursor()
    c.execute('''SELECT p.id, p.name, COUNT(ps.song_id) as song_count
                 FROM playlists p
                 LEFT JOIN playlist_songs ps ON p.id = ps.playlist_id
                 WHERE p.user_id = ?
                 GROUP BY p.id, p.name''', (user_id,))
    playlists = [{'id': row[0], 'name': row[1], 'song_count': row[2]} for row in c.fetchall()]
    conn.close()
    return jsonify(playlists)

# Create a new playlist
@bp.route('/api/playlists/create', methods=['POST'])
@login_required
def create_playlist():
    user_id = session['user_id']
    data = request.json
    name = data.get('name')
    if not name:
        return jsonify({'error': 'Playlist name is required'}), 400

    conn = sqlite3.connect(PLAYLIST_DB_PATH)
    c = conn.cursor()
    c.execute('INSERT INTO playlists (user_id, name, share_id) VALUES (?, ?, ?)',
              (user_id, name, secrets.token_urlsafe(16)))
    conn.commit()
    conn.close()
    return jsonify({'status': 'success'}), 201

# Add song to playlist
@bp.route('/api/playlists/add_song', methods=['POST'])
@login_required
def add_song_to_playlist():
    user_id = session['user_id']
    data = request.json
    playlist_id = data.get('playlist_id')
    song_id = data.get('song_id')

    if not playlist_id or not song_id:
        return jsonify({'error': 'Playlist ID and Song ID are required'}), 400

    conn = sqlite3.connect(PLAYLIST_DB_PATH)
    c = conn.cursor()
    c.execute('SELECT user_id FROM playlists WHERE id = ?', (playlist_id,))
    result = c.fetchone()
    if not result or result[0] != user_id:
        return jsonify({'error': 'Unauthorized or playlist not found'}), 403

    c.execute('INSERT OR IGNORE INTO playlist_songs (playlist_id, song_id) VALUES (?, ?)',
              (playlist_id, song_id))
    conn.commit()
    conn.close()
    return jsonify({'status': 'success'})
@bp.route('/api/playlists/<int:playlist_id>/songs', methods=['GET'])
@login_required
def get_playlist_songs(playlist_id):
    user_id = session['user_id']
    conn = sqlite3.connect(PLAYLIST_DB_PATH)
    c = conn.cursor()
    c.execute('SELECT user_id FROM playlists WHERE id = ?', (playlist_id,))
    result = c.fetchone()
    if not result or result[0] != user_id:
        return jsonify({'error': 'Unauthorized or playlist not found'}), 403

    c.execute('''SELECT ps.song_id
                 FROM playlist_songs ps
                 WHERE ps.playlist_id = ?''', (playlist_id,))
    song_ids = [row[0] for row in c.fetchall()]

    songs = []
    for song_id in song_ids:
        if song_id.startswith('local-'):
            meta = local_songs.get(song_id, {})
            songs.append({
                'id': song_id,
                'title': meta.get('title', 'Unknown'),
                'artist': meta.get('artist', 'Unknown Artist'),
                'thumbnail': meta.get('thumbnail', '/static/images/default-cover.jpg')
            })
        else:
            try:
                info = ytmusic.get_song(song_id)
                vd = info.get('videoDetails', {})
                thumbnails = vd.get('thumbnail', {}).get('thumbnails', [])
                if thumbnails:
                    # Select the highest-resolution thumbnail
                    best_thumbnail = max(thumbnails, key=lambda x: x.get('width', 0) * x.get('height', 0))
                    thumbnail_url = best_thumbnail['url']
                else:
                    # Fallback to standard YouTube thumbnail
                    thumbnail_url = f"https://i.ytimg.com/vi/{song_id}/hqdefault.jpg"
                songs.append({
                    'id': song_id,
                    'title': vd.get('title', 'Unknown'),
                    'artist': vd.get('author', 'Unknown Artist'),
                    'thumbnail': thumbnail_url
                })
            except Exception as e:
                logger.error(f"Error fetching song info for {song_id}: {e}")
                songs.append({
                    'id': song_id,
                    'title': 'Unknown',
                    'artist': 'Unknown Artist',
                    'thumbnail': '/static/images/default-cover.jpg'
                })
    conn.close()
    return jsonify(songs)

# Share playlist (make public)
@bp.route('/api/playlists/<int:playlist_id>/share', methods=['POST'])
@login_required
def share_playlist(playlist_id):
    user_id = session['user_id']
    conn = sqlite3.connect(PLAYLIST_DB_PATH)
    c = conn.cursor()
    c.execute('SELECT share_id FROM playlists WHERE id = ? AND user_id = ?', (playlist_id, user_id))
    result = c.fetchone()
    if not result:
        return jsonify({'error': 'Unauthorized or playlist not found'}), 403

    share_id = result[0]
    c.execute('UPDATE playlists SET is_public = 1 WHERE id = ?', (playlist_id,))
    conn.commit()
    conn.close()
    return jsonify({'share_id': share_id})

# Import shared playlist
@bp.route('/playlists/share/<share_id>', methods=['GET'])
@login_required
def import_shared_playlist(share_id):
    user_id = session['user_id']
    conn = sqlite3.connect(PLAYLIST_DB_PATH)
    c = conn.cursor()
    c.execute('SELECT id, name FROM playlists WHERE share_id = ? AND is_public = 1', (share_id,))
    playlist = c.fetchone()
    if not playlist:
        return jsonify({'error': 'Playlist not found or not public'}), 404

    playlist_id, name = playlist
    c.execute('SELECT song_id FROM playlist_songs WHERE playlist_id = ?', (playlist_id,))
    song_ids = [row[0] for row in c.fetchall()]

    # Create a new playlist for the user
    new_share_id = secrets.token_urlsafe(16)
    c.execute('INSERT INTO playlists (user_id, name, share_id) VALUES (?, ?, ?)',
              (user_id, f"{name} (Imported)", new_share_id))
    new_playlist_id = c.lastrowid

    for song_id in song_ids:
        c.execute('INSERT INTO playlist_songs (playlist_id, song_id) VALUES (?, ?)',
                  (new_playlist_id, song_id))
    conn.commit()
    conn.close()

    return redirect('/?playlist_added=true')



