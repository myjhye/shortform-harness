"""
Stage 9: Replicate 비디오 클립 생성기 (wan-video/wan-2.2-i2v-fast 모델)
Replicate API를 사용해서 정지 이미지를 짧은 동영상 클립(MP4)으로 변환한다.
실패 시 예외를 던지지 않고 ffmpeg 정지 이미지 루프 fallback 영상을 자동 생성하여 반환한다.
"""
import os
import subprocess
import time
from typing import Dict, Optional
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
REPLICATE_TIMEOUT_SEC = 300.0


def _create_fallback_video(
    image_path: str, output_path: str, duration_sec: float
) -> None:
    """Replicate API 최종 실패 시 ffmpeg으로 정지 이미지를 duration_sec 길이의 MP4 동영상으로 변환한다."""
    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    cmd = [
        "ffmpeg",
        "-y",
        "-loop",
        "1",
        "-i",
        image_path,
        "-c:v",
        "libx264",
        "-t",
        str(duration_sec),
        "-pix_fmt",
        "yuv420p",
        "-vf",
        "scale=trunc(iw/2)*2:trunc(ih/2)*2",
        output_path,
    ]

    startupinfo = None
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

    try:
        subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            startupinfo=startupinfo,
        )
    except Exception as e:
        print(f"[VideoGen] Fallback 영상 생성 에러: {e}")


def _trim_video_to_duration(
    input_video_path: str, target_duration_sec: float
) -> None:
    """생성된 비디오 클립의 길이를 target_duration_sec에 정확히 맞춰 자른다."""
    if not os.path.exists(input_video_path):
        return

    temp_path = input_video_path + ".tmp.mp4"
    if os.path.exists(temp_path):
        os.remove(temp_path)
    os.rename(input_video_path, temp_path)

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        temp_path,
        "-t",
        str(target_duration_sec),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        input_video_path,
    ]

    startupinfo = None
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

    try:
        subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            startupinfo=startupinfo,
        )
        if os.path.exists(temp_path):
            os.remove(temp_path)
    except Exception as e:
        print(f"[VideoGen] 비디오 길이 자르기 실패 (원본 유지): {e}")
        if os.path.exists(temp_path) and not os.path.exists(input_video_path):
            os.rename(temp_path, input_video_path)


