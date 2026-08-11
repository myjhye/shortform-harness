import argparse
import sys


def main():
    parser = argparse.ArgumentParser(
        description="shortform-harness CLI: 레퍼런스 영상 분석 및 숏폼 영상 생성 파이프라인 하네스"
    )
    parser.add_argument(
        "--ref",
        nargs="+",
        required=True,
        help="레퍼런스 영상 파일 경로 목록 (1개 이상)",
    )
    parser.add_argument(
        "--input",
        required=True,
        help="사용자 입력 프롬프트",
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

    args = parser.parse_args()

    print("[+] shortform-harness 실행 인자:")
    print(f"  - 레퍼런스 영상: {args.ref}")
    print(f"  - 사용자 프롬프트: {args.input}")
    print(f"  - 스펙 캐시 경로: {args.spec_cache}")
    print(f"  - 출력 폴더: {args.output}")

    # TODO: Stage 1~5 분석 실행
    # TODO: Stage 6~7 생성 실행
    # TODO: Stage 8 검증 실행

    print("[+] 준비 단계 완료 (파이프라인 실행 뼈대)")


if __name__ == "__main__":
    main()
