"""
간판 텍스트 합성 엔진  v2

v1 대비 개선
  1. 크로마키 경계 프린지(보라 잔상) 제거 강화 — 색상거리 기반 + 페더링
  2. 텍스트 자간(tracking) 지원
  3. 텍스트 입체감 — 드롭섀도우 + 미세 베벨(하이라이트/그림자 엣지)
  4. 야간 장면 자동 감지 → 텍스트 발광(글로우) + 패널 테두리 빛 번짐 추가

설계 원칙은 v1과 동일: 패널 검출(detect_chroma)과 합성 로직 분리,
꺾인 패널은 면마다 원근 변환으로 개별 합성.
"""
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from scipy import ndimage

from detect_chroma import detect_chroma_panel
from fold_split import analyze

import os as _os
_REPO_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
FONTS = {
    "regular": _os.path.join(_REPO_ROOT, "fonts", "NanumGothic-Regular.ttf"),
    "bold": _os.path.join(_REPO_ROOT, "fonts", "NanumGothic-Bold.ttf"),
    "extrabold": _os.path.join(_REPO_ROOT, "fonts", "NanumGothic-ExtraBold.ttf"),
}


# ---------------------------------------------------------------- 색상 유틸
def _hex2rgb(h):
    if isinstance(h, tuple):
        return h
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _luminance(rgb):
    return 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]


def auto_text_color(panel_rgb):
    return (255, 255, 255) if _luminance(panel_rgb) < 140 else (25, 25, 25)


def scene_is_dark(base_arr, mask, sample_margin=40):
    """패널 바깥 주변부의 평균 밝기로 야간 장면 여부 판정."""
    H, W = mask.shape
    ring = ndimage.binary_dilation(mask, iterations=sample_margin) & ~mask
    if ring.sum() < 50:
        return False
    lum = (base_arr[..., 0] * 0.299 + base_arr[..., 1] * 0.587 + base_arr[..., 2] * 0.114)
    return float(lum[ring].mean()) < 95


# ---------------------------------------------------------------- 텍스트 레이어
def _fit_font(text, box_w, box_h, font_path, max_ratio=0.82, tracking=0.0):
    lo, hi, best = 6, max(8, int(box_h * 2)), 6
    while lo <= hi:
        mid = (lo + hi) // 2
        f = ImageFont.truetype(font_path, mid)
        w, h = _measure(f, text, tracking)
        if w <= box_w * max_ratio and h <= box_h * max_ratio:
            best, lo = mid, mid + 1
        else:
            hi = mid - 1
    return ImageFont.truetype(font_path, best)


def _measure(font, text, tracking):
    """자간(tracking, em 대비 비율)을 포함한 텍스트 폭/높이 측정."""
    total_w = 0
    max_asc, max_desc = 0, 0
    for ch in text:
        l, t, r, b = font.getbbox(ch)
        total_w += (r - l)
        max_asc = max(max_asc, -t)
        max_desc = max(max_desc, b)
    total_w += tracking * font.size * max(len(text) - 1, 0)
    return total_w, max_asc + max_desc


def _draw_tracked(d, xy, text, font, fill, tracking):
    x, y = xy
    for ch in text:
        d.text((x, y), ch, font=font, fill=fill)
        l, t, r, b = font.getbbox(ch)
        x += (r - l) + tracking * font.size
    return x


