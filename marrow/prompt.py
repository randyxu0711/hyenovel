"""單一 prompt 組裝器:分層串接;指令層與素材層的指紋分開,同一套 prompt 換作品指紋不變。"""
from dataclasses import dataclass

from marrow.repo import sha256_text


def _sha(text: str) -> str:
    return sha256_text(text)[:12]


@dataclass(frozen=True)
class Layer:
    name: str
    text: str
    material: bool = False


@dataclass(frozen=True)
class Prompt:
    layers: tuple[Layer, ...]

    @property
    def text(self) -> str:
        return "".join(x.text for x in self.layers)

    def fingerprint(self) -> dict:
        ins = [x for x in self.layers if not x.material]
        return {"instructions": _sha("".join(x.text for x in ins)),
                "layers": {x.name: _sha(x.text) for x in ins},
                "material": {x.name: _sha(x.text) for x in self.layers if x.material}}


def recipe(prompt: Prompt, run: dict) -> dict:
    return {"prompt": prompt.fingerprint(), "run": run}
