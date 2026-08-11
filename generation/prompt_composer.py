"""
Stage 6: 프롬프트 조립기
style_spec.json + 사용자 입력을 결합해 훅/자막 생성용 LLM 프롬프트를
동적으로 만든다. 기존 app.py의 enforce_prompt_by_mode 패턴을 참고하되,
하드코딩된 모드 대신 style_spec 딕셔너리 기반으로 동작하도록 한다.

TODO: compose_hook_prompt(style_spec: dict, user_input: str) -> str
TODO: compose_subtitle_prompt(style_spec: dict, user_input: str) -> str
"""


def compose_hook_prompt(style_spec: dict, user_input: str) -> str:
    pass


def compose_subtitle_prompt(style_spec: dict, user_input: str) -> str:
    pass
