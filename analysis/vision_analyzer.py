"""
Stage 3: Vision LLM 분석기
이미지 여러 장 + 분석 프롬프트를 Gemini Vision에 넘기고
response_mime_type="application/json"으로 구조화된 결과를 받는다.
기존 2-cartoon-youtube/src/app.py의 Gemini Client 사용 패턴을 참고한다.

TODO: analyze_hook(image_paths: List[str]) -> dict
TODO: analyze_subtitle_pattern(image_paths: List[str]) -> dict
"""
from typing import List


def analyze_hook(image_paths: List[str]) -> dict:
    pass


def analyze_subtitle_pattern(image_paths: List[str]) -> dict:
    pass
