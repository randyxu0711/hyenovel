"""共用 fixture:在 tmp_path 造一個臨時「專案根」,把確定性層的
module-level ROOT/STORIES 指過去 —— 產品程式碼零改動。

鐵律:測試絕不碰真實的 stories/。
不只因為它 gitignored(CI runner 上根本沒有),更因為拿使用者的創作
當測試資料在任何正經專案都是錯的:不可重現、會漂移、有隱私問題。
"""
import shutil
from pathlib import Path

import pytest

import index
import render
import viz

REPO = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def story(tmp_path, monkeypatch):
    """造 tmp_root/stories/mini/{source.md,analysis.json},把 ROOT/STORIES 指過去。

    回 (slug, base) —— base 即該故事目錄。
    schemas/ 與 viz/ 從 repo 真的複製進來:它們是契約與模板的正本,不是測試資料。
    """
    root = tmp_path / "root"
    (root / "stories").mkdir(parents=True)
    shutil.copytree(REPO / "schemas", root / "schemas")
    shutil.copytree(REPO / "viz", root / "viz")

    base = root / "stories" / "mini"
    shutil.copytree(FIXTURES / "mini", base)

    monkeypatch.setattr(viz, "ROOT", root)
    monkeypatch.setattr(render, "ROOT", root)
    monkeypatch.setattr(index, "ROOT", root)
    monkeypatch.setattr(index, "STORIES", root / "stories")
    return "mini", base


@pytest.fixture
def feedback_json():
    """合 schemas/feedback.schema.json 的極小 feedback(quote 對得上 mini/source.md)。

    schema required:slug / read / key_points / one_line;
    每個 point required:title / quotes(minItems 1)/ body。
    """
    return {
        "slug": "mini",
        "read": "一則關於等待落空的極短篇,用一盞燈承載全部情緒。",
        "strengths": [
            {"title": "燈的用法", "body": "把等待外包給物件,不必說破。",
             "refs": ["k1"], "quotes": ["像在等誰"]}
        ],
        "key_points": [
            {"title": "收尾太快", "body": "關燈之後沒有餘波,情緒還沒落地就斷了。",
             "refs": ["e1"], "quotes": ["他把燈關了。"],
             "question": "關燈之後,他站在黑暗裡多久?"}
        ],
        "minor": ["第二段的逗號可以再收一點。"],
        "one_line": "節制,但收得太急。",
    }
