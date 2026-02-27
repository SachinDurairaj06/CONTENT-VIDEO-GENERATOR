"""
Background Music Module

Provides sentiment-based background music track selection and mixing.
The PRD specifies that audio sentiment (e.g., "warm", "festive", "professional")
should drive track selection for the final video.

In production, this would pull from an S3 library of royalty-free tracks.
For MVP, it defines the track mapping and FFmpeg mix logic.
"""
import os

BUCKET_NAME = os.environ.get('ASSETS_BUCKET', 'unified-flow-assets-bucket')

# Mapping of sentiment keywords to music track S3 keys
# These would be pre-uploaded royalty-free tracks in S3
MUSIC_LIBRARY = {
    "warm": {
        "track_key": "music/warm_acoustic.mp3",
        "description": "Light acoustic guitar, gentle, wholesome",
        "volume": 0.15  # Background volume relative to voiceover
    },
    "festive": {
        "track_key": "music/festive_dhol.mp3",
        "description": "Upbeat dhol and shehnai, celebratory Indian festival music",
        "volume": 0.20
    },
    "professional": {
        "track_key": "music/corporate_ambient.mp3",
        "description": "Clean ambient corporate, subtle piano and synth pads",
        "volume": 0.10
    },
    "energetic": {
        "track_key": "music/energetic_beat.mp3",
        "description": "Upbeat electronic with tabla fusion, high energy",
        "volume": 0.18
    },
    "calm": {
        "track_key": "music/calm_sitar.mp3",
        "description": "Gentle sitar and flute, meditative, trustworthy",
        "volume": 0.12
    },
    "romantic": {
        "track_key": "music/romantic_strings.mp3",
        "description": "Soft string ensemble, emotional, cinematic",
        "volume": 0.15
    },
    "inspiring": {
        "track_key": "music/inspiring_orchestral.mp3",
        "description": "Building orchestral crescendo, motivational",
        "volume": 0.15
    },
    "nostalgic": {
        "track_key": "music/nostalgic_keys.mp3",
        "description": "Soft piano with vinyl crackle, lo-fi warmth",
        "volume": 0.12
    }
}

# Default fallback
DEFAULT_SENTIMENT = "warm"


def get_music_track(sentiment: str) -> dict:
    """
    Returns the music track config for a given sentiment.
    Falls back to 'warm' if the sentiment is not found.
    """
    # Normalize and try to find a match
    sentiment_lower = sentiment.lower().strip()

    # Direct match
    if sentiment_lower in MUSIC_LIBRARY:
        return MUSIC_LIBRARY[sentiment_lower]

    # Fuzzy match: check if any key is contained in the sentiment string
    for key in MUSIC_LIBRARY:
        if key in sentiment_lower:
            return MUSIC_LIBRARY[key]

    return MUSIC_LIBRARY[DEFAULT_SENTIMENT]


def build_music_mix_ffmpeg_args(
    video_path: str,
    voiceover_path: str,
    music_path: str,
    output_path: str,
    music_volume: float = 0.15
) -> list:
    """
    Builds FFmpeg arguments to mix voiceover (primary) with background
    music (secondary at reduced volume) and overlay onto video.

    Uses amix filter with volume adjustment to keep voiceover dominant.
    """
    return [
        "-i", video_path,
        "-i", voiceover_path,
        "-i", music_path,
        "-filter_complex",
        f"[2:a]volume={music_volume}[bg];"
        f"[1:a][bg]amix=inputs=2:duration=first:dropout_transition=3[aout]",
        "-map", "0:v",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac",
        "-shortest",
        output_path
    ]
