import subprocess
import time
import sys
from flask import Flask, Response, request
import yt_dlp

app = Flask(__name__)

# -------------------------------------------------------------------------
# CONFIGURATION
# -------------------------------------------------------------------------
playlist = [
    "https://soundcloud.com/tung-do-688896603/sets/piece-of-mind",
    "https://soundcloud.com/tung-do-688896603/sets/cool-stuffs"
]

current_song_index = 0
# -------------------------------------------------------------------------

def expand_playlist(url):
    """Checks if a URL is a Set/Playlist and returns list of tracks."""
    ydl_opts = {
        'extract_flat': True, 
        'quiet': True,
    }
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
    global current_song_index, playlist
    
    while True:
        if not playlist:
            time.sleep(1)
            continue
            
        if current_song_index >= len(playlist):
            current_song_index = 0
            
        track_link = playlist[current_song_index]
        print(f"--> Processing: {track_link}")

        # 1. Unpack Playlist if needed
        if "/sets/" in track_link or "playlist" in track_link:
            sub_tracks = expand_playlist(track_link)
            if sub_tracks:
                print(f"    Found Playlist! Unpacking {len(sub_tracks)} songs...")
                playlist.pop(current_song_index)
                # Reverse insert to keep order
                for t in reversed(sub_tracks):
                    playlist.insert(current_song_index, t)
                continue
            # If unpack fails, try playing it as a track (fallback)

        # 2. Get Metadata (Title only) - We don't need the URL anymore!
        title = "Unknown Track"
        try:
            with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                info = ydl.extract_info(track_link, download=False)
                title = info.get('title', 'Unknown Track')
        except:
            pass
            
        print(f"--> Playing: {title}")

        # 3. THE PIPELINE STRATEGY
        # yt-dlp (downloader) -> Pipe -> FFmpeg (converter) -> Pipe -> Flask
        
        # Producer: yt-dlp dumps raw audio to STDOUT
        yt_cmd = [
            sys.executable, '-m', 'yt_dlp', 
            '--quiet', '--no-playlist', 
            '-o', '-', # Output to stdout
            track_link
        ]
        
        # Consumer: FFmpeg reads from STDIN
        ffmpeg_cmd = [
            'ffmpeg',
            '-i', 'pipe:0',          # Read input from the pipe (yt-dlp)
            '-f', 'mp3',             # Output MP3
            '-acodec', 'libmp3lame',
            '-ab', '128k', 
            '-ar', '44100', 
            '-ac', '2', 
            '-'                      # Write output to stdout (Flask)
        ]
        
        yt_process = None
        ffmpeg_process = None

        try:
            # Start yt-dlp
            yt_process = subprocess.Popen(yt_cmd, stdout=subprocess.PIPE)
            
            # Start FFmpeg, connecting yt-dlp's output to its input
            ffmpeg_process = subprocess.Popen(
                ffmpeg_cmd, 
                stdin=yt_process.stdout, 
                stdout=subprocess.PIPE,
                stderr=None # Keep stderr visible for debugging
            )
            
            # Read from FFmpeg's output
            chunk_size = 4096
            while True:
                data = ffmpeg_process.stdout.read(chunk_size)
                if not data: break
                yield data
                
        except Exception as e:
            print(f"Streaming Error: {e}")
        finally:
            # Cleanup processes
            if yt_process: yt_process.kill()
            if ffmpeg_process: ffmpeg_process.kill()

        print("--> Song finished.")
        current_song_index += 1

@app.route('/stream')
def stream():
    return Response(audio_generator(), mimetype='audio/mpeg')

@app.route('/next')
def next_track():
    global current_song_index
    current_song_index += 1
    return "Skipped", 200

@app.route('/prev')
def prev_track():
    global current_song_index
    current_song_index -= 1
    return "Previous", 200

@app.route('/add')
def add_track():
    url = request.args.get('url')
    if url:
        playlist.append(url)
        return f"Added: {url}", 200
    return "Missing url", 400

if __name__ == '__main__':
    print("Server running on port 5000...")
    app.run(host='0.0.0.0', port=5000, threaded=True)