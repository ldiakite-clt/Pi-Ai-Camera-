"""
This file handles turning a bunch of JPEG frames into an MP4 video file.
We use ffmpeg for the heavy lifting because it's fast and reliable.
"""
import subprocess
import tempfile
import os
from pathlib import Path
from typing import List, Tuple

# Take a list of (timestamp, jpeg_bytes) frames and make an MP4 video
def frames_to_mp4(frames: List[Tuple[int, bytes]], output_path: Path, fps: int = 5) -> dict:
    """
    Converts a list of JPEG frames into an MP4 using ffmpeg.
    Args:
        frames: List of (timestamp, jpeg_bytes) tuples
        output_path: Where to save the MP4
        fps: Frames per second for the video
    Returns:
        Dictionary with duration, frame_count, and file_size
    """
    if not frames:
        raise ValueError("No frames provided")

    # We'll use a temp folder to store the JPEGs before encoding
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Write each frame as a numbered JPEG file
        for i, (ts, jpeg_bytes) in enumerate(frames):
            frame_path = tmpdir_path / f"frame_{i:05d}.jpg"
            with open(frame_path, 'wb') as f:
                f.write(jpeg_bytes)

        # Build the ffmpeg command to make the MP4
        cmd = [
            'ffmpeg',
            '-framerate', str(fps),
            '-i', str(tmpdir_path / 'frame_%05d.jpg'),
            '-c:v', 'libx264',
            '-preset', 'fast',
            '-crf', '23',
            '-pix_fmt', 'yuv420p',
            '-movflags', '+faststart',  # helps with streaming
            '-y',
            str(output_path)
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                check=True
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"ffmpeg failed: {e.stderr}")
        except subprocess.TimeoutExpired:
            raise RuntimeError("ffmpeg encoding timeout")

    # Get info about the finished video
    file_size = output_path.stat().st_size
    frame_count = len(frames)
    duration = int(frame_count / fps)

    return {
        'duration': duration,
        'frame_count': frame_count,
        'file_size': file_size
    }
    frame_count = len(frames)
