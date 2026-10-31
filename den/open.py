"""python -m den.open:確保 den 在跑,換一張一次性啟動碼,用預設瀏覽器開 dashboard。

url 一律印出來:開不了瀏覽器(WSL 常見)時讓人自己點。啟動碼單次有效、120 秒內要用。
"""
import webbrowser

from den.client import DenClient
from marrow import db


def main(argv: list[str] | None = None) -> None:
    client, token = DenClient(db.data_dir()).ensure()
    r = client.post("/api/launch", headers={"Authorization": f"Bearer {token}"})
    r.raise_for_status()
    url = r.json()["url"]
    print(url, flush=True)
    webbrowser.open(url)


if __name__ == "__main__":
    main()
