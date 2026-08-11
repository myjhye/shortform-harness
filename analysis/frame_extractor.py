"""
Stage 1: 프레임 추출기
영상의 특정 시간 구간을 지정된 간격(fps)으로 프레임 이미지로 추출한다.
ffmpeg-python을 사용하며, 기존 2-cartoon-youtube/src/utils.py의
ffmpeg 바이너리 호출 패턴을 참고한다.

TODO: extract_frames(video_path, start_sec, end_sec, interval_sec, out_dir) -> List[str]
"""
from typing import List


def extract_frames(
    video_path: str,
    start_sec: float,
    end_sec: float,
    interval_sec: float,
    out_dir: str,
) -> List[str]:
    pass
