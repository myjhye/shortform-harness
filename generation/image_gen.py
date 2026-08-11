"""
Stage 8: Replicate 이미지를 생성하는 생성기 (Flux Schnell 모델)
Replicate API를 사용해서 프롬프트 텍스트로부터 이미지를 생성한다.
실패 시 예외를 던지지 않고 검은색 fallback 이미지를 자동 생성하여 반환한다.
"""
import os
import time
from typing import Dict, Optional
from PIL import Image
import requests
from dotenv import load_dotenv

try:
    import replicate
except ImportError:
    replicate = None

# .env 환경변수 로드
load_dotenv()

REPLICATE_MAX_RETRIES = 3
REPLICATE_RETRY_BASE_DELAY = 2.0
REPLICATE_RATE_LIMIT_RETRY_DELAY = 10.0


def _create_fallback_image(output_path: str, aspect_ratio: str = "9:16") -> None:
    """Replicate API 최종 실패 시 검은색 캔버스 단색 PNG 이미지를 생성한다."""
    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    if aspect_ratio == "9:16":
        width, height = 720, 1280
    elif aspect_ratio == "16:9":
        width, height = 1280, 720
    elif aspect_ratio == "1:1":
        width, height = 1024, 1024
    else:
        width, height = 720, 1280

    fallback_img = Image.new("RGB", (width, height), (0, 0, 0))
    fallback_img.save(output_path, "PNG")


def generate_image(
    prompt_text: str,
    output_path: str,
    api_key: Optional[str] = None,
    aspect_ratio: str = "9:16",
) -> Dict:
    """Replicate API (black-forest-labs/flux-schnell)로 텍스트 프롬프트 기반 이미지를 생성한다.

    api_key가 None이면 .env의 REPLICATE_API_TOKEN 사용.
    aspect_ratio 기본값은 숏폼 세로 비율(9:16).

    Returns:
        {
            "image_path": str,
            "success": bool,
            "error": str | None
        }

    실패 시 최대 3회 재시도 (Rate limit 429 시 10초 딜레이).
    최종 실패 시 예외를 던지지 않고 success: False와 검은색 fallback 이미지를 반환.
    """
    prompt_text = (prompt_text or "").strip()
    if not prompt_text:
        _create_fallback_image(output_path, aspect_ratio)
        return {
            "image_path": output_path,
            "success": False,
            "error": "입력 프롬프트 텍스트가 비어 있습니다.",
        }

    if replicate is None:
        _create_fallback_image(output_path, aspect_ratio)
        return {
            "image_path": output_path,
            "success": False,
            "error": "replicate 패키지가 설치되어 있지 않습니다.",
        }

    resolved_api_key = api_key or os.environ.get("REPLICATE_API_TOKEN")
    if not resolved_api_key:
        _create_fallback_image(output_path, aspect_ratio)
        return {
            "image_path": output_path,
            "success": False,
            "error": "REPLICATE_API_TOKEN이 .env 파일에 설정되어 있지 않습니다.",
        }

    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    client = replicate.Client(api_token=resolved_api_key, timeout=120.0)
    last_error = None

    for attempt in range(1, REPLICATE_MAX_RETRIES + 1):
        wait_seconds = REPLICATE_RETRY_BASE_DELAY * attempt
        try:
            output = client.run(
                "black-forest-labs/flux-schnell",
                input={
                    "prompt": prompt_text,
                    "aspect_ratio": aspect_ratio,
                    "output_format": "png",
                },
            )

            # 출력 결과 다운로드 처리
            img_url = None
            if isinstance(output, list) and len(output) > 0:
                img_url = str(output[0])
            elif isinstance(output, str):
                img_url = output
            elif hasattr(output, "url"):
                img_url = str(output.url)
            elif hasattr(output, "read"):
                # 파일 객체인 경우 직접 저장
                with open(output_path, "wb") as f:
                    f.write(output.read())
                return {
                    "image_path": output_path,
                    "success": True,
                    "error": None,
                }

            if img_url and img_url.startswith("http"):
                res = requests.get(img_url, timeout=120)
                res.raise_for_status()
                with open(output_path, "wb") as f:
                    f.write(res.content)

                if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                    return {
                        "image_path": output_path,
                        "success": True,
                        "error": None,
                    }
                else:
                    last_error = "다운로드한 이미지 파일 크기가 0입니다."
            else:
                last_error = f"예상치 못한 Replicate API 출력 형식: {type(output)}"

        except Exception as exc:
            err_str = str(exc)
            last_error = err_str
            if "429" in err_str or "rate limit" in err_str.lower():
                wait_seconds = max(wait_seconds, REPLICATE_RATE_LIMIT_RETRY_DELAY)

        if attempt < REPLICATE_MAX_RETRIES:
            print(
                f"[ImageGen] 시도 {attempt}/{REPLICATE_MAX_RETRIES} 실패 ({last_error}). {wait_seconds}초 후 재시도..."
            )
            time.sleep(wait_seconds)

    # 모든 재시도 실패 시 검은색 Fallback 이미지 생성
    print(f"[ImageGen] 이미지 생성 최종 실패: {last_error}. Fallback 검은색 이미지 생성 중...")
    _create_fallback_image(output_path, aspect_ratio)
    return {
        "image_path": output_path,
        "success": False,
        "error": f"Replicate API 최종 실패: {last_error}",
    }


if __name__ == "__main__":
    prompt = (
        "A young Korean woman applying skincare serum, cinematic lighting, close-up, vertical shot"
    )
    test_output = "outputs/test_images/scene_01.png"

    print(f"[+] Replicate 이미지 생성 요청 중: '{prompt[:50]}...'")
    result = generate_image(
        prompt_text=prompt,
        output_path=test_output,
    )
    print(f"[+] 이미지 생성 결과: {result}")
