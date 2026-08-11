"""
Stage 5: 스타일 스펙 통합기
frame_extractor, cut_detector, vision_analyzer, audio_analyzer의 결과를
하나의 style_spec.json으로 통합하고 outputs/style_specs/에 저장한다.
여러 레퍼런스 영상 결과가 있을 경우 평균/병합 전략을 적용한다.
"""
from datetime import datetime, timezone
import json
import os
import sys
from typing import Dict, List

# 프로젝트 루트 경로를 sys.path 상단에 추가 (독립 실행 및 모듈 참조 지원)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from analysis.cut_detector import detect_cuts
from analysis.frame_extractor import (
    extract_hook_frames,
    extract_sampled_frames,
)
from analysis.vision_analyzer import (
    analyze_hook,
    analyze_subtitle_pattern,
)


def build_style_spec(video_paths: List[str]) -> Dict:
    """여러 레퍼런스 영상을 분석해서 통합 스타일 스펙을 만든다.

    각 영상에 대해:
    1. cut_detector.detect_cuts()로 컷 리듬 분석
    2. frame_extractor.extract_hook_frames() + vision_analyzer.analyze_hook()으로 훅 분석
    3. frame_extractor.extract_sampled_frames() + vision_analyzer.analyze_subtitle_pattern()으로 자막 분석
    """
    if not video_paths:
        raise ValueError("video_paths 리스트가 비어 있습니다.")

    total_videos = len(video_paths)
    per_video_cuts: Dict[str, Dict] = {}
    per_video_hooks: Dict[str, Dict] = {}
    per_video_subtitles: Dict[str, Dict] = {}
    errors: List[Dict] = []

    for idx, video_path in enumerate(video_paths, 1):
        print(f"\n[+] [{idx}/{total_videos}] '{video_path}' 스타일 분석 시작...")
        if not os.path.exists(video_path):
            err_msg = f"Video file not found: {video_path}"
            print(f"  [!] 경고: {err_msg}")
            errors.append({"video_path": video_path, "error": err_msg})
            continue

        try:
            # 1. 컷 분석
            print(f"  - [{idx}/{total_videos}] Stage 2: 컷 리듬 분석 중...")
            cut_res = detect_cuts(video_path)
            per_video_cuts[video_path] = cut_res

            # 2. 훅 분석
            print(f"  - [{idx}/{total_videos}] Stage 1 & 3: 훅 분석 중...")
            hook_out_dir = os.path.join("outputs", "temp_frames", f"video_{idx}", "hook")
            hook_frames = extract_hook_frames(video_path, hook_out_dir)
            hook_res = analyze_hook(hook_frames)
            per_video_hooks[video_path] = hook_res

            # 3. 자막 패턴 분석
            print(f"  - [{idx}/{total_videos}] Stage 1 & 3: 자막 등장 패턴 분석 중...")
            sampled_out_dir = os.path.join("outputs", "temp_frames", f"video_{idx}", "sampled")
            sampled_frames = extract_sampled_frames(video_path, sampled_out_dir)
            sub_res = analyze_subtitle_pattern(sampled_frames)
            per_video_subtitles[video_path] = sub_res

            print(f"  [v] '{video_path}' 분석 완료")
        except Exception as e:
            err_msg = str(e)
            print(f"  [!] '{video_path}' 분석 중 오류 발생: {err_msg}")
            errors.append({"video_path": video_path, "error": err_msg})

    if not per_video_cuts:
        raise RuntimeError("분석에 성공한 영상이 없습니다.")

    # -------------------------------------------------------------
    # 컷 리듬 (cut_rhythm) 통합
    # -------------------------------------------------------------
    all_avg_cuts = [c["avg_cut_sec"] for c in per_video_cuts.values()]
    all_min_cuts = [c["min_cut_sec"] for c in per_video_cuts.values()]
    all_max_cuts = [c["max_cut_sec"] for c in per_video_cuts.values()]

    avg_cut_sec = round(sum(all_avg_cuts) / len(all_avg_cuts), 2)
    cut_range_sec = [round(min(all_min_cuts), 2), round(max(all_max_cuts), 2)]

    cut_rhythm_spec = {
        "avg_cut_sec": avg_cut_sec,
        "cut_range_sec": cut_range_sec,
        "per_video": {
            v: {
                "avg_cut_sec": res["avg_cut_sec"],
                "min_cut_sec": res["min_cut_sec"],
                "max_cut_sec": res["max_cut_sec"],
                "cut_count": res["cut_count"],
            }
            for v, res in per_video_cuts.items()
        },
    }

    # -------------------------------------------------------------
    # 훅 (hook) 통합
    # -------------------------------------------------------------
    all_hook_delays = [
        float(h.get("hook_text_appears_at_sec", 0.0)) for h in per_video_hooks.values()
    ]
    avg_hook_delay = round(sum(all_hook_delays) / len(all_hook_delays), 2)

    # 중복 제거 및 고유 스타일 풀 구성 (순서 보장)
    hook_styles = []
    for h in per_video_hooks.values():
        st = h.get("hook_style")
        if st and st not in hook_styles:
            hook_styles.append(st)

    hook_spec = {
        "avg_delay_sec": avg_hook_delay,
        "style_pool": hook_styles,
        "per_video": per_video_hooks,
    }

    # -------------------------------------------------------------
    # 자막 (subtitle) 통합
    # -------------------------------------------------------------
    all_sub_durations = [
        float(s.get("avg_subtitle_duration_guess_sec", 0.0))
        for s in per_video_subtitles.values()
    ]
    avg_sub_duration = round(sum(all_sub_durations) / len(all_sub_durations), 2)
    sub_duration_range = [
        round(min(all_sub_durations), 2),
        round(max(all_sub_durations), 2),
    ]

    subtitle_styles = []
    subtitle_tones = []
    for s in per_video_subtitles.values():
        st = s.get("subtitle_style")
        if st and st not in subtitle_styles:
            subtitle_styles.append(st)

        tn = s.get("subtitle_tone")
        if tn and tn not in subtitle_tones:
            subtitle_tones.append(tn)

    subtitle_spec = {
        "avg_duration_sec": avg_sub_duration,
        "duration_range_sec": sub_duration_range,
        "style_pool": subtitle_styles,
        "tone_pool": subtitle_tones,
        "per_video": per_video_subtitles,
    }

    # -------------------------------------------------------------
    # 최종 style_spec 구조체 완성
    # -------------------------------------------------------------
    spec = {
        "source_videos": video_paths,
        "cut_rhythm": cut_rhythm_spec,
        "hook": hook_spec,
        "subtitle": subtitle_spec,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    if errors:
        spec["errors"] = errors

    return spec


def save_style_spec(spec: Dict, out_path: str) -> None:
    """style_spec을 JSON 파일로 저장. out_dir 없으면 생성."""
    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False, indent=2)

    print(f"[+] style_spec 저장 완료: '{out_path}'")


if __name__ == "__main__":
    # Windows 콘솔 유니코드 인코딩 설정
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    test_videos = ["references/ref1.mp4", "references/ref2.mp4"]
    print("[+] style_spec_builder 통합 분석 시작...")
    spec_result = build_style_spec(test_videos)
    save_path = "outputs/style_specs/style_spec.json"
    save_style_spec(spec_result, save_path)

    print("\n[+] 생성된 style_spec.json 요약:")
    print(f"  - 컷 평균: {spec_result['cut_rhythm']['avg_cut_sec']}초")
    print(f"  - 컷 범위: {spec_result['cut_rhythm']['cut_range_sec']}초")
    print(f"  - 훅 평균 지연: {spec_result['hook']['avg_delay_sec']}초")
    print(f"  - 훅 스타일 풀: {spec_result['hook']['style_pool']}")
    print(f"  - 자막 평균 유지: {spec_result['subtitle']['avg_duration_sec']}초")
    print(f"  - 자막 스타일 풀: {spec_result['subtitle']['style_pool']}")
    print(f"  - 자막 톤 풀: {spec_result['subtitle']['tone_pool']}")