def render_text_layer(size, lines, color, weight="bold", vertical=False,
                      line_gap=0.20, padding=0.10, tracking=0.03,
                      shadow=True, bevel=True):
    """
    패널 크기에 맞춘 투명 텍스트 레이어 생성.
    lines: [(문자열, 상대크기)]
    """
    W, H = size
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    fp = FONTS[weight]
    pad_w, pad_h = W * padding, H * padding
    inner_w, inner_h = W - 2 * pad_w, H - 2 * pad_h

    glyph_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(glyph_layer)
    placements = []  # (text, font, x, y) 기록 → 섀도우/베벨에 재사용

    if vertical:
        text = lines[0][0]
        n = max(len(text), 1)
        cell_h = inner_h / n
        f = _fit_font("가", inner_w, cell_h, fp, max_ratio=0.86)
        for i, ch in enumerate(text):
            l, t, r, b = f.getbbox(ch)
            x = (W - (r - l)) / 2 - l
            y = pad_h + i * cell_h + (cell_h - (b - t)) / 2 - t
            placements.append((ch, f, x, y))
    else:
        total_ratio = sum(r for _, r in lines) + line_gap * (len(lines) - 1)
        unit_h = inner_h / total_ratio
        y = pad_h
        for text, ratio in lines:
            bh = unit_h * ratio
            f = _fit_font(text, inner_w, bh, fp, max_ratio=0.95, tracking=tracking)
            tw, th = _measure(f, text, tracking)
            x = (W - tw) / 2
            l, t, r, b = f.getbbox(text[0]) if text else (0, 0, 0, 0)
            yy = y + (bh - th) / 2 - t
            placements.append((text, f, x, yy))
            y += bh + unit_h * line_gap

    # 1) 드롭섀도우 (입체감)
    if shadow:
        shadow_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        sd = ImageDraw.Draw(shadow_layer)
        off = max(1, int(H * 0.012))
        for text, f, x, y in placements:
            _draw_tracked(sd, (x + off, y + off * 1.4), text, f, (0, 0, 0, 150), tracking)
        shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(max(1, H * 0.006)))
        layer = Image.alpha_composite(layer, shadow_layer)

    # 2) 베벨(위쪽 하이라이트) — 살짝 입체 느낌
    if bevel:
        hi_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        hd = ImageDraw.Draw(hi_layer)
        for text, f, x, y in placements:
            _draw_tracked(hd, (x, y - max(1, int(H * 0.006))), text, f, (255, 255, 255, 90), tracking)
        layer = Image.alpha_composite(layer, hi_layer)

    # 3) 실제 글자
    for text, f, x, y in placements:
        _draw_tracked(d, (x, y), text, f, color, tracking)
    layer = Image.alpha_composite(layer, glyph_layer)

    return layer, placements


def add_glow(layer, size, color, strength=1.0):
    """야간용 발광 효과: 글자 주변에 색이 번지는 블룸을 추가."""
    W, H = size
    alpha = layer.split()[-1]
    glow_src = Image.new("RGBA", (W, H), color + (0,))
    glow_src.putalpha(alpha)
    blur_r = max(2, int(H * 0.045 * strength))
    glow = glow_src.filter(ImageFilter.GaussianBlur(blur_r))
    # 글로우 강도 조절
    g = np.asarray(glow).astype(float)
    g[..., 3] = np.clip(g[..., 3] * (1.6 * strength), 0, 255)
    glow = Image.fromarray(g.astype(np.uint8))
    out = Image.alpha_composite(glow, layer)
    return out


# ---------------------------------------------------------------- 원근 변환
def _perspective_coeffs(dst_quad, src_size):
    w, h = src_size
    src = [(0, 0), (w, 0), (w, h), (0, h)]
    A, B = [], []
    for (dx, dy), (sx, sy) in zip(dst_quad, src):
        A.append([dx, dy, 1, 0, 0, 0, -sx * dx, -sx * dy])
        A.append([0, 0, 0, dx, dy, 1, -sy * dx, -sy * dy])
        B += [sx, sy]
    res = np.linalg.lstsq(np.array(A, float), np.array(B, float), rcond=None)[0]
    return res.tolist()


def _warp_onto(base_size, layer, quad):
    coeffs = _perspective_coeffs(quad, layer.size)
    return layer.transform(base_size, Image.PERSPECTIVE, coeffs,
                           resample=Image.BICUBIC)


# ---------------------------------------------------------------- 크로마키 정리 (강화판)
def clean_chroma_fringe(arr, mask, panel_rgb, feather_px=3, ring_px=8):
    """
    패널 경계의 보라/마젠타 프린지를 제거.
    v1: 얕은 dilation + 단순 임계값 → 얇은 잔상 라인을 놓침.
    v2: 더 넓은 링 + 마젠타 색상거리 기반 검출 + 알파 페더링으로 자연스럽게 블렌딩.
    """
    a = arr.astype(float)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]

    # 마젠타(255,0,255) 방향으로의 색상 유사도 (거리 기반, 임계값 하나로 안 놓치게)
    magenta_dist = np.sqrt((r - 255) ** 2 + g ** 2 + (b - 255) ** 2)
    magenta_like = magenta_dist < 260  # 어두워진 잔상까지 폭넓게 포함

    ring = ndimage.binary_dilation(mask, iterations=ring_px) & ~mask
    suspect = ring & magenta_like
    if not suspect.any():
        return arr

    # suspect 영역을 '주변 비-마젠타 픽셀'의 색으로 채움 (인페인팅 근사: 최근접 비-마젠타 값 전파)
    clean_ref = ~magenta_like
    idx = ndimage.distance_transform_edt(~clean_ref, return_distances=False, return_indices=True)
    filled = a[idx[0], idx[1]]

    # suspect 경계를 부드럽게 페더링
    dist_in = ndimage.distance_transform_edt(suspect)
    alpha = np.clip(dist_in / max(feather_px, 1), 0, 1)
    alpha3 = alpha[..., None]
    a = np.where(suspect[..., None], filled * alpha3 + a * (1 - alpha3), a)

    return a.astype(np.uint8)


