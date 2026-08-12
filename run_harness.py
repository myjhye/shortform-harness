"""
shortform-harness CLI: 레퍼런스 영상 분석 및 숏폼 영상 생성 파이프라인 하네스
Stage 1~10 파이프라인 전체를 오케스트레이션하여 숏폼 영상(MP4)을 자동 제작한다.
"""
import argparse
from datetime import datetime, timezone
import json
import os
import shutil
import sys

# Windows 콘솔 유니코드 출력 인코딩 설정
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from analysis.style_spec_builder import build_style_spec, save_style_spec
from generation.compositor import composite_video
from generation.image_gen import generate_image
from generation.llm import call_gemini_text
from generation.prompt_composer import (
    compose_hook_prompt,
    compose_image_prompt,
    compose_subtitle_prompt,
)
from generation.tts import concat_audio_clips, generate_tts, get_default_voice_id
from generation.video_gen import generate_video_clip


def main():
    parser = argparse.ArgumentParser(
        description="shortform-harness CLI: 레퍼런스 영상 분석 및 숏폼 영상 생성 파이프라인 하네스"
    )
    parser.add_argument(
        "--ref",
        nargs="+",
        default=["references/ref1.mp4", "references/ref2.mp4"],
        help="레퍼런스 영상 파일 경로 목록 (기본값: references/ref1.mp4 references/ref2.mp4)",
    )
    parser.add_argument(
        "--input",
        required=True,
        help="사용자 입력 프롬프트 (주제)",
    )
    parser.add_argument(
        "--spec-cache",
        default=None,
        help="기존 style_spec.json 파일 경로 (지정 시 분석 단계 생략 및 재사용)",
    )
    parser.add_argument(
        "--output",
        default="outputs/videos",
        help="생성 결과물 영상 출력 폴더 경로 (기본값: outputs/videos)",
    )
    parser.add_argument(
        "--num-scenes",
        type=int,
        default=3,
        help="생성할 씬(자막 세그먼트) 개수 (기본값: 3)",
    )
    parser.add_argument(
        "--voice-id",
        default=None,
        help="TTS 보이스 ID (지정하지 않으면 기본 보이스 사용)",
    )

    args = parser.parse_args()

    print("=" * 60)
    print("[+] shortform-harness 실행 설정:")
    print(f"  - 레퍼런스 영상: {args.ref}")
    print(f"  - 사용자 프롬프트: '{args.input}'")
    print(f"  - 스펙 캐시 경로: {args.spec_cache}")
    print(f"  - 씬 수(세그먼트): {args.num_scenes}개")
    print(f"  - 출력 폴더: {args.output}")
    print("=" * 60)

    timestamp = int(datetime.now(timezone.utc).timestamp())
    voice_id = args.voice_id or get_default_voice_id()

    # 작업 전 임시 폴더 초기화
    temp_work_dir = "outputs/temp"
    shutil.rmtree(temp_work_dir, ignore_errors=True)
    os.makedirs(temp_work_dir, exist_ok=True)

    # -----------------------------------------------------------------
    # 1. [분석 단계] Style Spec 준비
    # -----------------------------------------------------------------
    if args.spec_cache and os.path.exists(args.spec_cache):
        print(f"\n[1/5] 기존 스펙 캐시 로드 중: '{args.spec_cache}'")
        try:
            with open(args.spec_cache, encoding="utf-8") as f:
                spec = json.load(f)
            spec_save_path = args.spec_cache
        except Exception as e:
            print(f"[!] 스펙 캐시 파일 로드 실패: {e}")
            sys.exit(1)
    else:
        print(f"\n[1/5] 레퍼런스 영상 분석 중... ({args.ref})")
        try:
            spec = build_style_spec(args.ref)
            spec_save_path = f"outputs/style_specs/style_spec_{timestamp}.json"
            save_style_spec(spec, spec_save_path)
        except Exception as e:
            print(f"[!] 레퍼런스 영상 스타일 분석 실패: {e}")
            sys.exit(1)

    # -----------------------------------------------------------------
    # 2. [훅 생성 단계]
    # -----------------------------------------------------------------
    print("\n[2/5] Gemini LLM 기반 훅(Hook) 문구 생성 중...")
    try:
        hook_prompt_meta = compose_hook_prompt(spec, args.input)
        hook_text = call_gemini_text(hook_prompt_meta)
        print(f"  → 생성된 훅 문구: '{hook_text}'")
    except Exception as e:
        print(f"[!] 훅 문구 생성 실패: {e}")
        sys.exit(1)

    # -----------------------------------------------------------------
    # 3. [자막 스크립트 생성 단계]
    # -----------------------------------------------------------------
    print(f"\n[3/5] Gemini LLM 기반 자막 스크립트 생성 중 ({args.num_scenes}개 세그먼트)...")
    try:
        sub_prompt_meta = compose_subtitle_prompt(
            spec, args.input, num_segments=args.num_scenes
        )
        sub_json_str = call_gemini_text(sub_prompt_meta, response_as_json=True)

        try:
            subtitle_segments = json.loads(sub_json_str)
        except Exception:
            # 파싱 실패 시 1회 재시도
            print("  [!] 자막 스크립트 JSON 파싱 1차 실패. 재시도 중...")
            sub_json_str = call_gemini_text(sub_prompt_meta, response_as_json=True)
            subtitle_segments = json.loads(sub_json_str)

        if not isinstance(subtitle_segments, list) or not subtitle_segments:
            raise ValueError("생성된 자막 세그먼트 배열이 비어있거나 올바르지 않습니다.")

        # 첫 번째 세그먼트는 2단계에서 생성한 훅 문구로 대체 (훅=첫 자막)
        subtitle_segments[0]["text"] = hook_text
        print(f"  → 자막 스크립트 생성 완료 ({len(subtitle_segments)}개 세그먼트 파싱 성공)")

    except Exception as e:
        print(f"[!] 자막 스크립트 생성 및 파싱 실패: {e}")
        sys.exit(1)

    # -----------------------------------------------------------------
    # 4. [자산 생성 단계 - 씬별 순차 반복]
    # -----------------------------------------------------------------
    print(f"\n[4/5] 씬별 멀티미디어 자산(TTS / Image / Video Clip) 생성 시작...")
    accumulated_audio_paths = []
    accumulated_video_paths = []
    accumulated_durations = []

    for idx, seg in enumerate(subtitle_segments):
        seg_text = str(seg.get("text", "")).strip()
        print(f"\n  [Scene {idx+1}/{len(subtitle_segments)}] 텍스트: '{seg_text}'")

        # a. TTS 생성 (실제 재생 오디오 길이를 진실의 원천으로 사용)
        tts_path = os.path.join(temp_work_dir, f"tts_{idx:02d}.mp3")
        try:
            tts_res = generate_tts(
                text=seg_text,
                voice_id=voice_id,
                output_path=tts_path,
            )
            actual_duration = tts_res["duration_sec"]
            print(f"    - TTS 생성 완료: {tts_path} ({actual_duration}초)")
        except Exception as e:
            print(f"[!] 씬 {idx+1} TTS 생성 실패: {e}")
            sys.exit(1)

        # b. 이미지 영문 프롬프트 생성 (Gemini LLM)
        try:
            img_prompt_meta = compose_image_prompt(spec, args.input, seg_text)
            img_prompt_text = call_gemini_text(img_prompt_meta)
            print(f"    - 이미지 영문 프롬프트: '{img_prompt_text[:60]}...'")
        except Exception as e:
            print(f"[!] 씬 {idx+1} 이미지 프롬프트 생성 실패: {e}")
            sys.exit(1)

        # c. 이미지 생성 (Replicate Flux Schnell)
        img_path = os.path.join(temp_work_dir, f"img_{idx:02d}.png")
        try:
            img_res = generate_image(prompt_text=img_prompt_text, output_path=img_path)
            if not img_res["success"]:
                print(f"    [!] 씬 {idx+1} 이미지 생성 실패 경고: {img_res['error']} (Fallback 검은색 이미지 사용)")
            else:
                print(f"    - 이미지 생성 완료: {img_path}")
        except Exception as e:
            print(f"[!] 씬 {idx+1} 이미지 생성 중 심각한 에러: {e}")
            sys.exit(1)

        # d. 비디오 클립 생성 (Replicate Wan 2.2 또는 1초 미만 Fast Static Clip)
        clip_path = os.path.join(temp_work_dir, f"clip_{idx:02d}.mp4")
        try:
            vid_res = generate_video_clip(
                image_path=img_path,
                output_path=clip_path,
                prompt="subtle natural motion, high quality",
                duration_sec=actual_duration,
            )
            if not vid_res["success"]:
                print(f"    [!] 씬 {idx+1} 비디오 클립 생성 실패 경고: {vid_res['error']} (Fallback 영상 사용)")
            else:
                print(f"    - 비디오 클립 생성 완료: {clip_path}")
        except Exception as e:
            print(f"[!] 씬 {idx+1} 비디오 클립 생성 예외: {e}")
            sys.exit(1)

        accumulated_audio_paths.append(tts_path)
        accumulated_video_paths.append(clip_path)
        accumulated_durations.append(actual_duration)

    # -----------------------------------------------------------------
    # 5. [최종 합성 단계]
    # -----------------------------------------------------------------
    print("\n[5/5] 전체 나레이션 오디오 병합 및 최종 영상 합성 중...")
    try:
        full_audio_path = os.path.join(temp_work_dir, "full_audio.mp3")
        total_audio_sec = concat_audio_clips(accumulated_audio_paths, full_audio_path)

        # 자막 타임스탬프 계산 (누적 시작/끝 시각)
        timed_subtitles = []
        curr_time = 0.0
        for idx, seg in enumerate(subtitle_segments):
            dur = accumulated_durations[idx]
            timed_subtitles.append(
                {
                    "text": seg["text"],
                    "start_sec": round(curr_time, 2),
                    "end_sec": round(curr_time + dur, 2),
                }
            )
            curr_time += dur

        os.makedirs(args.output, exist_ok=True)
        final_video_path = os.path.join(
            args.output, f"harness_output_{timestamp}.mp4"
        )

        comp_res = composite_video(
            scene_clips=accumulated_video_paths,
            tts_audio_path=full_audio_path,
            subtitle_segments=timed_subtitles,
            output_path=final_video_path,
        )

        if not comp_res["success"]:
            raise RuntimeError(f"최종 비디오 합성 오류: {comp_res['error']}")

    except Exception as e:
        print(f"[!] [5/5] 최종 영상 합성 실패: {e}")
        sys.exit(1)

    # -----------------------------------------------------------------
    # 6. [결과 요약 출력]
    # -----------------------------------------------------------------
    print("\n" + "=" * 60)
    print("[+] shortform-harness 최종 영상 파이프라인 제작 완료!")
    print("=" * 60)
    print(f"  - 최종 영상 경로: {final_video_path}")
    print(f"  - 총 재생 시간: {comp_res['duration_sec']}초")
    print(f"  - 사용된 style_spec 경로: {spec_save_path}")
    print("  - 각 씬 자막 대본 목록:")
    for idx, sub in enumerate(timed_subtitles, 1):
        print(
            f"    {idx}. [{sub['start_sec']:.2f}s ~ {sub['end_sec']:.2f}s] \"{sub['text']}\""
        )
    print("=" * 60)


if __name__ == "__main__":
    main()