def generate_video_clip(
    image_path: str,
    output_path: str,
    prompt: str = "",
    duration_sec: float = 3.0,
    min_ai_duration_sec: float = 1.0,
    api_key: Optional[str] = None,
) -> Dict:
    """Replicate API(wan-video/wan-2.2-i2v-fast)로 정지 이미지를

    짧은 동영상 클립으로 변환한다.
    api_key가 None이면 .env의 REPLICATE_API_TOKEN 사용.

    duration_sec가 min_ai_duration_sec(기본 1.0초) 미만일 경우 API 호출을 스킵하고
    ffmpeg 정지 이미지 클립으로 즉시 변환한다 (비용/시간 절약).

    Returns:
        {
            "video_path": str,
            "success": bool,
            "error": str | None
        }

    실패 시 최대 3회 재시도 (rate limit 처리 포함).
    최종 실패 시 예외를 던지지 않고 ffmpeg으로 정지 이미지를 duration_sec 길이의
    정지 MP4 영상으로 변환하여 반환한다.
    """
    if not os.path.exists(image_path):
        return {
            "video_path": output_path,
            "success": False,
            "error": f"입력 이미지 파일을 찾을 수 없습니다: {image_path}",
        }

    # 짧은 컷(1초 미만)은 AI 생성 스킵 후 ffmpeg 정지 이미지 클립으로 즉시 반환
    if duration_sec < min_ai_duration_sec:
        print(
            f"[VideoGen] 컷 길이({duration_sec:.2f}초)가 AI 임계값({min_ai_duration_sec:.1f}초) 미만이므로 정지 클립으로 즉시 생성합니다 (비용/시간 절약)."
        )
        _create_fallback_video(image_path, output_path, duration_sec)
        return {
            "video_path": output_path,
            "success": True,
            "error": None,
        }

    if replicate is None:
        _create_fallback_video(image_path, output_path, duration_sec)
        return {
            "video_path": output_path,
            "success": False,
            "error": "replicate 패키지가 설치되어 있지 않습니다.",
        }

    resolved_api_key = api_key or os.environ.get("REPLICATE_API_TOKEN")
    if not resolved_api_key:
        _create_fallback_video(image_path, output_path, duration_sec)
        return {
            "video_path": output_path,
            "success": False,
            "error": "REPLICATE_API_TOKEN이 .env 파일에 설정되어 있지 않습니다.",
        }

    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    client = replicate.Client(
        api_token=resolved_api_key, timeout=REPLICATE_TIMEOUT_SEC
    )
    last_error = None

    for attempt in range(1, REPLICATE_MAX_RETRIES + 1):
        wait_seconds = REPLICATE_RETRY_BASE_DELAY * attempt
        try:
            fps = 16
            # Wan 2.2-i2v-fast 모델 제약 조건: num_frames >= 81 (최소 5.06초 분량)
            num_frames = max(81, int(round(duration_sec * fps)))

            with open(image_path, "rb") as img_file:
                input_params = {
                    "image": img_file,
                    "num_frames": num_frames,
                    "frames_per_second": fps,
                }
                if prompt and prompt.strip():
                    input_params["prompt"] = prompt.strip()

                print(
                    f"[VideoGen] Replicate 영상 클립 생성 호출 (시도 {attempt}/{REPLICATE_MAX_RETRIES}, 목표={duration_sec}초, API={num_frames}프레임@{fps}fps)..."
                )
                output = client.run(
                    "wan-video/wan-2.2-i2v-fast", input=input_params
                )

            # 결과 다운로드 처리
            video_url = None
            if isinstance(output, list) and len(output) > 0:
                video_url = str(output[0])
            elif isinstance(output, str):
                video_url = output
            elif hasattr(output, "url"):
                video_url = str(output.url)

            if video_url and video_url.startswith("http"):
                res = requests.get(video_url, timeout=REPLICATE_TIMEOUT_SEC)
                res.raise_for_status()
                with open(output_path, "wb") as f:
                    f.write(res.content)
            elif hasattr(output, "read"):
                with open(output_path, "wb") as f:
                    f.write(output.read())

            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                # 목표 duration_sec와 생성 영상 길이가 다른 경우 ffmpeg 트림 적용
                _trim_video_to_duration(output_path, duration_sec)
                return {
                    "video_path": output_path,
                    "success": True,
                    "error": None,
                }
            else:
                last_error = "다운로드한 비디오 파일 크기가 0입니다."

        except Exception as exc:
            err_str = str(exc)
            last_error = err_str
            if "429" in err_str or "rate limit" in err_str.lower():
                wait_seconds = max(
                    wait_seconds, REPLICATE_RATE_LIMIT_RETRY_DELAY
                )

        if attempt < REPLICATE_MAX_RETRIES:
            print(
                f"[VideoGen] 시도 {attempt}/{REPLICATE_MAX_RETRIES} 실패 ({last_error}). {wait_seconds}초 후 재시도..."
            )
            time.sleep(wait_seconds)

    # 모든 재시도 실패 시 ffmpeg 루프 Fallback 영상 생성
    print(
        f"[VideoGen] Replicate 영상 클립 생성 최종 실패: {last_error}. ffmpeg Fallback 정지 영상 생성 중..."
    )
    _create_fallback_video(image_path, output_path, duration_sec)
    return {
        "video_path": output_path,
        "success": False,
        "error": f"Replicate API 최종 실패: {last_error}",
    }


if __name__ == "__main__":
    test_image = "outputs/test_images/scene_01.png"
    test_video = "outputs/test_videos/scene_01.mp4"
    test_prompt = "gentle camera movement, subtle motion"

    # 테스트 이미지가 없는 경우 검은색 더미 이미지 자동 생성
    if not os.path.exists(test_image):
        print(f"[+] 테스트용 이미지 생성 중: '{test_image}'")
        from generation.image_gen import generate_image

        generate_image(
            prompt_text="A young Korean woman applying skincare serum",
            output_path=test_image,
        )

    print(f"[+] Replicate 비디오 클립 생성 요청 중 (3.0초): '{test_image}' -> '{test_video}'")
    result = generate_video_clip(
        image_path=test_image,
        output_path=test_video,
        prompt=test_prompt,
        duration_sec=3.0,
    )
    print(f"[+] 3.0초 영상 클립 생성 결과: {result}")

    short_video = "outputs/test_videos/scene_short.mp4"
    print(f"\n[+] 짧은 컷 최적화 테스트 (0.6초): '{test_image}' -> '{short_video}'")
    short_result = generate_video_clip(
        image_path=test_image,
        output_path=short_video,
        prompt=test_prompt,
        duration_sec=0.6,
    )
    print(f"[+] 0.6초 짧은 컷 클립 생성 결과: {short_result}")
