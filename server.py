import os
import uuid
import subprocess
import tempfile
import threading
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

@app.route('/api/pull', methods=['POST'])
def pull():
    data = request.json
    query = data.get('query', '').strip()
    if not query:
        return jsonify({'error': 'No query provided'}), 400
    job_id = str(uuid.uuid4())
    jobs[job_id] = {'status': 'starting', 'file': None, 'error': None}
    thread = threading.Thread(target=run_download, args=(job_id, query))
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

def run_download(job_id, query):
    out_dir = os.path.join(DOWNLOAD_DIR, job_id)
    os.makedirs(out_dir, exist_ok=True)

    jobs[job_id]['status'] = 'trying spotdl...'
    try:
        subprocess.run(
            ['spotdl', 'download', query, '--output', out_dir + '/{artist} - {title}.{output-ext}', '--format', 'flac'],
            capture_output=True, text=True, timeout=60
        )
        files = [f for f in os.listdir(out_dir) if f.endswith('.flac')]
        if files:
            jobs[job_id].update({'status': 'done', 'file': os.path.join(out_dir, files[0]), 'filename': files[0]})
            return
    except Exception:
        pass

    jobs[job_id]['status'] = 'spotdl failed — trying yt-dlp...'
    try:
        subprocess.run(
            ['yt-dlp', f'ytsearch5:{query} official audio',
             '--match-filter', '!is_live & duration>60',
             '--extract-audio', '--audio-format', 'mp3', '--audio-quality', '0',
             '-o', out_dir + '/%(artist)s - %(title)s.%(ext)s',
             '--no-playlist', '--playlist-items', '1'],
            capture_output=True, text=True, timeout=120
        )
        files = [f for f in os.listdir(out_dir) if f.endswith('.mp3')]
        if files:
            jobs[job_id].update({'status': 'done', 'file': os.path.join(out_dir, files[0]), 'filename': files[0]})
            return
    except Exception:
        pass

    jobs[job_id].update({'status': 'error', 'error': 'All engines failed'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
