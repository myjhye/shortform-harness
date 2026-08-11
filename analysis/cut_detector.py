"""
Stage 2: 컷(장면 전환) 감지기
PySceneDetect(ContentDetector)를 사용해 영상의 컷 전환 타임스탬프를
검출하고, 컷 길이 리스트/평균/분산을 계산한다.

TODO: detect_cuts(video_path, threshold=27.0) -> dict
  반환 예시: {"cut_count": int, "avg_cut_sec": float, "raw_durations": List[float]}
"""


def detect_cuts(video_path: str, threshold: float = 27.0) -> dict:
    pass
