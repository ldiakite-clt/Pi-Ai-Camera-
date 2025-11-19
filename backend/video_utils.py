"""
Video encoding utilities for converting frame sequences to MP4.
"""
import subprocess
import tempfile
import os
from pathlib import Path
from typing import List, Tuple


def frames_to_mp4(frames: List[Tuple[int, bytes]], output_path: Path, fps: int = 5) -> dict:
    """
    Convert a list of JPEG frames to an MP4 video using ffmpeg.
    
    Args:
        frames: List of (timestamp, jpeg_bytes) tuples
        output_path: Path where the MP4 file should be saved
        fps: Frames per second for the output video
    
    Returns:
        dict with metadata: duration, frame_count, file_size
    """
    if not frames:
        raise ValueError("No frames provided")
    
    # Create temporary directory for frame files
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        
        # Write frames as numbered JPEG files
        for i, (ts, jpeg_bytes) in enumerate(frames):
            frame_path = tmpdir_path / f"frame_{i:05d}.jpg"
            with open(frame_path, 'wb') as f:
                f.write(jpeg_bytes)
        
        # Use ffmpeg to create MP4
        # -framerate: input framerate
        # -i: input pattern
        # -c:v libx264: use H.264 codec
        # -preset fast: encoding speed/quality tradeoff
        # -crf 23: quality (lower = better, 18-28 is good range)
        # -pix_fmt yuv420p: pixel format for compatibility
        # -y: overwrite output file
        cmd = [
            'ffmpeg',
            '-framerate', str(fps),
            '-i', str(tmpdir_path / 'frame_%05d.jpg'),
            '-c:v', 'libx264',
            '-preset', 'fast',
            '-crf', '23',
            '-pix_fmt', 'yuv420p',
            '-movflags', '+faststart',  # optimize for streaming
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
    
    # Get output file size
    file_size = output_path.stat().st_size
    frame_count = len(frames)
    duration = int(frame_count / fps)
    
    return {
        'duration': duration,
        'frame_count': frame_count,
        'file_size': file_size
    }
