import cv2
import mediapipe as mp
import csv
import matplotlib.pyplot as plt
import math
import parselmouth
from scipy.signal import find_peaks
import numpy as np
import pandas as pd
import seaborn as sns
from mediapipe.tasks.python import vision
from mediapipe.tasks import python
import os
from pathlib import Path


def extract_landmarks(results, tracks_numbers):
    """
    This is a function to be used inside the movement extraction function.
    """
    row = []
    if results.pose_world_landmarks:
        landmarks = results.pose_world_landmarks
        for idx in tracks_numbers:
            lm = landmarks[0][idx]
            if lm.visibility > 0.5:
                row.extend([lm.x, lm.y, lm.z])
            else:
                row.extend([None, None, None])
    else:
        row.extend([None] * (len(tracks_numbers) * 3))
    return row


def movement_extraction(video_path, landmarks, landmarker, outputs_destination, make_frames=False, keypoints=None):
    """
    The code receives the video as an input and creates the csv files with the movements and creates the images of the frames with each landmark extracted

    Args:
        video_path: String or list of strings with video paths
        landmarks: list with each landmark to be tracked
        landmarker: instantiation of MediaPipe, in this notebook it is stated in the Initialization cell
        outputs_destination: string with the directory of the output destination
        make_frames: True if user wants to have each frame with the landmarks tracked generated, False otherwise
        keypoints: Dictionary with the relation of each landmark with a number, needed for MediaPipe purposes

    Returns:
        Doesn't return anything, just creates files
    """
    Path(outputs_destination).mkdir(parents=True, exist_ok=True)
    if keypoints is None:
        raise ValueError("Must set keypoints")
    keypoints_inverted = {v: k for k, v in keypoints.items()}
    tracks_numbers = [keypoints_inverted[landmark] for landmark in landmarks]
    outputs = []
    if isinstance(video_path, str):
        video_path = [video_path]
    for video in video_path:
        p = Path(video)
        outputs.append(Path(outputs_destination) / "parts.csv")
        cap = cv2.VideoCapture(video)
        frame_number = 0
        csv_data = []
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
            result = landmarker.detect(mp_image)
            row = extract_landmarks(result, tracks_numbers)
            csv_data.append(row)

            if result.pose_landmarks:
                for idx in tracks_numbers:
                    lm = result.pose_landmarks[0][idx]
                    h, w, _ = frame.shape
                    cx, cy = int(lm.x * w), int(lm.y * h)
                    cv2.circle(frame, (cx, cy), 6, (0, 255, 0), -1)
            if make_frames:
                frame_path = Path(outputs_destination) / f"{p.stem}_frame_{frame_number}.png"
                cv2.imwrite(str(frame_path), frame)
                frame_number += 1
        cap.release()
        print(f"Processed frames: {len(csv_data)}")
        output = outputs[-1]
        with open(output, 'w', newline='') as f:
            writer = csv.writer(f)
            header = []
            for name in landmarks:
                header.extend([f"{name}_x", f"{name}_y", f"{name}_z"])
            writer.writerow(header)
            for row in csv_data:
                writer.writerow(row)

        movement_csv = Path(outputs_destination) / "movement_all.csv"
        all_movement = {}
        all_accel = {}

        for lm_idx, lm_name in enumerate(landmarks):
            movement = [0.0]
            acceleration = [0.0]
            col = lm_idx * 3
            for i in range(1, len(csv_data)):
                prev = csv_data[i - 1]
                curr = csv_data[i]
                if None not in (prev[col], curr[col]):
                    dx = curr[col] - prev[col]
                    dy = curr[col + 1] - prev[col + 1]
                    dz = curr[col + 2] - prev[col + 2]
                    dist = math.sqrt(dx * dx + dy * dy + dz * dz)
                else:
                    dist = 0.0
                movement.append(dist)
                accel = dist - movement[i - 1]
                acceleration.append(accel)
            all_movement[lm_name] = movement
            all_accel[lm_name] = acceleration

        with open(movement_csv, 'w', newline='') as f:
            writer = csv.writer(f)
            movement_header = ['frame']
            for lm_name in landmarks:
                movement_header.extend([f'movement_{lm_name}', f'acceleration_{lm_name}'])
            writer.writerow(movement_header)
            for i in range(len(csv_data)):
                row = [i]
                for lm_name in landmarks:
                    row.extend([all_movement[lm_name][i], all_accel[lm_name][i]])
                writer.writerow(row)


