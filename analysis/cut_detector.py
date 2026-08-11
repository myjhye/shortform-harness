"""
Stage 2: 컷(장면 전환) 감지기
PySceneDetect(ContentDetector)를 사용해 영상의 컷 전환 타임스탬프를
검출하고, 컷 길이 리스트/평균/분산을 계산한다.
"""
import os
import subprocess
import sys
from typing import Dict, List

# PySceneDetect 모듈 임포트 검사
try:
    from scenedetect import ContentDetector, detect  # type: ignore
except ImportError:
    detect = None
    ContentDetector = None

NO_WINDOW_FLAG = (
    subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
)


def get_video_duration(video_path: str) -> float:
    """ffprobe로 영상 전체 길이(초)를 조회한다."""
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
            "ffprobe가 설치되어 있는지, PATH에 등록되어 있는지 확인하세요."
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffprobe execution failed:\n{e.stderr}")
    except ValueError as e:
        raise RuntimeError(f"Failed to parse video duration: {e}")


def detect_cuts(video_path: str, threshold: float = 27.0) -> Dict:
    """영상의 컷 전환 시점을 감지하고 컷 길이 통계를 반환한다.

    Args:
        video_path: 분석할 영상 경로
        threshold: ContentDetector의 민감도 (기본값 27.0, scenedetect 기본값)

    Returns:
        {
            "cut_count": int,              # 감지된 컷 개수
            "avg_cut_sec": float,          # 평균 컷 길이 (초, 소수점 2자리)
            "min_cut_sec": float,          # 최소 컷 길이 (초, 소수점 2자리)
            "max_cut_sec": float,          # 최대 컷 길이 (초, 소수점 2자리)
            "cut_timestamps": list[float], # 각 컷의 시작 시각 (초)
            "raw_durations": list[float]   # 각 컷의 길이 리스트 (초)
        }
    """
    if detect is None or ContentDetector is None:
        raise ImportError(
            "PySceneDetect가 설치되어 있지 않습니다. pip install scenedetect[opencv]를 실행하세요."
        )

    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")

    if threshold <= 0:
        raise ValueError("threshold must be greater than 0")

    # scenedetect 감지 실행
    scene_list = detect(video_path, ContentDetector(threshold=threshold))

    # 컷이 감지되지 않은 경우 (전체가 하나의 씬인 경우)
    if not scene_list:
        duration = get_video_duration(video_path)
        duration_rounded = round(duration, 2)
        return {
            "cut_count": 1,
            "avg_cut_sec": duration_rounded,
            "min_cut_sec": duration_rounded,
            "max_cut_sec": duration_rounded,
            "cut_timestamps": [0.0],
            "raw_durations": [duration_rounded],
        }

    cut_timestamps: List[float] = []
    raw_durations: List[float] = []

    for start_time, end_time in scene_list:
        start_sec = round(start_time.seconds, 2)
        end_sec = round(end_time.seconds, 2)
        duration_sec = round(end_sec - start_sec, 2)

        cut_timestamps.append(start_sec)
        raw_durations.append(duration_sec)

    cut_count = len(scene_list)
    avg_cut_sec = round(sum(raw_durations) / cut_count, 2)
    min_cut_sec = round(min(raw_durations), 2)
    max_cut_sec = round(max(raw_durations), 2)

    return {
        "cut_count": cut_count,
        "avg_cut_sec": avg_cut_sec,
        "min_cut_sec": min_cut_sec,
        "max_cut_sec": max_cut_sec,
        "cut_timestamps": cut_timestamps,
        "raw_durations": raw_durations,
    }


def compare_cut_rhythm(spec_a: Dict, spec_b: Dict) -> Dict:
    """두 개의 detect_cuts() 결과를 비교해서 유사도를 계산한다.

    (여러 레퍼런스 영상 간 스타일이 비슷한지 판단하는 용도)

    Returns:
        {
            "avg_cut_diff_sec": float,  # 평균 컷 길이 차이
            "similar": bool             # 차이가 0.3초 이내면 True
        }
    """
    diff = round(
        abs(spec_a.get("avg_cut_sec", 0.0) - spec_b.get("avg_cut_sec", 0.0)), 2
    )
    return {"avg_cut_diff_sec": diff, "similar": diff <= 0.3}


if __name__ == "__main__":
    ref1_path = "references/ref1.mp4"
    ref2_path = "references/ref2.mp4"

    if os.path.exists(ref1_path):
        result1 = detect_cuts(ref1_path)
        print(f"[+] '{ref1_path}' 컷 분석 결과:")
        print(f"  - 컷 개수: {result1['cut_count']}")
        print(f"  - 평균 컷 길이: {result1['avg_cut_sec']}초")
        print(f"  - 최소/최대: {result1['min_cut_sec']}초 / {result1['max_cut_sec']}초")
        print(f"  - 타임스탬프: {result1['cut_timestamps']}")

        if os.path.exists(ref2_path):
            result2 = detect_cuts(ref2_path)
            print(f"\n[+] '{ref2_path}' 컷 분석 결과:")
            print(f"  - 컷 개수: {result2['cut_count']}")
            print(f"  - 평균 컷 길이: {result2['avg_cut_sec']}초")
            print(f"  - 최소/최대: {result2['min_cut_sec']}초 / {result2['max_cut_sec']}초")
            print(f"  - 타임스탬프: {result2['cut_timestamps']}")

            comp = compare_cut_rhythm(result1, result2)
            print(f"\n[+] 레퍼런스 영상 간 컷 리듬 비교:")
            print(f"  - 평균 컷 길이 차이: {comp['avg_cut_diff_sec']}초")
            print(f"  - 유사성 판단 (0.3초 이내): {comp['similar']}")
    else:
        print(f"테스트용 레퍼런스 영상이 존재하지 않습니다: {ref1_path}")
