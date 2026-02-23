import os
import uuid
import subprocess
import tempfile
import threading
import json
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

DOWNLOAD_DIR = tempfile.mkdtemp()
jobs = {}

with open('index.html') as f:
    HTML = f.read()

@app.route('/')
def index():
    return HTML

@app.route('/api/search', methods=['POST'])
def search():
    data = request.json
    query = data.get('query', '').strip()
    page = int(data.get('page', 1))
    if not query:
        return jsonify({'error': 'No query provided'}), 400
    try:
        per_page = 10
        fetch = per_page * page
        result = subprocess.run(
            ['yt-dlp', f'ytsearch{fetch}:{query} official audio',
             '--match-filter', '!is_live & duration>60',
             '--no-playlist', '--skip-download',
             '--print', '%(title)s|||%(uploader)s|||%(duration)s|||%(webpage_url)s|||%(thumbnail)s'],
            capture_output=True, text=True, timeout=30
        )
        lines = [l.strip() for l in result.stdout.strip().split('\n') if '|||' in l]
        # Return only current page slice
        page_lines = lines[(page-1)*per_page : page*per_page]
        tracks = []
        for line in page_lines:
            parts = line.split('|||')
            if len(parts) >= 4:
                dur = int(parts[2]) if parts[2].isdigit() else 0
                mins = dur // 60
                secs = dur % 60
                tracks.append({
                    'title': parts[0],
                    'uploader': parts[1],
                    'duration': f'{mins}:{secs:02d}',
                    'url': parts[3],
                    'thumb': parts[4] if len(parts) > 4 else ''
                })
        return jsonify({'tracks': tracks, 'page': page, 'has_more': len(lines) >= fetch})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/pull', methods=['POST'])
def pull():
    data = request.json
    query = data.get('query', '').strip()
    url = data.get('url', '').strip()
    if not query and not url:
        return jsonify({'error': 'No query provided'}), 400
    job_id = str(uuid.uuid4())
    jobs[job_id] = {'status': 'starting', 'file': None, 'error': None}
    thread = threading.Thread(target=run_download, args=(job_id, url or query, bool(url)))
    thread.daemon = True
    thread.start()
    return jsonify({'job_id': job_id})

@app.route('/api/status/<job_id>')
def status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    return jsonify(job)

@app.route('/api/download/<job_id>')
def download(job_id):
    job = jobs.get(job_id)
    if not job or not job.get('file'):
        return jsonify({'error': 'File not ready'}), 404
    filepath = job['file']
    if not os.path.exists(filepath):
        return jsonify({'error': 'File not found'}), 404
    return send_file(filepath, as_attachment=True)

def run_download(job_id, target, is_url=False):
    out_dir = os.path.join(DOWNLOAD_DIR, job_id)
    os.makedirs(out_dir, exist_ok=True)
    jobs[job_id]['status'] = 'pulling...'
    try:
        source = target if is_url else f'ytsearch1:{target} official audio'
        cmd = ['yt-dlp', source,
               '--match-filter', '!is_live & duration>60',
               '--extract-audio', '--audio-format', 'mp3', '--audio-quality', '0',
               '--prefer-free-formats', '--format', 'bestaudio[ext!=webm]/bestaudio',
               '-o', out_dir + '/%(title)s.%(ext)s',
               '--no-playlist', '--output-na-placeholder', '']
        if not is_url:
            cmd += ['--playlist-items', '1']
        subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        files = [f for f in os.listdir(out_dir) if f.endswith('.mp3')]
        if files:
            jobs[job_id].update({'status': 'done', 'file': os.path.join(out_dir, files[0]), 'filename': files[0]})
            return
    except Exception:
        pass
    jobs[job_id].update({'status': 'error', 'error': 'Download failed'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
