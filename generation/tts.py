"""
Stage 7: ElevenLabs TTS 생성기 (Alignment / 타임스탬프 지원)
ElevenLabs API의 with-timestamps 엔드포인트를 호출하여
TTS 오디오 파일(MP3)과 문자별 타임스탬프 정보를 함께 받아 반환한다.
"""
import base64
import os
import subprocess
import time
from typing import Dict, List, Optional
import requests
from dotenv import load_dotenv

# .env 환경변수 로드
load_dotenv()

TTS_MAX_RETRIES = 3
TTS_RETRY_BASE_DELAY = 1.0


def get_default_voice_id() -> str:
    """기본 ElevenLabs Voice ID를 반환한다."""
    return "EXAVITQu4vr4xnSDxMaL"  # Sarah (Standard valid public voice)


def _get_audio_duration(audio_path: str) -> float:
    """ffprobe를 통해 오디오 파일의 길이를 초 단위로 반환한다."""
    if not os.path.exists(audio_path):
        return 0.0

    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        audio_path,
    ]
    try:
        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        out = subprocess.check_output(
            cmd, stderr=subprocess.STDOUT, startupinfo=startupinfo
        )
        return round(float(out.decode("utf-8").strip()), 2)
    except Exception:
        return 0.0


def generate_tts(
    text: str,
    voice_id: Optional[str] = None,
    output_path: str = "outputs/tts.mp3",
    api_key: Optional[str] = None,
    model_id: str = "eleven_turbo_v2_5",
) -> Dict:
    """ElevenLabs API로 TTS 생성 + alignment(타임스탬프) 정보를 함께 받는다.

    api_key가 None이면 .env의 ELEVENLABS_API_KEY 사용.

    Returns:
        {
            "audio_path": str,       # 저장된 오디오 파일 경로
            "alignment": dict | None,  # 문자별 타임스탬프 정보 (API 원본 그대로)
            "duration_sec": float    # 오디오 전체 길이
        }

    실패 시 최대 3회 재시도 (TTS_MAX_RETRIES, TTS_RETRY_BASE_DELAY 패턴 적용).
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("TTS 생성을 위한 입력 텍스트가 비어 있습니다.")

    resolved_api_key = api_key or os.environ.get("ELEVENLABS_API_KEY")
    if not resolved_api_key:
        raise ValueError(
            "ELEVENLABS_API_KEY가 설정되지 않았습니다. .env 파일에 등록하거나 api_key 파라미터로 전달하세요."
        )

    resolved_voice_id = voice_id or get_default_voice_id()

    url = (
        f"https://api.elevenlabs.io/v1/text-to-speech/{resolved_voice_id}/with-timestamps"
    )
    headers = {
        "xi-api-key": resolved_api_key,
        "Accept": "application/json",
    }

    payload = {
        "text": text,
        "model_id": model_id,
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
            "style": 0.0,
            "speed": 1.0,
            "use_speaker_boost": True,
        },
        "output_format": "mp3_44100_128",
        "optimize_streaming_latency": 0,
    }

    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    last_error = None

    for attempt in range(1, TTS_MAX_RETRIES + 1):
        wait_seconds = TTS_RETRY_BASE_DELAY * attempt
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=120)
            if resp.status_code == 200:
                data = resp.json()
                audio_b64 = data.get("audio") or data.get("audio_base64")
                alignment = data.get("alignment")

                if not audio_b64:
                    last_error = "오디오 데이터가 비어 있습니다."
                else:
                    audio_bytes = base64.b64decode(audio_b64)
                    with open(output_path, "wb") as f:
                        f.write(audio_bytes)

                    if os.path.getsize(output_path) == 0:
                        last_error = "생성된 오디오 파일 크기가 0입니다."
                    else:
                        duration_sec = _get_audio_duration(output_path)
                        if duration_sec == 0.0 and alignment:
                            end_times = alignment.get(
                                "character_end_times_seconds", []
                            )
                            if end_times:
                                duration_sec = round(float(end_times[-1]), 2)

                        return {
                            "audio_path": output_path,
                            "alignment": alignment,
                            "duration_sec": duration_sec,
                        }
            else:
                error_detail = ""
                try:
                    error_json = resp.json()
                    error_detail = (
                        error_json.get("detail")
                        or error_json.get("message")
                        or str(error_json)
                    )
                except Exception:
                    error_detail = resp.text[:300]
                last_error = f"HTTP {resp.status_code}: {error_detail}"

        except Exception as exc:
            last_error = str(exc)

        if attempt < TTS_MAX_RETRIES:
            print(
                f"[TTS] 시도 {attempt}/{TTS_MAX_RETRIES} 실패 ({last_error}). {wait_seconds}초 후 재시도..."
            )
            time.sleep(wait_seconds)

    raise RuntimeError(
        f"ElevenLabs TTS 생성 실패 ({TTS_MAX_RETRIES}회 시도): {last_error}"
    )


def concat_audio_clips(audio_paths: List[str], output_path: str) -> float:
    """여러 개의 mp3 오디오 파일들을 순서대로 이어붙여 하나의 오디오 파일로 만든다.

    FFmpeg concat demuxer 사용. 반환값은 합쳐진 전체 재생 시간(초).
    """
    if not audio_paths:
        raise ValueError("audio_paths 리스트가 비어 있습니다.")

    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    temp_concat_list = os.path.join(
        out_dir, f"concat_audio_list_{int(time.time())}.txt"
    )
    with open(temp_concat_list, "w", encoding="utf-8") as f:
        for path in audio_paths:
            if not os.path.exists(path):
                raise FileNotFoundError(f"Audio clip file not found: {path}")
            safe_p = os.path.abspath(path).replace("\\", "/")
            f.write(f"file '{safe_p}'\n")

    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        temp_concat_list,
        "-c",
        "copy",
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
    finally:
        if os.path.exists(temp_concat_list):
            os.remove(temp_concat_list)

    return _get_audio_duration(output_path)


if __name__ == "__main__":
    test_text = "퇴근하고 3분, 이거 안 하면 5년 뒤 후회함"
    test_output = "outputs/test_tts/hook_test.mp3"

    print(f"[+] TTS 생성 요청 중: '{test_text}'")
    result = generate_tts(
        text=test_text,
        voice_id=get_default_voice_id(),
        output_path=test_output,
    )

    print(f"\n[+] TTS 생성 완료: {result['audio_path']}")
    print(f"  - 길이: {result['duration_sec']}초")
    print(f"  - alignment 정보 존재: {result['alignment'] is not None}")
    if result["alignment"]:
        chars = result["alignment"].get("characters", [])
        starts = result["alignment"].get("character_start_times_seconds", [])
        ends = result["alignment"].get("character_end_times_seconds", [])
        print(f"  - 문자 개수: {len(chars)}개")
        print(f"  - 처음 5문자: {chars[:5]}")
        print(f"  - 처음 5문자 시작 타임스탬프: {starts[:5]}")
