from pathlib import Path
import os

import openai
import streamlit as st
from dotenv import dotenv_values

MAX_CHARS = 5000
DEFAULT_MODEL = "gpt-6-astra"
ENV_PATH = Path(__file__).with_name(".env")

# 한국어 이름 → (모델에 전달할 언어명, 버튼에 함께 표시할 현지어 이름).
# 국기 이모지는 Windows에서 "US"처럼 글자로 깨져 보이므로 쓰지 않음.
# 언어를 추가하려면 여기에 항목만 추가.
LANGUAGES = {
    "영어": ("English", "English"),
    "일본어": ("Japanese", "日本語"),
    "베트남어": ("Vietnamese", "Tiếng Việt"),
}

SYSTEM_PROMPT = (
    "You are a professional translator. Translate the user's text into {target_language}. "
    "Preserve the original meaning, tone, line breaks, and formatting. "
    "Output only the translated text without any explanation."
)


class TranslationError(Exception):
    """사용자에게 그대로 보여줄 한국어 메시지를 담는 예외."""


def load_config():
    # 매 실행마다 .env를 다시 읽어 서버 재시작 없이 설정 변경이 반영되게 함
    values = dotenv_values(ENV_PATH) if ENV_PATH.exists() else {}
    api_key = (values.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()
    model = (values.get("OPENAI_MODEL") or os.getenv("OPENAI_MODEL") or DEFAULT_MODEL).strip()
    return api_key, model


def translate(text, target_language, api_key, model):
    client = openai.OpenAI(api_key=api_key, timeout=60, max_retries=1)
    try:
        response = client.chat.completions.create(
            # gpt-6-astra는 temperature 기본값(1)만 지원하므로 지정하지 않음
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT.format(target_language=target_language)},
                {"role": "user", "content": text},
            ],
        )
    except openai.AuthenticationError:
        raise TranslationError("API 키 인증에 실패했습니다. .env의 OPENAI_API_KEY 값이 올바른지 확인하세요.")
    except openai.PermissionDeniedError:
        raise TranslationError(f"이 API 키로는 '{model}' 모델을 사용할 권한이 없습니다.")
    except openai.NotFoundError:
        raise TranslationError(f"'{model}' 모델을 찾을 수 없습니다. .env의 OPENAI_MODEL 값을 확인하세요.")
    except openai.RateLimitError:
        raise TranslationError("요청 한도를 초과했거나 크레딧이 부족합니다. 잠시 후 다시 시도하세요.")
    except openai.APITimeoutError:
        raise TranslationError("응답 시간이 초과되었습니다. 잠시 후 다시 시도하세요.")
    except openai.APIConnectionError:
        raise TranslationError("OpenAI 서버에 연결할 수 없습니다. 네트워크 연결을 확인하세요.")
    except openai.BadRequestError:
        raise TranslationError(f"요청이 거부되었습니다. 모델명('{model}')과 입력 내용을 확인하세요.")
    except openai.APIError:
        raise TranslationError("OpenAI 서버에서 오류가 발생했습니다. 잠시 후 다시 시도하세요.")

    result = (response.choices[0].message.content or "").strip() if response.choices else ""
    if not result:
        raise TranslationError("번역 결과가 비어 있습니다. 다시 시도하세요.")
    return result


def request_translation(label):
    """버튼 on_click 콜백. 입력을 검사하고, 통과하면 번역 요청을 예약한다."""
    text = st.session_state.get("source_text", "")
    if not text.strip():
        st.session_state["notice"] = ("warning", "번역할 글을 입력하세요.")
    elif len(text) > MAX_CHARS:
        st.session_state["notice"] = (
            "warning",
            f"글이 너무 깁니다. {MAX_CHARS:,}자 이하로 줄여주세요. (현재 {len(text):,}자)",
        )
    else:
        st.session_state["pending"] = label


