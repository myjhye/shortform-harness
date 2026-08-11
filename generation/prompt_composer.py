"""
Stage 6: 프롬프트 조립기
style_spec.json + 사용자 입력을 결합해 훅/자막 생성용 LLM 프롬프트를
동적으로 만든다. 기존 app.py의 enforce_prompt_by_mode 패턴을 참고하되,
하드코딩된 모드 대신 style_spec 딕셔너리 기반으로 동작하도록 한다.
"""
import random
from typing import Dict, List, Optional


def compose_hook_prompt(
    style_spec: Dict,
    user_input: str,
    target_language: str = "ko",
    formality: str = "casual",
    seed: Optional[int] = None,
) -> str:
    """style_spec의 hook/subtitle 필드와 사용자 입력을 결합해서,

    LLM에게 훅 문구 생성을 요청하는 프롬프트를 만든다.

    Args:
        style_spec: 스타일 분석 스펙 딕셔너리
        user_input: 사용자 입력 주제
        target_language: 출력 언어 (기본값 "ko", 호출자 지정)
        formality: 어조 문체 ("casual"=반말체, "formal"=존댓말, 한국 숏폼 관례 기본값 "casual")
        seed: 시드값 (테스트 재현성용)

    Returns: 완성된 프롬프트 문자열
    """
    rng = random.Random(seed) if seed is not None else random

    hook_spec = style_spec.get("hook", {}) if isinstance(style_spec, dict) else {}
    sub_spec = style_spec.get("subtitle", {}) if isinstance(style_spec, dict) else {}

    style_pool = hook_spec.get("style_pool", [])
    tone_pool = sub_spec.get("tone_pool", [])
    avg_delay_sec = hook_spec.get("avg_delay_sec", 0.0)

    selected_style = rng.choice(style_pool) if style_pool else "problem_solution"
    selected_tone = rng.choice(tone_pool) if tone_pool else "casual_friendly"

    formality_desc = (
        "반말체(친근하고 자극적인 톤)"
        if formality == "casual"
        else "존댓말/경어체(정중하고 격식 있는 톤)"
    )

    prompt = f"""[숏폼 영상 훅(Hook) 문구 생성 프롬프트]

주제(사용자 입력): {user_input}
타겟 연출 스타일(레퍼런스 분석): {selected_style}
참고 톤(레퍼런스 분석): {selected_tone}
출력 언어(호출자 지정): {target_language}
문체/존비속어 구분(타겟 시장 관례): {formality} ({formality_desc})
텍스트 등장 권장 타임라인: 영상 시작 {avg_delay_sec:.1f}초 시점

[작성 지침]
1. 시청자의 시선을 3초 안에 사로잡을 수 있는 강렬하고 임팩트 있는 훅 문구를 생성해라.
2. 어조 및 문체: 레퍼런스에서 추출된 '{selected_tone}' 톤의 성격(활기참/친근함 등)을 반영하여, 지정된 출력 언어({target_language})와 문체({formality_desc})에 맞게 자연스럽게 재현해라.
3. 다양성: 이전과 동일하지 않은 매번 새롭고 독창적인 문구를 생성해라.
4. 출력 형식: 다른 설명 없이 오직 생성된 훅 문구만 출력해라.
"""
    return prompt.strip()


def compose_subtitle_prompt(
    style_spec: Dict,
    user_input: str,
    num_segments: int = 4,
    target_language: str = "ko",
    formality: str = "casual",
    seed: Optional[int] = None,
) -> str:
    """style_spec의 subtitle 필드와 사용자 입력을 결합해서, LLM에게

    자막 스크립트(여러 세그먼트) 생성을 요청하는 프롬프트를 만든다.

    Args:
        style_spec: 스타일 분석 스펙 딕셔너리
        user_input: 사용자 입력 주제
        num_segments: 목표 세그먼트 수
        target_language: 출력 언어 (기본값 "ko")
        formality: 어조 문체 ("casual"=반말체, "formal"=존댓말, 기본값 "casual")
        seed: 시드값

    Returns: 완성된 프롬프트 문자열
    """
    rng = random.Random(seed) if seed is not None else random

    sub_spec = style_spec.get("subtitle", {}) if isinstance(style_spec, dict) else {}
    duration_range = sub_spec.get("duration_range_sec", [1.5, 4.0])
    style_pool = sub_spec.get("style_pool", [])
    tone_pool = sub_spec.get("tone_pool", [])

    min_dur, max_dur = duration_range if len(duration_range) == 2 else (1.5, 4.0)

    selected_tone = rng.choice(tone_pool) if tone_pool else "casual_friendly"
    selected_style = rng.choice(style_pool) if style_pool else "large_bold_center"

    formality_desc = (
        "반말체(친근한 톤)" if formality == "casual" else "존댓말/경어체(격식 있는 톤)"
    )

    prompt = f"""[숏폼 자막 스크립트 생성 프롬프트]

주제(사용자 입력): {user_input}
목표 세그먼트 개수: {num_segments}개
권장 자막 유지 시간: 세그먼트당 {min_dur:.1f}초 ~ {max_dur:.1f}초 범위
참고 톤(레퍼런스 분석): {selected_tone}
참고 연출 스타일(레퍼런스 분석): {selected_style}
출력 언어(호출자 지정): {target_language}
문체/존비속어 구분(타겟 시장 관례): {formality} ({formality_desc})

[작성 지침]
1. 주제에 부합하는 나레이션/자막 대본을 정확히 {num_segments}개의 세그먼트로 나누어 작성해라.
2. 각 세그먼트 자막 길이는 화면 읽기 편하도록 짧게 유지하고, duration_sec은 {min_dur:.1f}초 ~ {max_dur:.1f}초 사이로 할당해라.
3. 레퍼런스의 '{selected_tone}' 톤의 느낌을 지정된 언어({target_language})와 문체({formality_desc})로 자연스럽게 살려 작성해라.
4. 반드시 아래 JSON 배열 형식으로만 응답해라 (마크다운 설명 제외):

[
  {{"text": "자막 내용 1", "duration_sec": 2.5}},
  {{"text": "자막 내용 2", "duration_sec": 3.0}}
]
"""
    return prompt.strip()