# ---------------------------------------------------------------- 메인
def compose(path, texts, panel_color="#2B2B2B", text_color=None,
            weight="bold", vertical=False, out_path=None,
            tracking=0.03, night_glow="auto", debug=False):
    """
    texts: 면별 텍스트. [[("병원명",1.0), ("ENG",0.42)], ...]
    night_glow: True/False/"auto" — auto면 주변 밝기로 야간 여부 자동 판정
    """
    det = detect_chroma_panel(path)
    if det is None:
        raise RuntimeError(f"크로마키 패널을 찾지 못함: {path}")
    geo = analyze(det["mask"])
    if geo is None:
        raise RuntimeError(f"패널 형상 분석 실패: {path}")

    base = Image.open(path).convert("RGB")
    arr = np.asarray(base).copy()
    mask = det["mask"]

    pc = _hex2rgb(panel_color)
    is_dark_scene = scene_is_dark(arr, mask) if night_glow == "auto" else bool(night_glow)

    # 1) 마스크를 살짝 확장해서 안티에일리어싱 경계(마젠타-배경 블렌드 픽셀)까지
    #    통째로 채움 영역에 포함시킨다 — 프린지 잔상의 근본 원인 제거
    fill_mask = ndimage.binary_dilation(mask, iterations=2)
    arr[fill_mask] = pc
    # 2) 그래도 남을 수 있는 미세 잔상을 한 번 더 정리
    arr = clean_chroma_fringe(arr, fill_mask, pc, ring_px=3)

    composed = Image.fromarray(arr).convert("RGBA")

    faces = geo["faces"]
    if len(texts) != len(faces):
        if len(texts) == 1:
            texts = texts * len(faces)
        else:
            raise ValueError(f"면 {len(faces)}개인데 텍스트는 {len(texts)}세트")

    tc = _hex2rgb(text_color) if text_color else auto_text_color(pc)

    for quad, lines in zip(faces, texts):
        xs = [p[0] for p in quad]; ys = [p[1] for p in quad]
        w = max(int(max(xs) - min(xs)), 10)
        h = max(int(max(ys) - min(ys)), 10)

        layer, _ = render_text_layer((w, h), lines, tc + (255,),
                                     weight=weight, vertical=vertical, tracking=tracking)
        if is_dark_scene:
            layer = add_glow(layer, (w, h), tc, strength=1.0)

        warped = _warp_onto(base.size, layer, quad)
        composed = Image.alpha_composite(composed, warped)

    # 3) 야간 장면이면 패널 테두리에 은은한 빛 번짐 추가 (LED 백라이트 느낌)
    if is_dark_scene:
        glow_mask = Image.fromarray((mask * 255).astype(np.uint8)).filter(
            ImageFilter.GaussianBlur(max(4, int(min(base.size) * 0.02))))
        glow_layer = Image.new("RGBA", base.size, pc + (0,))
        gm = np.asarray(glow_mask).astype(float) * 0.35
        glow_layer.putalpha(Image.fromarray(gm.astype(np.uint8)))
        composed = Image.alpha_composite(composed, glow_layer)

    out = composed.convert("RGB")
    if out_path:
        out.save(out_path)
    return out, geo


if __name__ == "__main__":
    import sys
    src = sys.argv[1] if len(sys.argv) > 1 else "chroma/03_channel_sign.png"
    img, geo = compose(src, [[("서울베리굿치과", 1.0), ("SEOUL VERY GOOD DENTAL", 0.34)]],
                       panel_color="#23262B", out_path="out_test.png")
    print("완료:", geo["folded"], len(geo["faces"]), "면")
