"""從工人的文字輸出抽出單一 JSON 物件(確定性層)。

工人不再走 CLI 的 --json-schema(那段內部驗證與重試我們看不到);模型把 JSON 當文字吐,
這裡只負責「抽得出一個物件」,合不合格交給閘門。任何失敗回 None,不拋。
"""
import json

_FENCE = "```"


def extract_json(text: str) -> dict | None:
    s = text.strip()
    if s.startswith(_FENCE) and s.endswith(_FENCE):
        s = s[len(_FENCE):-len(_FENCE)]
        if "\n" in s:                       # 去掉 ```json 那行的語言標記
            s = s.split("\n", 1)[1]
    try:
        obj = json.loads(s)
    except ValueError:                      # 全文解析失敗才退而取第一個 { 到最後一個 }
        try:
            obj = json.loads(s[s.find("{"):s.rfind("}") + 1])
        except ValueError:
            return None
    # 全文是合法 JSON 但不是物件(陣列、字串…)就是不對,不去裡面撈
    return obj if isinstance(obj, dict) else None
