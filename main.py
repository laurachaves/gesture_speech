import os
import cv2
import numpy as np
import pandas as pd
from scipy.signal import find_peaks
import matplotlib.pyplot as plt
import seaborn as sns

from constants import (
    VIDEO_PATH, AUDIO_PATH, OUTPUT_DIR,
    MOVEMENT_CSV, AUDIO_CSV,
    TRACKS, KEYPOINTS, LANDMARKER,
    THRESHOLD_PERCENTILE, PEAK_DISTANCE,
)
from tools import (
    movement_extraction, plot_velocity_acc,
    plot_pitch, f0_extract, nearest_event, histo,
)

# =============================================================================
# Setup
# =============================================================================

os.makedirs(OUTPUT_DIR, exist_ok=True)

# =============================================================================
# Extracting landmarks
# =============================================================================

movement_extraction(VIDEO_PATH, TRACKS, LANDMARKER, OUTPUT_DIR, False, KEYPOINTS)

# =============================================================================
# Plotting graphs for velocity and acceleration
# =============================================================================

plot_velocity_acc(MOVEMENT_CSV, TRACKS, OUTPUT_DIR)

# =============================================================================
# Synching the audio with the gestures
# =============================================================================

plot_pitch(AUDIO_PATH, OUTPUT_DIR)
f0_extract(AUDIO_PATH, AUDIO_CSV)

cap = cv2.VideoCapture(VIDEO_PATH)
fps = cap.get(cv2.CAP_PROP_FPS)
cap.release()
dt = 1 / fps

audio_data   = pd.read_csv(AUDIO_CSV)
f0           = audio_data['f0']
time_pitch   = audio_data['time_pitch']
movement_all = pd.read_csv(MOVEMENT_CSV)

# =============================================================================
# Histogram: gesture peaks vs pitch peaks
# =============================================================================

histo(
    MOVEMENT_CSV, TRACKS, AUDIO_CSV, fps, OUTPUT_DIR,
    threshold_percentile=THRESHOLD_PERCENTILE,
    peak_distance=PEAK_DISTANCE,
)
