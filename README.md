# shortform-harness

## 1. 프로젝트 개요

`shortform-harness`는 레퍼런스 숏폼 영상 2개를 분석하여 스타일 스펙(JSON)을 추출하고, 추출된 스타일 스펙과 사용자 프롬프트를 결합하여 고품질 숏폼 영상을 자동으로 생성 및 평가하는 CLI 하네스 시스템입니다.

## 2. 설치 방법

프로젝트 루트에서 가상환경을 생성하고 필요한 패키지를 설치합니다.

```bash
# 가상환경 생성 (Python 3.10+ 권장)
python -m venv venv

# 가상환경 활성화 (Windows PowerShell)
.\venv\Scripts\Activate.ps1

# 가상환경 활성화 (Linux/macOS)
source venv/bin/activate

# 의존성 패키지 설치
pip install -r requirements.txt
```

## 3. .env 설정 방법

`.env.example` 파일 복사 후 필요한 API 키를 작성합니다.

```bash
cp .env.example .env
```

`.env` 파일 내용:
```env
GEMINI_API_KEY=your_gemini_api_key_here
REPLICATE_API_TOKEN=your_replicate_api_token_here
ELEVENLABS_API_KEY=your_elevenlabs_api_key_here
```

## 4. 실행 방법

`run_harness.py` CLI 도구를 통해 하네스를 실행합니다.

```bash
# 신규 레퍼런스 영상 분석 및 생성
python run_harness.py --ref references/ref1.mp4 references/ref2.mp4 --input "AI 기술의 미래와 영향" --output outputs/videos

# 기존 스타일 스펙 재사용
python run_harness.py --ref references/ref1.mp4 --input "AI 기술의 미래와 영향" --spec-cache outputs/style_specs/style_spec.json
```

## 5. 폴더 구조 설명

```
shortform-harness/
├── README.md                 # 프로젝트 안내 문서
├── .env.example              # 환경 변수 템플릿
├── .gitignore                # Git 무시 파일 목록
├── requirements.txt          # 프로젝트 의존성 패키지 목록
├── analysis/                 # 영상/오디오 스타일 분석 모듈 (Stage 1~5)
│   ├── __init__.py
│   ├── frame_extractor.py    # Stage 1: 프레임 추출기 (ffmpeg)
│   ├── cut_detector.py       # Stage 2: 컷 전환 감지기 (PySceneDetect)
│   ├── vision_analyzer.py    # Stage 3: Vision LLM 분석기 (Gemini Vision)
│   ├── audio_analyzer.py     # Stage 4: 오디오 분석기 (librosa)
│   └── style_spec_builder.py # Stage 5: 스타일 스펙 통합기 (JSON 생성)
├── generation/               # 영상 생성 및 합성 모듈 (Stage 6~7)
│   ├── __init__.py
│   ├── prompt_composer.py    # Stage 6: 프롬프트 조립기
│   ├── tts.py                # Stage 7-1: TTS 오디오 생성기 (ElevenLabs)
│   ├── image_gen.py          # Stage 7-2: 이미지 생성기 (Replicate)
│   ├── video_gen.py          # Stage 7-3: 비디오 생성기 (Replicate)
│   └── compositor.py         # Stage 7-4: 최종 영상/자막/오디오 합성기
├── evaluation/               # 유사도 평가 및 판단 모듈 (Stage 8)
│   ├── __init__.py
│   └── gate.py               # Stage 8: 자동 판정 Gate
├── run_harness.py            # CLI 실행 진입점
├── outputs/                  # 생성된 결과물 출력 경로
│   ├── style_specs/          # 추출된 style_spec.json 저장 폴더
│   └── videos/               # 최종 생성된 숏폼 mp4 비디오 저장 폴더
└── references/               # 분석 대상 레퍼런스 mp4 비디오 폴더
```

## 6. 사용 API 키 목록 및 발급처

| API Key | 용도 / 주요 기능 | 발급처 URL |
| :--- | :--- | :--- |
| `GEMINI_API_KEY` | Vision LLM 프레임/자막/훅 패턴 분석 | [Google AI Studio](https://aistudio.google.com/apikey) |
| `REPLICATE_API_TOKEN` | 이미지 및 숏폼 비디오 생성 AI 모델 호출 | [Replicate API Tokens](https://replicate.com/account/api-tokens) |
| `ELEVENLABS_API_KEY` | 숏폼 나레이션 Voice/TTS 음성 합성 | [ElevenLabs API Keys](https://elevenlabs.io/app/settings/api-keys) |

## 7. 주요 의존성 패키지 및 스테이지별 사용처

| 패키지명 | 관련 스테이지 | 상세 역할 및 기능 |
| :--- | :--- | :--- |
| `ffmpeg-python` | Stage 1 | 영상 특정 구간 지정 간격 프레임 추출 |
| `requests` | Stage 7 | 외부 API 통신 및 생성 결과 다운로드 |
| `Pillow` | Stage 1 / Stage 3 | 프레임 이미지 읽기/변환 및 이미지 처리 |
| `mutagen` | Stage 4 / Stage 7 | 오디오 파일 메타데이터 분석 및 재생 시간 측정 |
| `scenedetect[opencv]` | Stage 2 | 영상 장면 전환(컷) 타임스탬프 및 컷 길이 감지 |
| `librosa` | Stage 4 | 오디오 RMS (볼륨) 변화 분석 및 BGM 전환점 검출 |
| `soundfile` | Stage 4 | 오디오 파일 I/O 및 파형 데이터 로딩 |
| `google-genai` | Stage 3 / Stage 6 | Gemini Vision 기반 visual 패턴 분석 및 구조화 JSON 출력 |
| `anthropic` | Stage 6 | Claude LLM 기반 프롬프트 조립 및 생성 |
| `python-dotenv` | 공통 | `.env` 파일 환경 변수 로드 |
| `numpy` | Stage 2 / Stage 4 | 수치 계산, 컷 길이 및 오디오 데이터 통계 처리 |

