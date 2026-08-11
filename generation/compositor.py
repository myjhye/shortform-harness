"""
Stage 10: 최종 영상 합성기 (Compositor)
씬별 영상 클립, TTS 나레이션 오디오, 자막 세그먼트를 ffmpeg으로 결합 및 합성하여
최종 숏폼 MP4 비디오(1080x1920 세로 비율, H.264 / AAC)를 제작한다.
"""
import os
import shutil
import subprocess
import time
from typing import Dict, List, Optional


def _run_ffmpeg(cmd: List[str]) -> None:
    """Windows 콘솔 창 안 뜨게 처리하는 FFmpeg subprocess 실행 헬퍼"""
    startupinfo = None
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

    res = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        startupinfo=startupinfo,
    )
    if res.returncode != 0:
        err_out = res.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(
            f"FFmpeg 실행 실패 (exit code {res.returncode}): {err_out[-500:]}"
        )


def _get_media_duration(media_path: str) -> float:
    """ffprobe를 사용하여 미디어(영상/오디오) 재생 길이를 초 단위로 측정한다."""
    if not os.path.exists(media_path):
        return 0.0

    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        media_path,
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


def _format_srt_time(seconds: float) -> str:
    """초 단위 float 시간을 SRT 자막 타임스탬프 Format (00:00:00,000)으로 변환"""
    seconds = max(0.0, seconds)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    if millis >= 1000:
        secs += 1
        millis -= 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def segments_to_srt(subtitle_segments: List[Dict], srt_path: str) -> None:
    """subtitle_segments를 SRT 자막 파일 형식으로 저장한다.

    subtitle_segments 예시:
    [{"text": "자막 내용", "start_sec": 0.0, "end_sec": 2.8}, ...]
    """
    out_dir = os.path.dirname(srt_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    lines = []
    for idx, seg in enumerate(subtitle_segments, 1):
        text = str(seg.get("text", "")).strip()
        if not text:
            continue
        start_sec = float(seg.get("start_sec", 0.0))
        end_sec = float(seg.get("end_sec", start_sec + 2.0))

        start_str = _format_srt_time(start_sec)
        end_str = _format_srt_time(end_sec)

        lines.append(f"{idx}")
        lines.append(f"{start_str} --> {end_str}")
        lines.append(text)
        lines.append("")

    with open(srt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def composite_video(
    scene_clips: List[str],
    tts_audio_path: str,
    subtitle_segments: List[Dict],
    output_path: str,
    fps: int = 25,
) -> Dict:
    """씬 클립들을 순서대로 이어붙이고, 그 위에 TTS 오디오와 자막을

    합성해서 최종 숏폼 영상을 만든다.

    Returns:
        {
            "output_path": str,
            "success": bool,
            "duration_sec": float,
            "error": str | None
        }
    """
    if not scene_clips:
        return {
            "output_path": output_path,
            "success": False,
            "duration_sec": 0.0,
            "error": "scene_clips 리스트가 비어 있습니다.",
        }

    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    temp_dir = os.path.join("outputs", "temp", f"comp_{int(time.time())}")
    os.makedirs(temp_dir, exist_ok=True)

    try:
        # -------------------------------------------------------------
        # 1단계: 각 씬 클립 표준화 (1080x1920, h264, 25fps) 및 Concat
        # -------------------------------------------------------------
        print(f"[Compositor] [1/3] 씬 클립 {len(scene_clips)}개 표준화 및 Concat 처리...")
        norm_clips = []
        for i, clip in enumerate(scene_clips):
            if not os.path.exists(clip):
                raise FileNotFoundError(f"씬 클립 파일을 찾을 수 없습니다: {clip}")

            norm_clip_path = os.path.join(temp_dir, f"norm_clip_{i:03d}.mp4")
            cmd_norm = [
                "ffmpeg",
                "-y",
                "-i",
                clip,
                "-vf",
                "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black",
                "-r",
                str(fps),
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                norm_clip_path,
            ]
            _run_ffmpeg(cmd_norm)
            norm_clips.append(norm_clip_path)

        concat_txt_path = os.path.join(temp_dir, "concat_list.txt")
        with open(concat_txt_path, "w", encoding="utf-8") as f:
            for n_path in norm_clips:
                safe_p = os.path.abspath(n_path).replace("\\", "/")
                f.write(f"file '{safe_p}'\n")

        concat_video_path = os.path.join(temp_dir, "concat_video.mp4")
        cmd_concat = [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            concat_txt_path,
            "-c",
            "copy",
            concat_video_path,
        ]
        _run_ffmpeg(cmd_concat)

        # -------------------------------------------------------------
        # 2단계: 오디오 트랙 얹기 (TTS 나레이션)
        # -------------------------------------------------------------
        print("[Compositor] [2/3] TTS 오디오 트랙 합성 중...")
        video_dur = _get_media_duration(concat_video_path)
        audio_dur = (
            _get_media_duration(tts_audio_path)
            if os.path.exists(tts_audio_path)
            else 0.0
        )

        video_audio_path = os.path.join(temp_dir, "video_audio.mp4")

        if os.path.exists(tts_audio_path) and audio_dur > 0:
            if video_dur < audio_dur:
                # 영상이 오디오보다 짧으면 마지막 프레임을 늘림 (tpad)
                pad_sec = round(audio_dur - video_dur + 0.1, 2)
                cmd_audio = [
                    "ffmpeg",
                    "-y",
                    "-i",
                    concat_video_path,
                    "-i",
                    tts_audio_path,
                    "-filter_complex",
                    f"[0:v]tpad=stop_mode=clone:stop_duration={pad_sec}[v]",
                    "-map",
                    "[v]",
                    "-map",
                    "1:a",
                    "-c:v",
                    "libx264",
                    "-c:a",
                    "aac",
                    "-shortest",
                    video_audio_path,
                ]
            else:
                # 영상이 오디오보다 길거나 같으면 audio 트랙 얹고 shortest 적용
                cmd_audio = [
                    "ffmpeg",
                    "-y",
                    "-i",
                    concat_video_path,
                    "-i",
                    tts_audio_path,
                    "-c:v",
                    "copy",
                    "-c:a",
                    "aac",
                    "-shortest",
                    video_audio_path,
                ]
            _run_ffmpeg(cmd_audio)
        else:
            # TTS 오디오가 없을 경우 비디오 원본 그대로 사용
            shutil.copy(concat_video_path, video_audio_path)

        # -------------------------------------------------------------
        # 3단계: 자막 하드섭(Hardsub) 구워내기
        # -------------------------------------------------------------
        print("[Compositor] [3/3] 자막 하드섭(Hardsub) 처리 중...")
        if subtitle_segments:
            srt_path = os.path.join(temp_dir, "subtitles.srt")
            segments_to_srt(subtitle_segments, srt_path)

            escaped_srt = (
                os.path.abspath(srt_path).replace("\\", "/").replace(":", "\\:")
            )
            # 자막 스타일: 중앙 하단, 큰 볼드 글씨, 흰색 글씨 + 검은 테두리
            sub_filter = (
                f"subtitles='{escaped_srt}':force_style="
                "'Alignment=2,FontSize=20,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=1,MarginV=90'"
            )

            cmd_sub = [
                "ffmpeg",
                "-y",
                "-i",
                video_audio_path,
                "-vf",
                sub_filter,
                "-c:v",
                "libx264",
                "-c:a",
                "copy",
                output_path,
            ]
            _run_ffmpeg(cmd_sub)
        else:
            shutil.copy(video_audio_path, output_path)

        # 최종 성공 시 결과 확인
        final_dur = _get_media_duration(output_path)
        print(f"[Compositor] [v] 최종 숏폼 영상 생성 완료: '{output_path}' ({final_dur}초)")
        return {
            "output_path": output_path,
            "success": True,
            "duration_sec": final_dur,
            "error": None,
        }

    except Exception as exc:
        err_msg = str(exc)
        print(f"[Compositor] [!] 영상 합성 중 에러 발생: {err_msg}")
        return {
            "output_path": output_path,
            "success": False,
            "duration_sec": 0.0,
            "error": err_msg,
        }
    finally:
        # 임시 작업 디렉토리 정리
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    test_scene_clips = ["outputs/test_videos/scene_01.mp4"]
    test_tts = "outputs/test_tts/hook_test.mp3"
    test_subtitles = [
        {
            "text": "퇴근하고 3분, 이거 안 하면 5년 뒤 후회함",
            "start_sec": 0.0,
            "end_sec": 2.8,
        }
    ]
    test_output = "outputs/test_final/mini_test.mp4"

    # 테스트 입력 파일 존재 여부 보장
    if not os.path.exists(test_scene_clips[0]):
        print(f"[+] 테스트용 비디오 클립 생성 중: '{test_scene_clips[0]}'")
        from generation.image_gen import generate_image
        from generation.video_gen import generate_video_clip

        img = "outputs/test_images/scene_01.png"
        if not os.path.exists(img):
            generate_image("A young Korean woman applying skincare serum", img)
        generate_video_clip(img, test_scene_clips[0], duration_sec=3.0)

    if not os.path.exists(test_tts):
        print(f"[+] 테스트용 TTS 생성 중: '{test_tts}'")
        from generation.tts import generate_tts

        generate_tts("퇴근하고 3분, 이거 안 하면 5년 뒤 후회함", output_path=test_tts)

    print(f"[+] 미니 통합 영상 합성 시작: '{test_output}'")
    result = composite_video(
        scene_clips=test_scene_clips,
        tts_audio_path=test_tts,
        subtitle_segments=test_subtitles,
        output_path=test_output,
    )
    print(f"[+] 최종 합성 결과: {result}")
