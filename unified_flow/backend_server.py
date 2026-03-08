from flask import Flask, request, jsonify
from flask_cors import CORS
import subprocess
import os
import uuid
import json

app = Flask(__name__)
CORS(app)  # Allow Vercel frontend to access this API

# Configuration
OUTPUT_BASE = "output"
os.makedirs(OUTPUT_BASE, exist_ok=True)

@app.route('/generate', methods=['POST'])
def generate():
    data = request.json
    prompt = data.get('prompt')
    if not prompt:
        return jsonify({"error": "Prompt required"}), 400

    run_id = uuid.uuid4().hex[:8]
    print(f"Starting generation for {run_id}: {prompt}")

    # Standard command to run the existing pipeline
    # We use run_pipeline_v2.py which handles everything
    try:
        process = subprocess.Popen(
            ['python', 'run_pipeline_v2.py', prompt],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env={**os.environ, "PYTHONUNBUFFERED": "1"}
        )
        
        stdout, stderr = process.communicate()
        
        # Look for the URL or file in output
        url_match = None
        for line in stdout.splitlines():
            if "[APP_OUTPUT_URL]:" in line:
                url_match = line.split("[APP_OUTPUT_URL]:")[1].strip()
            elif "[APP_LOCAL_FILE]:" in line:
                # If it's a local file, we might need to serve it or it's already in S3
                pass

        if process.returncode != 0:
            return jsonify({"error": "Pipeline failed", "log": stderr[-500:]}), 500

        return jsonify({
            "status": "success",
            "run_id": run_id,
            "video_url": url_match
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    return "OK", 200

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
