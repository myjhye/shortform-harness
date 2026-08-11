"""
Stage 1: 프레임 추출기
영상의 특정 시간 구간을 지정된 간격(fps)으로 프레임 이미지로 추출한다.
ffmpeg-python 및 subprocess를 사용하며, ffmpeg 바이너리를 호출하여 지정된 파라미터로
프레임 이미지를 추출하고 정렬된 경로 리스트를 반환한다.
"""
import glob
import os
import subprocess
import sys
from typing import List

# Windows 환경에서 콘솔 창이 뜨지 않도록 처리
NO_WINDOW_FLAG = (
    subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
)


def get_video_duration(video_path: str) -> float:
    """ffprobe를 사용해 영상의 총 길이를 초(second) 단위 float로 구한다."""
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")

    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        video_path,
    ]

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
            creationflags=NO_WINDOW_FLAG,
        )
        return float(result.stdout.strip())
    except FileNotFoundError:
        raise FileNotFoundError(
            "ffmpeg/ffprobe가 설치되어 있는지, PATH에 등록되어 있는지 확인하세요."
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffprobe execution failed:\n{e.stderr}")
    except ValueError as e:
        raise RuntimeError(f"Failed to parse video duration: {e}")


def extract_frames(
    video_path: str,
    start_sec: float,
    end_sec: float,
    interval_sec: float,
    out_dir: str,
    prefix: str = "frame",
) -> List[str]:
    """영상의 [start_sec, end_sec] 구간을 interval_sec 간격으로 프레임 추출.

    Returns:
        추출된 이미지 파일 경로 리스트 (시간 순 정렬)
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")

    if interval_sec <= 0:
        raise ValueError("interval_sec must be greater than 0")

    if end_sec <= start_sec:
        raise ValueError("end_sec must be greater than start_sec")

    os.makedirs(out_dir, exist_ok=True)

    duration = end_sec - start_sec
    output_pattern = os.path.join(out_dir, f"{prefix}_%03d.png")

    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{start_sec:.3f}",
        "-t",
        f"{duration:.3f}",
        "-i",
        video_path,
        "-vf",
        f"fps=1/{interval_sec}",
        output_pattern,
    ]

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=NO_WINDOW_FLAG,
        )
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg execution failed:\n{result.stderr}")
    except FileNotFoundError:
        raise FileNotFoundError(
            "ffmpeg가 설치되어 있는지, PATH에 등록되어 있는지 확인하세요."
        )

    # 추출된 파일 찾기 및 시간 순 정렬
    extracted_pattern = os.path.join(out_dir, f"{prefix}_*.png")
    extracted_files = glob.glob(extracted_pattern)
    extracted_files.sort(key=lambda p: os.path.basename(p))

    return [os.path.abspath(f) for f in extracted_files]


def extract_hook_frames(
    video_path: str, out_dir: str, hook_duration_sec: float = 3.0
) -> List[str]:
    """영상 시작 0초~hook_duration_sec 구간을 0.33초 간격으로 추출 (훅 분석용)"""
    return extract_frames(
        video_path=video_path,
        start_sec=0.0,
        end_sec=hook_duration_sec,
        interval_sec=0.33,
        out_dir=out_dir,
        prefix="hook",
    )


def extract_sampled_frames(
    video_path: str, out_dir: str, interval_sec: float = 0.5
) -> List[str]:
    """영상 전체를 interval_sec 간격으로 균등 추출 (자막 패턴 분석용)"""
    duration = get_video_duration(video_path)
    return extract_frames(
        video_path=video_path,
        start_sec=0.0,
        end_sec=duration,
        interval_sec=interval_sec,
        out_dir=out_dir,
        prefix="sample",
    )


if __name__ == "__main__":
    test_video = "references/ref1.mp4"
    output_dir = "outputs/test_frames"
    if os.path.exists(test_video):
        print(f"[+] '{test_video}' 영상 프레임 추출 테스트 시작...")
        frames = extract_hook_frames(test_video, output_dir)
        print(f"추출된 프레임: {len(frames)}개")
        for f in frames:
            print(f"  - {f}")
    else:
        print(f"테스트용 레퍼런스 영상이 존재하지 않습니다: {test_video}")
