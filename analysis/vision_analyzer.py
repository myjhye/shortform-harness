"""
Stage 3: Vision LLM 분석기
이미지 여러 장 + 분석 프롬프트를 Gemini Vision에 넘기고
response_mime_type="application/json"으로 구조화된 결과를 받는다.
기존 2-cartoon-youtube/src/app.py의 Gemini Client 사용 패턴을 참고한다.

TODO: analyze_hook(image_paths: List[str]) -> dict
TODO: analyze_subtitle_pattern(image_paths: List[str]) -> dict
"""
import json
import os
import time
from typing import Dict, List
from PIL import Image
from dotenv import load_dotenv

# dotenv 환경변수 로드 (.env)
load_dotenv()

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None


def _clean_json_text(text: str) -> str:
    """마크다운 코드 블록(```json ... ```) 제거 및 문자열 정리"""
    clean_text = text.strip()
    if clean_text.startswith("```json"):
        clean_text = clean_text[7:]
    elif clean_text.startswith("```"):
        clean_text = clean_text[3:]
    if clean_text.endswith("```"):
        clean_text = clean_text[:-3]
    return clean_text.strip()


def _call_gemini_vision_json(image_paths: List[str], prompt: str) -> Dict:
    """Gemini Vision API를 호출하여 이미지들 + 프롬프트 분석 결과를 구조화된 dict로 반환한다.

    복구 전략:
    1. 전체 프레임 배치 호출
    2. Safety Block 발생 시:
       - 1단계 (Fast Heuristic): 짝수 인덱스 서브셋 (`[::2]`) / 홀수 인덱스 서브셋 (`[1::2]`) 순차 시도
       - 2단계 (Deterministic Filtering): 차단된 프레임만 개별 선별/제외하고 정밀한 차단프레임 제로화 전송
    3. 네트워크/서버 에러 발생 시 exponential backoff (1초 -> 2초) 적용하여 최대 2회 재시도 (무한루프 금지)
    """
    if genai is None or types is None:
        raise ImportError(
            "google-genai 패키지가 설치되어 있지 않습니다. pip install google-genai 명령어를 실행하세요."
        )

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY가 .env 파일에 설정되어 있지 않습니다. .env 파일에 GEMINI_API_KEY를 등록해주세요."
        )

    if not image_paths:
        raise ValueError("image_paths 리스트가 비어 있습니다.")

    client = genai.Client(api_key=api_key)

    # 이미지 로드 및 유효성 검사
    pil_images = []
    for path in image_paths:
        if not os.path.exists(path):
            raise FileNotFoundError(f"Image file not found: {path}")
        pil_images.append(Image.open(path))

    contents = [*pil_images, prompt]
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
    )

    max_retries = 2
    delay = 1.0
    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=contents,
                config=config,
            )
            raw_text = response.text

            # Safety Block 발생 시 복구 절차
            if not raw_text and len(pil_images) > 1:
                # 1단계 (Fast Subsets): 짝수 -> 홀수 순차 시도
                for subset in (pil_images[::2], pil_images[1::2]):
                    sub_res = client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=[*subset, prompt],
                        config=config,
                    )
                    if sub_res.text:
                        raw_text = sub_res.text
                        break

                # 2단계 (Deterministic Exclude): 서브셋으로도 안 될 경우 차단된 단일 프레임 정밀 제거
                if not raw_text:
                    valid_images = []
                    for img in pil_images:
                        try:
                            chk = client.models.generate_content(
                                model="gemini-2.5-flash",
                                contents=[img, "Is safe?"],
                            )
                            if chk.candidates:
                                valid_images.append(img)
                        except Exception:
                            pass
                        time.sleep(0.5)  # Rate limit (429 Too Many Requests) 방지 딜레이

                    if valid_images:
                        det_res = client.models.generate_content(
                            model="gemini-2.5-flash",
                            contents=[*valid_images, prompt],
                            config=config,
                        )
                        raw_text = det_res.text

            if not raw_text:
                raise ValueError("Gemini API로부터 빈 응답이 반환되었습니다 (Safety Block persistent).")

            cleaned_text = _clean_json_text(raw_text)
            return json.loads(cleaned_text)
        except Exception as e:
            last_exception = e
            if attempt < max_retries:
                time.sleep(delay)
                delay *= 2
            else:
                raise RuntimeError(
                    f"Gemini Vision API 호출 실패 ({max_retries + 1}회 시도): {last_exception}"
                )