def plot_velocity_acc(csv_path, landmarks, output_path, peak=False, fps=None, threshold_percentile=75, peak_distance=5):
    """
    The code plots the acceleration and the velocity of the specified landmarks from a specified CSV file

    Args:
        csv_path: The path for the csv file, including the csv (e.g. "../outputs/meteo4_movement_all.csv")
        landmarks: list with each landmark to be tracked
        output_path: directory where the plots will be saved
        peak: If True, highlights detected peaks on the plot
        fps: Frames per second of the video, required if peak is True
        threshold_percentile: Percentile threshold for peak detection
        peak_distance: Minimum distance between peaks

    Returns:
        Doesn't return anything, just plots the results
    """
    with open(csv_path, newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = list(reader)

    if peak:
        if fps is None:
            raise ValueError("fps is required if peaks is True")
        movement_all = pd.read_csv(csv_path)
        dt = 1 / fps
        time = np.array([i * dt for i in range(len(movement_all))])
        for lm in landmarks:
            for metric, col_name, ylabel in [
                ("velocity", f"movement_{lm}", f"Velocity of {lm}"),
                ("acceleration", f"acceleration_{lm}", f"Acceleration of {lm}"),
            ]:
                signal = np.array(movement_all[col_name])
                threshold = np.percentile(signal, threshold_percentile)
                peaks, _ = find_peaks(signal, height=threshold, distance=peak_distance)
                plt.figure()
                plt.plot(time, signal, label=metric.capitalize())
                plt.scatter(time[peaks], signal[peaks], color="red", zorder=5,
                            label=f"Peaks (≥ p{threshold_percentile}, dist{peak_distance})")
                plt.xlabel("Time (s)")
                plt.ylabel(ylabel)
                plt.title(f"Evolution of {metric} of {lm} throughout the video")
                plt.legend()
                plt.savefig(os.path.join(output_path, f"{metric}_{lm}.png"))

    else:
        for lm in landmarks:
            mov_col = header.index(f'movement_{lm}')
            accel_col = header.index(f'acceleration_{lm}')

            frames = [int(row[0]) for row in rows]
            movement = [float(row[mov_col]) for row in rows]
            acceleration = [float(row[accel_col]) for row in rows]

            plt.figure(figsize=(15, 8))
            plt.plot(frames, movement)
            plt.xlabel("Frame")
            plt.ylabel(f"Velocity of {lm}")
            plt.title(f"Evolution of velocity of {lm} throughout the video")
            plt.savefig(os.path.join(output_path, f"velocity_{lm}.png"))


            plt.figure(figsize=(15, 8))
            plt.plot(frames, acceleration)
            plt.xlabel("Frame")
            plt.ylabel("Acceleration")
            plt.title(f"Evolution of acceleration of {lm} throughout the video")
            plt.savefig(os.path.join(output_path, f"acceleration_{lm}.png"))



def plot_pitch(audio_path, output_path, time_step=0.00333, pitch_floor=100.0, pitch_ceiling=500.0,
               peak=False, threshold_percentile=75, threshold_distance=75, peak_distance=5):
    """
    Plots the pitch (F0) contour of an audio file.

    Args:
        audio_path: The path for the audio file, eg "../data/meteoaudio.mp3"
        output_path: directory where the plot will be saved
        time_step: Value of the time step to be considered, defaults to 0.00333
        pitch_floor: Value for the minimum frequency to be captured, defaults to 100Hz
        pitch_ceiling: Value for the maximum frequency to be captured, defaults to 500Hz
        peak: If True, highlights detected peaks
        threshold_percentile: Percentile threshold for peak detection
        peak_distance: Minimum distance between peaks
    """
    snd = parselmouth.Sound(audio_path)
    pitch = snd.to_pitch(time_step, pitch_floor, pitch_ceiling)
    f0 = pitch.selected_array['frequency']
    time_pitch = pitch.xs()
    f0_plot = np.where(f0 == 0, np.nan, f0)

    if peak:
        voiced_f0 = f0[f0 > 0]
        threshold = np.percentile(voiced_f0, threshold_percentile)
        peaks, _ = find_peaks(f0, height=threshold, distance=peak_distance)
        plt.figure(figsize=(15, 8))
        plt.plot(time_pitch, f0_plot, label="Pitch (F0)")
        plt.scatter(time_pitch[peaks], f0[peaks], color="red", zorder=5,
                    label=f"Peaks (≥ p{threshold_percentile}, dist={peak_distance})")
        plt.xlabel("Time (s)")
        plt.ylabel("Frequency (Hz)")
        plt.title(f"Evolution of pitch throughout the audio: {audio_path.split('/')[-1]}")
        plt.legend()
        plt.savefig(os.path.join(output_path, "f0.png"))

    else:
        plt.figure(figsize=(15, 8))
        plt.plot(time_pitch, f0_plot)
        plt.xlabel("Time (s)")
        plt.ylabel("Frequency (Hz)")
        plt.title(f"Evolution of pitch throughout the audio: {audio_path.split('/')[-1]}")
        plt.savefig(os.path.join(output_path, "f0.png"))



def nearest_event(t, events):
    return events[np.argmin(np.abs(events - t))]


def f0_extract(audio_path, output, time_step=0.00333, pitch_floor=100.0, pitch_ceiling=500.0):
    """
    The code receives an audio input and makes a file with the f0 and time_pitch parameters

    Args:
        audio_path: The path for the audio file, eg "../data/meteoaudio.mp3"
        output: The name and path for the resulting file, eg "../outputs/audio_data.csv"
        time_step: Value of the time step to be considered, defaults to 0.00333
        pitch_floor: Value for the minimum frequency to be captured, defaults to 100Hz
        pitch_ceiling: Value for the maximum frequency to be captured, defaults to 500Hz

    Returns:
        Doesn't return anything, just creates the file
    """
    snd = parselmouth.Sound(audio_path)
    pitch = snd.to_pitch(time_step, pitch_floor, pitch_ceiling)
    f0 = pitch.selected_array['frequency']
    time_pitch = pitch.xs()
    np.savetxt(output, np.column_stack((f0, time_pitch)), delimiter=",", header="f0,time_pitch", comments='')


def histo(csv_path, landmarks, f0_path, fps, output_path, threshold_percentile=75, peak_distance=5):
    """
    The code takes a csv file with the acceleration and velocity of the landmarks tracked and the csv file with the information on the audio
    and plots the histograms relating the peak pitch with peak velocity and peak acceleration.

    Args:
        csv_path: The path for the csv file, including the csv (e.g. "../outputs/meteo4_movement_all.csv")
        landmarks: list with each landmark to be tracked
        f0_path: Path for the CSV file with the information on the audio, (e.g. "../outputs/audio_data.csv")
        fps: The fps of the original video
        output_path: directory where the plots will be saved
        threshold_percentile: The threshold for acceleration and velocity metrics
        peak_distance: Value establishing what the distance between peaks should be, defaults to 5
    """
    audio_data = pd.read_csv(f0_path)
    f0 = audio_data['f0']
    time_pitch = audio_data['time_pitch']
    movement_all = pd.read_csv(csv_path)
    dt = 1 / fps
    time = np.array([i * dt for i in range(len(movement_all))])
    pitch_threshold = np.percentile(f0[f0 > 0], threshold_percentile)
    peaks_pitch, _ = find_peaks(f0, height=pitch_threshold, distance=peak_distance)
    peak_pitch_times = time_pitch.values[peaks_pitch]

    for metric in ['acceleration', 'velocity']:
        if metric == 'acceleration':
            all_acceleration = []
            for lm_name in landmarks:
                acceleration_lm = movement_all[f'acceleration_{lm_name}']
                acceleration = np.array(acceleration_lm)
                acc_threshold = np.percentile(acceleration, threshold_percentile)
                peaks_acc, _ = find_peaks(acceleration, height=acc_threshold, distance=peak_distance)
                peak_acc_times = time[peaks_acc]
                D_acc = []
                for t_acc in peak_acc_times:
                    t_pitch = peak_pitch_times[np.argmin(np.abs(peak_pitch_times - t_acc))]
                    D_acc.append(t_acc - t_pitch)
                D_acc = np.array(D_acc) * 1000
                fig, ax = plt.subplots()
                sns.histplot(D_acc, bins=10)
                ax.axvline(0, linestyle='--', color='blue', label='peak pitch')
                ax.set_xlabel('D (ms)')
                ax.set_ylabel('Count')
                ax.set_title(f'Acceleration peak vs Pitch peak: {lm_name}')
                ax.legend()
                plt.tight_layout()
                plt.savefig(os.path.join(output_path, f"histogram_acceleration_{lm_name}.png"))

                all_acceleration.append(np.array(movement_all[f'acceleration_{lm_name}']))
            mean_acceleration = np.mean(all_acceleration, axis=0)
            acc_threshold = np.percentile(mean_acceleration, 75)
            peaks_acc, _ = find_peaks(mean_acceleration, height=acc_threshold, distance=peak_distance)
            peak_acc_times = time[peaks_acc]
            D_acc = []
            for t_acc in peak_acc_times:
                t_pitch = peak_pitch_times[np.argmin(np.abs(peak_pitch_times - t_acc))]
                D_acc.append(t_acc - t_pitch)
            D_acc = np.array(D_acc) * 1000
            fig, ax = plt.subplots(figsize=(15, 8))
            sns.histplot(D_acc, bins=10)
            ax.axvline(0, linestyle='--', color='blue', label='peak pitch')
            ax.set_xlabel('D (ms)')
            ax.set_ylabel('Count')
            ax.set_title('Acceleration peak vs Pitch peak: AVERAGE')
            ax.legend()
            plt.tight_layout()
            plt.savefig(os.path.join(output_path, "histogram_acceleration_average.png"))


        if metric == 'velocity':
            all_velocity = []
            for lm_name in landmarks:
                velocity_lm = movement_all[f'movement_{lm_name}']
                velocity = np.array(velocity_lm)
                vel_threshold = np.percentile(velocity, threshold_percentile)
                peaks_vel, _ = find_peaks(velocity, height=vel_threshold, distance=peak_distance)
                peak_vel_times = time[peaks_vel]
                D_vel = []
                for t_vel in peak_vel_times:
                    t_pitch = peak_pitch_times[np.argmin(np.abs(peak_pitch_times - t_vel))]
                    D_vel.append(t_vel - t_pitch)
                D_vel = np.array(D_vel) * 1000
                fig, ax = plt.subplots(figsize=(15, 8))
                sns.histplot(D_vel, bins=10)
                ax.axvline(0, linestyle='--', color='blue', label='peak pitch')
                ax.set_xlabel('D (ms)')
                ax.set_ylabel('Count')
                ax.set_title(f'Velocity peak vs Pitch peak: {lm_name}')
                ax.legend()
                plt.tight_layout()
                plt.savefig(os.path.join(output_path, f"histogram_velocity_{lm_name}.png"))

                all_velocity.append(np.array(movement_all[f'movement_{lm_name}']))
            mean_velocity = np.mean(all_velocity, axis=0)
            vel_threshold = np.percentile(mean_velocity, 75)
            peaks_vel, _ = find_peaks(mean_velocity, height=vel_threshold, distance=peak_distance)
            peak_vel_times = time[peaks_vel]
            D_vel = []
            for t_vel in peak_vel_times:
                t_pitch = peak_pitch_times[np.argmin(np.abs(peak_pitch_times - t_vel))]
                D_vel.append(t_vel - t_pitch)
            D_vel = np.array(D_vel) * 1000
            fig, ax = plt.subplots()
            sns.histplot(D_vel, bins=10)
            ax.axvline(0, linestyle='--', color='blue', label='peak pitch')
            ax.set_xlabel('D (ms)')
            ax.set_ylabel('Count')
            ax.set_title('Velocity peak vs Pitch peak: AVERAGE')
            ax.legend()
            plt.tight_layout()
            plt.savefig(os.path.join(output_path, "histogram_velocity_average.png"))



def plot_with_peaks(csv_path=None, landmarks=None, audio_path=None,
                    time_step=0.00333, pitch_floor=100.0, pitch_ceiling=500.0,
                    fps=None, threshold_percentile=75, peak_distance=5):
    """
    Plots the evolution of velocity, acceleration and/or pitch throughout the video/audio,
    highlighting the detected peaks as red dots.

    For gesture signals (velocity & acceleration), pass csv_path, landmarks, and fps.
    For pitch (F0), pass audio_path.
    Both can be combined in a single call.

    Args:
        csv_path:              Path to the movement CSV (e.g. "../outputs/meteo4_movement_all.csv").
                               Required for velocity/acceleration plots.
        landmarks:             List of landmark names to plot (e.g. tracks).
                               Required for velocity/acceleration plots.
        audio_path:            Path to the audio file (e.g. "../data/meteoaudio.mp3").
                               Required for the pitch plot.
        time_step:             Parselmouth time step for pitch extraction. Defaults to 0.00333.
        pitch_floor:           Minimum frequency for pitch extraction (Hz). Defaults to 100.0.
        pitch_ceiling:         Maximum frequency for pitch extraction (Hz). Defaults to 500.0.
        fps:                   Frames per second of the original video. Required when csv_path
                               is provided.
        threshold_percentile:  Percentile used to set the minimum peak height. Defaults to 75.
        peak_distance:         Minimum number of samples between consecutive peaks. Defaults to 5.

    Returns:
        Doesn't return anything, just plots the results.
    """
    if csv_path is not None and landmarks is not None:
        if fps is None:
            raise ValueError("fps is required when csv_path is provided")
        movement_all = pd.read_csv(csv_path)
        dt = 1 / fps
        time = np.array([i * dt for i in range(len(movement_all))])

        for lm in landmarks:
            for metric, col_name, ylabel in [
                ("velocity", f"movement_{lm}", f"Velocity of {lm}"),
                ("acceleration", f"acceleration_{lm}", f"Acceleration of {lm}"),
            ]:
                signal = np.array(movement_all[col_name])
                threshold = np.percentile(signal, threshold_percentile)
                peaks, _ = find_peaks(signal, height=threshold, distance=peak_distance)

                plt.figure(figsize=(15, 8))
                plt.plot(time, signal, label=metric.capitalize())
                plt.scatter(time[peaks], signal[peaks], color="red", zorder=5,
                            label=f"Peaks (≥ p{threshold_percentile}, dist={peak_distance})")
                plt.xlabel("Time (s)")
                plt.ylabel(ylabel)
                plt.title(f"Evolution of {metric} of {lm} throughout the video")
                plt.legend()


    if audio_path is not None:
        snd = parselmouth.Sound(audio_path)
        pitch = snd.to_pitch(time_step, pitch_floor, pitch_ceiling)
        f0 = pitch.selected_array['frequency']
        time_pitch = pitch.xs()
        f0_plot = np.where(f0 == 0, np.nan, f0)

        voiced_f0 = f0[f0 > 0]
        threshold = np.percentile(voiced_f0, threshold_percentile)
        peaks, _ = find_peaks(f0, height=threshold, distance=peak_distance)

        plt.figure(figsize=(15, 8))
        plt.plot(time_pitch, f0_plot, label="Pitch (F0)")
        plt.scatter(time_pitch[peaks], f0[peaks], color="red", zorder=5,
                    label=f"Peaks (≥ p{threshold_percentile}, dist={peak_distance})")
        plt.xlabel("Time (s)")
        plt.ylabel("Frequency (Hz)")
        plt.title(f"Evolution of pitch throughout the audio: {audio_path.split('/')[-1]}")
        plt.legend()


def smoothed_curves(csv_path, landmarks, f0_path, fps, output_path, threshold_percentile=75, peak_distance=5):
    """
    The code takes a csv file with the acceleration and velocity of the landmarks tracked and the csv file with the information on the audio
    and plots the histograms relating the peak pitch with peak velocity and peak acceleration.

    Args:
        csv_path: The path for the csv file, including the csv (e.g. "../outputs/meteo4_movement_all.csv")
        landmarks: list with each landmark to be tracked
        f0_path: Path for the CSV file with the information on the audio, (e.g. "../outputs/audio_data.csv")
        fps: The fps of the original video
        output_path: directory where the plots will be saved
        threshold_percentile: The threshold for acceleration and velocity metrics
        peak_distance: Value establishing what the distance between peaks should be, defaults to 5
    """
    audio_data = pd.read_csv(f0_path)
    f0 = audio_data['f0']
    time_pitch = audio_data['time_pitch']
    movement_all = pd.read_csv(csv_path)
    dt = 1 / fps
    time = np.array([i * dt for i in range(len(movement_all))])
    pitch_threshold = np.percentile(f0[f0 > 0], threshold_percentile)
    peaks_pitch, _ = find_peaks(f0, height=pitch_threshold, distance=peak_distance)
    for lm_name in landmarks:
        velocity_lm = movement_all[f'movement_{lm_name}']
        acceleration_lm = movement_all[f'acceleration_{lm_name}']
        time = np.array([i * dt for i in range(len(movement_all))])
        acceleration = np.array(acceleration_lm)
        velocity = np.array(velocity_lm)
        time = np.array(time)
        acc_threshold = np.percentile(acceleration,75)
        vel_threshold = np.percentile(velocity,75)
        peaks_acc, _ = find_peaks(acceleration, height=acc_threshold, distance=5)
        peak_acc_times = time[peaks_acc]
        peaks_vel, _ = find_peaks(velocity, height=vel_threshold, distance=5)
        peak_vel_times = time[peaks_vel]
        pitch_threshold = np.percentile(f0[f0 > 0], 75)
        peaks_pitch, _ = find_peaks(f0,height=pitch_threshold,distance=5)
        peak_pitch_times = time_pitch.values[peaks_pitch]

        D_acc = []
        D_vel = []
        for t_acc in peak_acc_times:
            t_pitch = nearest_event(t_acc, peak_pitch_times)
            D_acc.append(t_acc - t_pitch)
        D_acc = np.array(D_acc) * 1000
        for t_vel in peak_vel_times:
            t_pitch = nearest_event(t_vel, peak_pitch_times)
            D_vel.append(t_vel - t_pitch)
        D_vel = np.array(D_vel) * 1000
        fig, ax = plt.subplots(figsize=(8,4))
        sns.kdeplot(D_vel, ax=ax, color = 'orange', label=f"peak velocity ({lm_name})")
        sns.kdeplot(D_acc, ax=ax, color = 'green', label=f"peak acceleration ({lm_name})")
        ax.axvline(0, linestyle="--", color="blue", label="peak pitch")
        ax.set_xlabel("D (time in ms)")
        ax.set_ylabel("density")
        ax.set_title(f"Velocity & Acceleration vs Pitch: {lm_name}")
        ax.legend()
        plt.tight_layout()
        plt.savefig(os.path.join(output_path, f"smoothed_curves_{lm_name}.png"))



def smooth(x, window_len=11, window='hanning'):
    """
    Smooth a 1D signal using a window function.
    Adapted from https://scipy-cookbook.readthedocs.io/items/SignalSmooth.html
    """
    if x.ndim != 1:
        raise ValueError("smooth only accepts 1 dimension arrays")
    if x.size < window_len:
        raise ValueError("Input vector needs to be bigger than window size")
    if window_len < 3:
        return x
    if window not in ['flat', 'hanning', 'hamming', 'bartlett', 'blackman']:
        raise ValueError("Window must be one of 'flat', 'hanning', 'hamming', 'bartlett', 'blackman'")
    s = np.r_[x[window_len - 1:0:-1], x, x[-2:-window_len - 1:-1]]
    w = np.ones(window_len, 'd') if window == 'flat' else getattr(np, window)(window_len)
    y = np.convolve(w / w.sum(), s, mode='valid')
    trim = (len(y) - len(x)) // 2
    return y[trim:trim + len(x)]
