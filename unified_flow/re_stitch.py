import sys, os
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from run_pipeline_v2 import _ffmpeg_fallback_compose, OUTPUT_DIR

# Set up the existing output dir environment
import run_pipeline_v2
run_pipeline_v2.OUTPUT_DIR = 'output/c778da83'
run_pipeline_v2.S3_BUCKET = 'unified-flow-assets'

clip_paths = ['output/c778da83/clip_1.mp4']
audio_path = 'output/c778da83/voiceover.mp3'
bgm_path = 'output/c778da83/bgm.mp3'

print("Retrying FFmpeg stitch...")
res = run_pipeline_v2._ffmpeg_fallback_compose(clip_paths, audio_path, bgm_path)
print(res)
