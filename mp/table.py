"""配图 OCR → 重建表格。

这一步不能省：实测这位作者把补货1/补货2 的卖出价**只放在图里**，
正文完全没写。纯文本抓取会漏掉一半卖点。
"""
import json, subprocess, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
BIN = ROOT / "bin" / "ocr_vision"


def ocr(paths: list[str]) -> list[dict]:
    if not paths:
        return []
    r = subprocess.run([str(BIN), *paths], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ocr_vision 失败: {r.stderr[:300]}")
    return json.loads(r.stdout or "[]")


def rows(lines: list[dict], y_tol: float = 0.06) -> list[list[dict]]:
    """按 y 坐标聚行，行内按 x 排序。Vision 的 y 原点在左下。"""
    out: list[list[dict]] = []
    for ln in sorted(lines, key=lambda r: -r["y"]):
        for row in out:
            if abs(row[0]["y"] - ln["y"]) < y_tol:
                row.append(ln); break
        else:
            out.append([ln])
    return [sorted(r, key=lambda c: c["x"]) for r in out]


def as_table(lines: list[dict]) -> list[list[str]]:
    return [[c["text"].strip() for c in r] for r in rows(lines)]


def low_confidence(lines: list[dict], thr: float = 0.6) -> list[dict]:
    """低置信度单元格——这些必须人工复核，尤其是价格数字。"""
    import re as _re
    return [l for l in lines if l["confidence"] < thr
            and _re.fullmatch(r"[\d.,]+", l["text"].strip())]


def rescue(lines: list[dict], paths: list[str], scale: int = 6) -> tuple[list[dict], list[dict]]:
    """低置信数字单元格自动补救：按 bbox 裁切 → 放大 → 重新 OCR。

    实测把表格里的 `2.4` 从 0.30 救到 1.00。小字号数字在整图里识别率低，
    单独放大后 Vision 的表现完全不同。返回 (修正后的 lines, 仍未解决的)。
    """
    from PIL import Image
    import tempfile, os
    by_name = {pathlib.Path(p).name: p for p in paths}
    fixed, still_weak = list(lines), []

    for ln in low_confidence(lines):
        src = by_name.get(ln["file"])
        if not src:
            still_weak.append(ln); continue
        im = Image.open(src); W, H = im.size
        # Vision 坐标原点在左下且已归一化，转成 PIL 的左上原点像素
        x0 = int(max(0, (ln["x"] - 0.02)) * W); x1 = int(min(1, ln["x"] + ln["w"] + 0.02) * W)
        y0 = int(max(0, (1 - ln["y"] - ln["h"] - 0.02)) * H); y1 = int(min(1, 1 - ln["y"] + 0.02) * H)
        if x1 <= x0 or y1 <= y0:
            still_weak.append(ln); continue
        crop = im.crop((x0, y0, x1, y1))
        crop = crop.resize((crop.width * scale, crop.height * scale), Image.LANCZOS)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            crop.save(f.name); tmp = f.name
        try:
            got = ocr([tmp])
        finally:
            os.unlink(tmp)
        best = max(got, key=lambda g: g["confidence"], default=None)
        if best and best["confidence"] > ln["confidence"]:
            for i, o in enumerate(fixed):
                if o is ln:
                    fixed[i] = {**ln, "text": best["text"].strip(),
                                "confidence": best["confidence"], "rescued": True}
                    break
        else:
            still_weak.append(ln)
    return fixed, still_weak
