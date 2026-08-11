"""
Stage 5: 스타일 스펙 통합기
frame_extractor, cut_detector, vision_analyzer, audio_analyzer의 결과를
하나의 style_spec.json으로 통합하고 outputs/style_specs/에 저장한다.
여러 레퍼런스 영상 결과가 있을 경우 평균/병합 전략을 적용한다.

TODO: build_style_spec(video_paths: List[str]) -> dict
TODO: save_style_spec(spec: dict, out_path: str) -> None
"""
from typing import List


def build_style_spec(video_paths: List[str]) -> dict:
    pass


def save_style_spec(spec: dict, out_path: str) -> None:
    pass