def run_pending_translation(label, api_key, model):
    # Streamlit은 실행 중 새 조작이 들어오면 실행을 중단하므로,
    # 번역 중에는 입력창·버튼을 비활성화한 화면을 먼저 그린 뒤 이 함수를 호출한다.
    # 예약은 먼저 지워서, 실행이 중단되더라도 같은 번역이 반복 요청되지 않게 한다.
    del st.session_state["pending"]
    text = st.session_state.get("source_text", "")
    with st.spinner("번역 중..."):
        try:
            result = translate(text, LANGUAGES[label][0], api_key, model)
            st.session_state["result"] = {"label": label, "text": result, "source": text}
        except TranslationError as e:
            st.session_state["notice"] = ("error", str(e))
    st.rerun()  # 입력창·버튼을 다시 활성화한 화면으로 갱신


CSS = """
<style>
h1 { word-break: keep-all; }
.char-count { text-align: right; font-size: 0.85rem; opacity: 0.65; margin-top: -0.5rem; }
.char-count.over { color: #e5484d; opacity: 1; font-weight: 600; }
.empty-result { text-align: center; opacity: 0.6; padding: 1.5rem 0; }
</style>
"""


def render_sidebar(model):
    with st.sidebar:
        st.header("ℹ️ 정보")
        st.markdown(f"**사용 모델**  \n`{model}`")
        st.divider()
        st.markdown(
            "**사용 방법**\n"
            "1. 번역할 글을 입력합니다.\n"
            "2. 원하는 언어 버튼을 누릅니다.\n"
            "3. 결과 오른쪽 위 복사 버튼으로 결과를 복사합니다."
        )
        st.caption("원문 언어는 자동으로 감지됩니다.")


def render_result():
    result = st.session_state.get("result")
    st.markdown("#### 번역 결과" + (f" ({result['label']})" if result else ""))
    if result and result["source"] != st.session_state.get("source_text", ""):
        st.info("원문이 바뀌었습니다. 아래는 이전 원문의 번역입니다. 다시 번역하려면 언어 버튼을 누르세요.")
    with st.container(border=True):
        if result:
            st.code(result["text"], language=None, wrap_lines=True)
        else:
            st.markdown(
                '<div class="empty-result">언어 버튼을 누르면 이곳에 번역 결과가 표시됩니다.</div>',
                unsafe_allow_html=True,
            )


def main():
    st.set_page_config(page_title="다국어 번역기", page_icon="🌐", layout="centered")
    st.markdown(CSS, unsafe_allow_html=True)

    api_key, model = load_config()
    render_sidebar(model)

    st.title("🌐 다국어 번역기")
    st.caption("글을 입력하고 번역할 언어 버튼을 누르세요. 영어 · 일본어 · 베트남어를 지원합니다.")

    if not api_key:
        st.error(
            "OpenAI API 키가 설정되지 않았습니다. 프로젝트 폴더의 .env 파일에 "
            "`OPENAI_API_KEY=sk-...` 형식으로 키를 입력한 뒤 페이지를 새로고침하세요."
        )

    pending = st.session_state.get("pending") if api_key else None
    busy = pending is not None

    # max_chars를 쓰면 한도를 넘는 붙여넣기가 안내 없이 통째로 무시되므로, 길이 제한은 직접 검사
    st.text_area(
        "번역할 글",
        height=200,
        key="source_text",
        placeholder="번역할 글을 입력하세요...",
        disabled=busy,
    )
    count = len(st.session_state.get("source_text", ""))
    over = " over" if count > MAX_CHARS else ""
    st.markdown(f'<div class="char-count{over}">{count:,} / {MAX_CHARS:,}자</div>', unsafe_allow_html=True)

    cols = st.columns(len(LANGUAGES))
    for col, (label, (_, native)) in zip(cols, LANGUAGES.items()):
        col.button(
            f"{label} · {native}",
            key=f"btn_{label}",
            on_click=request_translation,
            args=(label,),
            disabled=busy or not api_key,
            width="stretch",
            type="primary",
        )

    notice = st.session_state.pop("notice", None)
    if notice:
        getattr(st, notice[0])(notice[1])

    if busy:
        run_pending_translation(pending, api_key, model)

    render_result()


main()