def analyze_hook(image_paths: List[str]) -> Dict:
    """영상 시작 0~3초 구간 프레임들(frame_extractor.extract_hook_frames로 뽑은 것)을

    Gemini Vision에 넣고 훅 정보를 분석한다.

    Returns:
        {
            "hook_text_appears_at_sec": float,  # 텍스트가 나타나는 대략적 시점(초)
            "hook_text_content_guess": str,      # 추정되는 문구 내용 (프레임에서 읽을 수 있으면)
            "hook_style": str,   # "curiosity_bait" / "shock_value" / "before_after_tease" / "problem_solution" 중 하나
            "camera_movement": str  # "static" / "zoom_in" / "zoom_out" / "handheld" / "pan" 중 하나
        }
    """
    prompt = """
제공된 이미지들은 숏폼 영상 시작 0초부터 3초 구간의 순차적 프레임들입니다.
프레임 순서상 시간 위치를 참조하여 아래 요구사항에 맞게 오직 지정된 JSON 형식으로만 결과를 답하십시오.

요구사항:
1. hook_text_appears_at_sec: 화면에 훅/제목/강조 텍스트가 나타나는 대략적인 시점 (초 단위 float). 텍스트가 안 보이면 0.0.
2. hook_text_content_guess: 프레임에서 읽을 수 있는 훅 문구/텍스트 내용 추정 (없으면 "").
3. hook_style: 시각적/내용적 훅 연출 스타일. "curiosity_bait", "shock_value", "before_after_tease", "problem_solution" 중 가장 부합하는 1개 선택.
4. camera_movement: 카메라 움직임/구도 변화. "static", "zoom_in", "zoom_out", "handheld", "pan" 중 가장 부합하는 1개 선택.

JSON 출력 형태 (반드시 이 키 구조 유지):
{
  "hook_text_appears_at_sec": 0.0,
  "hook_text_content_guess": "문구 내용",
  "hook_style": "curiosity_bait",
  "camera_movement": "static"
}
"""
    return _call_gemini_vision_json(image_paths, prompt)


def analyze_subtitle_pattern(image_paths: List[str]) -> Dict:
    """영상 전체를 균등 샘플링한 프레임들(extract_sampled_frames로 뽑은 것)을

    Gemini Vision에 넣고 자막 등장 패턴을 분석한다.

    Returns:
        {
            "has_subtitles": bool,
            "subtitle_style": str,   # "large_bold_center" / "bottom_caption" / "word_by_word" 등 관찰한 대로
            "avg_subtitle_duration_guess_sec": float,  # 자막 하나가 대략 몇 초 유지되는지 추정
            "subtitle_tone": str    # "casual_banmal" / "formal" / "energetic" 등
        }
    """
    prompt = """
제공된 이미지들은 숏폼 영상 전체 구간에서 균등한 간격으로 샘플링한 프레임들입니다.
화면의 자막 패턴을 관찰하고 아래 요구사항에 맞게 오직 지정된 JSON 형식으로만 결과를 답하십시오.

요구사항:
1. has_subtitles: 화면에 나레이션이나 대사를 설명하는 자막/캡션 텍스트가 존재하는지 여부 (boolean: true 또는 false).
2. subtitle_style: 관찰된 자막 배치 및 스타일 (예: "large_bold_center", "bottom_caption", "word_by_word", "shadow_highlight" 등 관찰한 대로 기재).
3. avg_subtitle_duration_guess_sec: 자막 하나가 화면에 유지되는 대략적인 시간 추정 (초 단위 float, 자막이 없으면 0.0).
4. subtitle_tone: 자막 문체의 어조/톤 (예: "casual_banmal", "formal", "energetic", "humorous" 등).

JSON 출력 형태 (반드시 이 키 구조 유지):
{
  "has_subtitles": true,
  "subtitle_style": "large_bold_center",
  "avg_subtitle_duration_guess_sec": 1.5,
  "subtitle_tone": "casual_banmal"
}
"""
    return _call_gemini_vision_json(image_paths, prompt)


if __name__ == "__main__":
    import sys

    # Windows 콘솔 유니코드/이모지 출력 인코딩 설정
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    # 스크립트 직접 실행 시 프로젝트 루트를 sys.path에 추가
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

    from analysis.frame_extractor import extract_hook_frames, extract_sampled_frames

    def run_analysis_for_video(video_path: str, out_base_dir: str) -> Dict:
        print(f"\n[+] '{video_path}' 분석 시작...")
        hook_dir = os.path.join(out_base_dir, "hook")
        sampled_dir = os.path.join(out_base_dir, "sampled")

        hook_frames = extract_hook_frames(video_path, hook_dir)
        print(f"  - 추출된 훅 프레임: {len(hook_frames)}개")
        hook_res = analyze_hook(hook_frames)

        sampled_frames = extract_sampled_frames(video_path, sampled_dir)
        print(f"  - 추출된 샘플 프레임: {len(sampled_frames)}개")
        sub_res = analyze_subtitle_pattern(sampled_frames)

        return {"hook": hook_res, "subtitle": sub_res}

    ref1_video = "references/ref1.mp4"
    ref2_video = "references/ref2.mp4"

    results = {}
    if os.path.exists(ref1_video):
        results["ref1"] = run_analysis_for_video(ref1_video, "outputs/vision_test/ref1")
    if os.path.exists(ref2_video):
        results["ref2"] = run_analysis_for_video(ref2_video, "outputs/vision_test_ref2")

    print("\n" + "=" * 60)
    print("[+] 레퍼런스 영상 Vision 분석 결과 비교")
    print("=" * 60)
    print(json.dumps(results, ensure_ascii=False, indent=2))
