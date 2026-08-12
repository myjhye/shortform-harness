"""
Stage 6-LLM: Gemini 텍스트 LLM 호출기
Gemini API (gemini-2.5-flash)를 사용해 프롬프트 텍스트를 보내고 응답 텍스트를 받는다.
response_as_json=True 지정 시 response_mime_type="application/json"으로 구조화된 결과를 수신한다.
"""
import os
import time
from typing import Optional
from dotenv import load_dotenv

# dotenv 환경변수 로드
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


def call_gemini_text(
    prompt: str,
    response_as_json: bool = False,
    api_key: Optional[str] = None,
    max_retries: int = 3,
) -> str:
    """Gemini API로 텍스트 프롬프트를 보내고 응답 텍스트를 반환한다.

    Args:
        prompt: LLM에 전달할 텍스트 프롬프트
        response_as_json: True일 경우 JSON 구조화 응답 요청
        api_key: Gemini API 키 (None일 경우 .env의 GEMINI_API_KEY 사용)
        max_retries: API 실패 시 최대 재시도 횟수

    Returns:
        LLM 응답 텍스트 (JSON 요청 시 정리된 JSON 텍스트)
    """
    if genai is None or types is None:
        raise ImportError(
            "google-genai 패키지가 설치되어 있지 않습니다. pip install google-genai 명령어를 실행하세요."
        )

    resolved_api_key = api_key or os.environ.get("GEMINI_API_KEY")
    if not resolved_api_key:
        raise ValueError(
            "GEMINI_API_KEY가 .env 파일에 설정되어 있지 않습니다. .env 파일에 GEMINI_API_KEY를 등록해주세요."
        )

    prompt = (prompt or "").strip()
    if not prompt:
        raise ValueError("Gemini LLM 호출을 위한 프롬프트가 비어 있습니다.")

    client = genai.Client(api_key=resolved_api_key)

    config_kwargs = {}
    if response_as_json:
        config_kwargs["response_mime_type"] = "application/json"

    config = (
        types.GenerateContentConfig(**config_kwargs) if config_kwargs else None
    )

    delay = 1.0
    last_exception = None

    for attempt in range(1, max_retries + 1):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=config,
            )
            raw_text = response.text
            if not raw_text:
                raise ValueError("Gemini API로부터 빈 응답 텍스트가 반환되었습니다.")

            if response_as_json:
                return _clean_json_text(raw_text)
            return raw_text.strip()
        except Exception as exc:
            last_exception = exc
            if attempt < max_retries:
                print(
                    f"[LLM] Gemini API 호출 시도 {attempt}/{max_retries} 실패 ({exc}). {delay:.1f}초 후 재시도..."
                )
                time.sleep(delay)
                delay *= 2

    raise RuntimeError(
        f"Gemini LLM 텍스트 생성 최종 실패 ({max_retries}회 시도): {last_exception}"
    )


if __name__ == "__main__":
    test_prompt = "숏폼 영감 멘트 1줄을 한국어 반말체로 작성해줘."
    print(f"[+] LLM 테스트 요청: '{test_prompt}'")
    res = call_gemini_text(test_prompt)
    print(f"[+] LLM 응답: {res}")
