import subprocess
import time
import sys
from flask import Flask, Response, request, jsonify
import yt_dlp

app = Flask(__name__)

# -------------------------------------------------------------------------
# CONFIGURATION
# -------------------------------------------------------------------------
playlist = ["https://soundcloud.com/tung-do-688896603/sets/piece-of-mind"]
current_song_index = 0
current_title = "Waiting for stream..."
current_ffmpeg_process = None
current_yt_process = None 

# AUDIO SETTINGS
AUDIO_BITRATE = '128k'
CHUNK_SIZE = 2048      

def expand_playlist(url):
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

        # Unpack Playlist
        if "/sets/" in track_link or "playlist" in track_link:
            sub_tracks = expand_playlist(track_link)
            if sub_tracks:
                playlist.pop(current_song_index)
                for t in reversed(sub_tracks):
                    playlist.insert(current_song_index, t)
                continue
            else:
                current_song_index += 1
                continue

        # Get Title
        try:
            with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                info = ydl.extract_info(track_link, download=False)
                current_title = info.get('title', 'Unknown Track')
        except:
            current_title = "Unknown Track"
        print(f"--> Playing: {current_title}")

        # PIPING STRATEGY
        yt_cmd = [sys.executable, '-m', 'yt_dlp', '--quiet', '--no-playlist', '-o', '-', track_link]
        
        ffmpeg_cmd = [
            'ffmpeg', '-i', 'pipe:0', '-f', 'mp3', 
            '-acodec', 'libmp3lame', '-ar', '44100', '-ac', '2',
            '-ab', AUDIO_BITRATE, '-minrate', AUDIO_BITRATE, '-maxrate', AUDIO_BITRATE,
            '-bufsize', str(int(AUDIO_BITRATE.replace('k','')) * 2) + 'k',
            '-af', 'volume=0.8', '-'
        ]
        
        try:
            current_yt_process = subprocess.Popen(yt_cmd, stdout=subprocess.PIPE)
            current_ffmpeg_process = subprocess.Popen(ffmpeg_cmd, stdin=current_yt_process.stdout, stdout=subprocess.PIPE, stderr=None)
            
            while True:
                data = current_ffmpeg_process.stdout.read(CHUNK_SIZE)
                if not data: break
                yield data
                
        except Exception as e:
            print(f"Streaming Error: {e}")
        finally:
            if current_yt_process: current_yt_process.kill()
            if current_ffmpeg_process: current_ffmpeg_process.kill()
        
        current_song_index += 1

# --- NEW TEST ENDPOINT ---
@app.route('/test')
def test_tone():
    """Generates a 440Hz Sine Wave (Beep) to test audio hardware"""
    ffmpeg_cmd = [
        'ffmpeg', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=10',
        '-f', 'mp3', '-acodec', 'libmp3lame', '-ab', '128k', '-ar', '44100', '-ac', '2', '-'
    ]
    process = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=None)
    def generate():
        while True:
            data = process.stdout.read(CHUNK_SIZE)
            if not data: break
            yield data
    return Response(generate(), mimetype='audio/mpeg')

@app.route('/stream')
def stream():
    return Response(audio_generator(), mimetype='audio/mpeg', headers={"Transfer-Encoding": "chunked"})

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
    app.run(host='0.0.0.0', port=5000, threaded=True)
