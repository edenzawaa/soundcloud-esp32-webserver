import subprocess
import time
import sys
import threading
from flask import Flask, Response, request, jsonify
import yt_dlp

app = Flask(__name__)

# -------------------------------------------------------------------------
# GLOBAL STATE
# -------------------------------------------------------------------------
playlist = [
    "https://soundcloud.com/tung-do-688896603/sets/piece-of-mind"
]
current_song_index = 0
current_title = "Waiting for stream..."
current_ffmpeg_process = None
current_yt_process = None 
# -------------------------------------------------------------------------

def expand_playlist(url):
    """Checks if a URL is a Set/Playlist."""
    ydl_opts = {'extract_flat': True, 'quiet': True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if 'entries' in info:
                return [entry['url'] for entry in info['entries'] if entry]
            return None 
    except Exception as e:
        print(f"Error expanding playlist: {e}")
        return None

def audio_generator():
    global current_song_index, playlist, current_title, current_ffmpeg_process, current_yt_process
    
    while True:
        if not playlist:
            time.sleep(1)
            continue
            
        if current_song_index >= len(playlist):
            current_song_index = 0
            
        track_link = playlist[current_song_index]
        print(f"--> Processing: {track_link}")

        # 1. Unpack Playlist
        if "/sets/" in track_link or "playlist" in track_link:
            sub_tracks = expand_playlist(track_link)
            if sub_tracks:
                print(f"    Found Playlist! Unpacking {len(sub_tracks)} songs...")
                playlist.pop(current_song_index)
                for t in reversed(sub_tracks):
                    playlist.insert(current_song_index, t)
                continue
            else:
                current_song_index += 1
                continue

        # 2. Get Title (Metadata Only)
        try:
            with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                info = ydl.extract_info(track_link, download=False)
                current_title = info.get('title', 'Unknown Track')
        except:
            current_title = "Unknown Track"
            
        print(f"--> Playing: {current_title}")

        # 3. PIPING STRATEGY (Fixes 'Invalid Argument' errors)
        yt_cmd = [
            sys.executable, '-m', 'yt_dlp', 
            '--quiet', '--no-playlist', 
            '-o', '-', # Output raw audio to stdout
            track_link
        ]
        
        ffmpeg_cmd = [
            'ffmpeg',
            '-i', 'pipe:0',          # Read from stdin (yt-dlp)
            '-f', 'mp3',             # Output format
            '-acodec', 'libmp3lame',
            '-ab', '128k', '-ar', '44100', '-ac', '2', 
            '-'                      # Write to stdout (Flask)
        ]
        
        try:
            current_yt_process = subprocess.Popen(yt_cmd, stdout=subprocess.PIPE)
            
            current_ffmpeg_process = subprocess.Popen(
                ffmpeg_cmd, 
                stdin=current_yt_process.stdout, 
                stdout=subprocess.PIPE, 
                stderr=None 
            )
            
            chunk_size = 4096
            while True:
                data = current_ffmpeg_process.stdout.read(chunk_size)
                if not data: break
                yield data
                
        except Exception as e:
            print(f"Streaming Error: {e}")
        finally:
            if current_yt_process: current_yt_process.kill()
            if current_ffmpeg_process: current_ffmpeg_process.kill()
        
        current_song_index += 1

# --- API ENDPOINTS ---

@app.route('/stream')
def stream():
    return Response(audio_generator(), mimetype='audio/mpeg')

@app.route('/metadata')
def metadata():
    return jsonify({'title': current_title, 'index': current_song_index, 'total': len(playlist)})

@app.route('/play')
def play_playlist():
    global playlist, current_song_index
    url = request.args.get('url')
    if url:
        playlist = [url]
        current_song_index = 0
        kill_current_stream()
        return "Playing new list", 200
    return "Missing url", 400

@app.route('/next')
def next_track():
    global current_song_index
    current_song_index += 1
    kill_current_stream()
    return "Skipped", 200

@app.route('/prev')
def prev_track():
    global current_song_index
    current_song_index -= 1
    kill_current_stream()
    return "Previous", 200

def kill_current_stream():
    if current_yt_process: current_yt_process.kill()
    if current_ffmpeg_process: current_ffmpeg_process.kill()

if __name__ == '__main__':
    print("Server running on port 5000...")
    app.run(host='0.0.0.0', port=5000, threaded=True)
