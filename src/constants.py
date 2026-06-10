import sys
from datetime import date

sys.path.append('../src')

from src.tools import *

# =============================================================================
# Paths
# =============================================================================

VIDEO_PATH   = 'data/meteo4.mp4'
AUDIO_PATH   = 'data/meteoaudio.mp3'
MODEL_PATH   = 'model/pose_landmarker_full.task'
OUTPUT_DIR   = 'outputs'
OUTPUT_CSV   = 'outputs/video_parts.csv'
MOVEMENT_CSV = 'outputs/movement_all.csv'
AUDIO_CSV    = 'outputs/audio_data.csv'

DATA_PATH = "data/participants/"

# =============================================================================
# Landmark tracking
# =============================================================================

TRACKS = [
    "NOSE",
    "LEFT_SHOULDER", "RIGHT_SHOULDER",
    "LEFT_ELBOW",    "RIGHT_ELBOW",
    "LEFT_WRIST",    "RIGHT_WRIST",
    "LEFT_INDEX",    "RIGHT_INDEX",
]

KEYPOINTS = {
    0:  'NOSE',
    1:  'LEFT_EYE_INNER',
    2:  'LEFT_EYE',
    3:  'LEFT_EYE_OUTER',
    4:  'RIGHT_EYE_INNER',
    5:  'RIGHT_EYE',
    6:  'RIGHT_EYE_OUTER',
    7:  'LEFT_EAR',
    8:  'RIGHT_EAR',
    9:  'MOUTH_LEFT',
    10: 'MOUTH_RIGHT',
    11: 'LEFT_SHOULDER',
    12: 'RIGHT_SHOULDER',
    13: 'LEFT_ELBOW',
    14: 'RIGHT_ELBOW',
    15: 'LEFT_WRIST',
    16: 'RIGHT_WRIST',
    17: 'LEFT_PINKY',
    18: 'RIGHT_PINKY',
    19: 'LEFT_INDEX',
    20: 'RIGHT_INDEX',
    21: 'LEFT_THUMB',
    22: 'RIGHT_THUMB',
    23: 'LEFT_HIP',
    24: 'RIGHT_HIP',
    25: 'LEFT_KNEE',
    26: 'RIGHT_KNEE',
    27: 'LEFT_ANKLE',
    28: 'RIGHT_ANKLE',
    29: 'LEFT_HEEL',
    30: 'RIGHT_HEEL',
    31: 'LEFT_FOOT_INDEX',
    32: 'RIGHT_FOOT_INDEX',
}

KEYPOINTS_INVERTED = {v: k for k, v in KEYPOINTS.items()}
TRACKS_NUMBERS     = [KEYPOINTS_INVERTED[track] for track in TRACKS]

# =============================================================================
# Peak detection parameters
# =============================================================================

THRESHOLD_PERCENTILE = 75
PEAK_DISTANCE        = 5

# =============================================================================
# MediaPipe pose landmarker
# =============================================================================

_base_options = python.BaseOptions(
    model_asset_path=MODEL_PATH,
    # delegate=python.BaseOptions.Delegate.GPU
)

_options = vision.PoseLandmarkerOptions(
    base_options=_base_options,
    output_segmentation_masks=True,
)

LANDMARKER = vision.PoseLandmarker.create_from_options(_options)

# =============================================================================
# Misc
# =============================================================================
THIS_YEAR = date.today().year
BACKGROUND = "darkgray"