def compose_cut_plan(
    style_spec: Dict, total_duration_sec: float, seed: Optional[int] = None
) -> Dict:
    """style_spec의 cut_rhythm을 참고해서, 전체 영상 길이에 맞는 컷

    개수와 각 컷의 대략적인 길이를 계산한다. (LLM 호출 없이 순수 계산)

    전체 컷 중 약 20% 확률로 cut_range_sec의 극단값(짧은 컷 / 긴 컷)을 섞어
    레퍼런스 영상의 리듬감 및 컷 다양성을 충실히 반영한다.

    Returns:
        {
            "num_cuts": int,
            "cut_durations_sec": [float, float, ...]  # 합이 total_duration_sec에 근접
        }
    """
    if total_duration_sec <= 0:
        raise ValueError("total_duration_sec must be greater than 0")

    rng = random.Random(seed) if seed is not None else random

    cut_spec = style_spec.get("cut_rhythm", {}) if isinstance(style_spec, dict) else {}
    avg_cut_sec = float(cut_spec.get("avg_cut_sec", 1.5))
    cut_range = cut_spec.get("cut_range_sec", [0.5, 3.0])
    min_cut, max_cut = cut_range if len(cut_range) == 2 else (0.5, 3.0)

    if avg_cut_sec <= 0:
        avg_cut_sec = 1.5

    # 컷 개수 산출
    num_cuts = max(1, int(round(total_duration_sec / avg_cut_sec)))

    raw_durations = []
    for _ in range(num_cuts):
        rand_val = rng.random()
        if rand_val < 0.10:
            # 극단적 짧은 컷 (min_cut 근처 빠른 호흡 컷)
            dur = rng.uniform(min_cut, min(min_cut + 0.3, avg_cut_sec))
        elif rand_val < 0.20:
            # 극단적 긴 컷 (max_cut 근처 잔잔한 컷)
            dur = rng.uniform(max(avg_cut_sec, max_cut * 0.65), max_cut)
        else:
            # 일반 컷 (avg_cut_sec 주변 ±25% 편차)
            variation = rng.uniform(-0.25, 0.25)
            dur = avg_cut_sec * (1.0 + variation)

        dur = max(min_cut, min(max_cut, dur))
        raw_durations.append(dur)

    # 전체 합이 total_duration_sec와 정확히 일치하도록 비율 정규화
    current_sum = sum(raw_durations)
    scale_factor = total_duration_sec / current_sum if current_sum > 0 else 1.0

    normalized_durations = [
        round(max(min_cut, min(max_cut, dur * scale_factor)), 2) for dur in raw_durations
    ]

    # 반올림 오차 보정
    diff = round(total_duration_sec - sum(normalized_durations), 2)
    if abs(diff) > 0.001 and normalized_durations:
        normalized_durations[-1] = round(max(min_cut, min(max_cut, normalized_durations[-1] + diff)), 2)

    return {
        "num_cuts": len(normalized_durations),
        "cut_durations_sec": normalized_durations,
    }


if __name__ == "__main__":
    import json
    import os

    spec_path = "outputs/style_specs/style_spec.json"
    if os.path.exists(spec_path):
        with open(spec_path, encoding="utf-8") as f:
            spec = json.load(f)
    else:
        spec = {
            "cut_rhythm": {"avg_cut_sec": 1.35, "cut_range_sec": [0.53, 4.0]},
            "hook": {"avg_delay_sec": 0.0, "style_pool": ["problem_solution"]},
            "subtitle": {
                "duration_range_sec": [3.0, 8.0],
                "style_pool": ["large_bold_center"],
                "tone_pool": ["enthusiastic_promotional", "casual_friendly"],
            },
        }

    user_input = "콜라겐 앰플로 탄력 관리하는 20대 직장인 스킨케어 루틴"

    print("[+] 수정된 훅 프롬프트 (기본 ko, casual):")
    print(compose_hook_prompt(spec, user_input))
    print()

    print("[+] 훅 프롬프트 (Option: ko, formal):")
    print(compose_hook_prompt(spec, user_input, formality="formal"))
    print()

    print("[+] 자막 프롬프트 (기본 ko, casual):")
    print(compose_subtitle_prompt(spec, user_input))
    print()

    print("[+] 컷 플랜 (25초 기준):")
    cut_plan = compose_cut_plan(spec, 25.0)
    print(json.dumps(cut_plan, ensure_ascii=False, indent=2))
