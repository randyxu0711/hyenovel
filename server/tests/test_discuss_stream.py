"""討論串流:哪一類 delta 送得到前端 —— 這是我們的政策,不是 SDK 的行為。
跑法(repo 根):  server/.venv/bin/python -m pytest server/tests/test_discuss_stream.py

背景:`thinking` 預設是 adaptive(開著),但舊的抽取器只認 `text_delta`,
其餘一律丟掉 → 使用者盯著一個 `…` 等,後端其實一直在生 token(實測單輪
產出的 token 有 63–87% 從沒到過畫面)。這組測試釘住「哪些看得到、哪些不該看到」。

2026-07-27 起討論**關掉** thinking(見 `discuss_options`),抽取器的 thinking 分支因此休眠
——測試留著:那是可逆的實驗,翻回來時這些性質要立刻有人守。
"""
from types import SimpleNamespace

from server import sdk_runner


def ev(delta: dict, kind: str = "content_block_delta"):
    return SimpleNamespace(event={"type": kind, "delta": delta})


def test_text_delta_是回答():
    assert sdk_runner.delta_of(ev({"type": "text_delta", "text": "他把燈關了"})) == ("text", "他把燈關了")


def test_thinking_delta_是思考且取的是_thinking_欄不是_text():
    """wire 上 thinking_delta 的內容在 `thinking` 欄。
    照著 text_delta 的形狀去讀 `text` 會靜靜地拿到空字串 —— 功能看起來接好了、畫面永遠空白。"""
    assert sdk_runner.delta_of(ev({"type": "thinking_delta", "thinking": "先確認 m2 在原文出現幾次"})) \
        == ("thinking", "先確認 m2 在原文出現幾次")


def test_signature_delta_不外流():
    """簽章是 base64 雜訊,不是人看的東西;漏出去會在討論框裡糊一大片。"""
    assert sdk_runner.delta_of(ev({"type": "signature_delta", "signature": "AbCd=="})) is None


def test_空字串當作沒有():
    assert sdk_runner.delta_of(ev({"type": "text_delta", "text": ""})) is None
    assert sdk_runner.delta_of(ev({"type": "thinking_delta", "thinking": ""})) is None


def test_非_content_block_delta_一律略過():
    assert sdk_runner.delta_of(ev({"type": "text_delta", "text": "x"}, kind="message_start")) is None


def test_討論關掉_thinking_但保留串流():
    """「討論要不要想」是我們的政策(要來回節奏,深思是 criticizer 的活),不是 SDK 的預設。
    預設 adaptive 會開著,所以這是**主動關**,拿掉就悄悄回到開著 —— 值得一根釘子。
    同一支測試也釘住 `include_partial_messages`:關 thinking 不該連帶把逐 token 串流關掉。"""
    opts = sdk_runner.discuss_options()
    assert opts.thinking == {"type": "disabled"}
    assert opts.include_partial_messages is True


def test_形狀不對不炸():
    """串流事件的形狀是 SDK 那邊的事,我們只保證不因此掛掉整輪討論。"""
    assert sdk_runner.delta_of(SimpleNamespace()) is None
    assert sdk_runner.delta_of(SimpleNamespace(event=None)) is None
    assert sdk_runner.delta_of(SimpleNamespace(event="not-a-dict")) is None
    assert sdk_runner.delta_of(ev({})) is None


def test_tool_use_is_logged(caplog):
    """討論模型讀了哪些檔要留痕 —— 擋不住,至少看得見。"""
    from claude_agent_sdk import ToolUseBlock

    from server import discuss

    blocks = [ToolUseBlock(id="x", name="Read",
                           input={"file_path": "/p/stories/s03/analysis.json"})]
    with caplog.at_level("INFO", logger="hyenovel"):
        discuss._log_reads("s07", blocks)
    assert "event=discuss-read" in caplog.text
    assert "s03/analysis.json" in caplog.text


def test_non_read_tools_are_not_logged(caplog):
    from claude_agent_sdk import ToolUseBlock

    from server import discuss

    with caplog.at_level("INFO", logger="hyenovel"):
        discuss._log_reads("s07", [ToolUseBlock(id="x", name="Grep", input={})])
    assert "event=discuss-read" not in caplog.text
