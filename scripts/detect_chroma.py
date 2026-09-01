"""
크로마키 패널 검출 모듈

프롬프트로 마젠타(#FF00FF)로 생성된 간판 패널 영역을 색상 매칭으로 검출.
반환값은 '네 꼭짓점 좌표'로 통일 — 추후 B경로(사용자 사진 + 클릭 4점)에서
이 모듈만 교체하면 합성 로직은 그대로 재사용 가능.
"""
import numpy as np
from PIL import Image
from scipy import ndimage


def _rgb_to_hsv(arr):
    a = arr.astype(np.float32) / 255.0
    mx = a.max(axis=2)
    mn = a.min(axis=2)
    diff = mx - mn
    h = np.zeros_like(mx)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    m = (mx == r) & (diff > 0)
    h[m] = (60 * ((g[m] - b[m]) / diff[m])) % 360
    m = (mx == g) & (diff > 0)
    h[m] = (60 * ((b[m] - r[m]) / diff[m]) + 120) % 360
    m = (mx == b) & (diff > 0)
    h[m] = (60 * ((r[m] - g[m]) / diff[m]) + 240) % 360
    s = np.where(mx > 0, diff / np.maximum(mx, 1e-6), 0)
    return h, s, mx


def detect_chroma_panel(path, hue_center=300.0, hue_tol=30.0,
                        sat_min=0.45, val_min=0.30, min_area_frac=0.002):
    """마젠타 영역을 검출해 패널 정보를 반환. 실패 시 None."""
    im = Image.open(path).convert("RGB")
    W, H = im.size
    arr = np.asarray(im)

    h, s, v = _rgb_to_hsv(arr)
    dh = np.abs(((h - hue_center + 180) % 360) - 180)
    mask = (dh <= hue_tol) & (s >= sat_min) & (v >= val_min)

    # 잔노이즈 제거
    mask = ndimage.binary_opening(mask, np.ones((3, 3)))
    mask = ndimage.binary_closing(mask, np.ones((5, 5)))

    lab, n = ndimage.label(mask)
    if n == 0:
        return None
    sizes = ndimage.sum(mask, lab, range(1, n + 1))
    cid = int(np.argmax(sizes)) + 1
    area = float(sizes[cid - 1])
    if area < W * H * min_area_frac:
        return None

    comp = (lab == cid)
    ys, xs = np.where(comp)
    x0, x1, y0, y1 = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())
    bw, bh = x1 - x0 + 1, y1 - y0 + 1
    fill = area / (bw * bh)

    # 네 꼭짓점 추출 (코너가 꺾인 패널도 대응)
    pts = np.column_stack([xs, ys]).astype(np.float32)
    ssum, sdiff = pts[:, 0] + pts[:, 1], pts[:, 0] - pts[:, 1]
    corners = {
        "tl": pts[np.argmin(ssum)], "br": pts[np.argmax(ssum)],
        "tr": pts[np.argmax(sdiff)], "bl": pts[np.argmin(sdiff)],
    }
    quad = [tuple(int(c) for c in corners[k]) for k in ("tl", "tr", "br", "bl")]

    # 직사각형 이탈도: 실제 마스크가 사각형에서 얼마나 벗어나는지
    rect_dev = 1.0 - fill

    # 마젠타 오염 검사: 패널 밖에 남은 마젠타 픽셀 비율
    outside = mask.copy()
    outside[y0:y1 + 1, x0:x1 + 1] = False
    spill = float(outside.sum()) / max(area, 1)

    return {
        "box": (x0, y0, x1, y1),
        "quad": quad,
        "size": (W, H),
        "area_px": int(area),
        "fill": round(float(fill), 3),
        "rect_deviation": round(float(rect_dev), 3),
        "spill_ratio": round(spill, 4),
        "width_pct": round(bw / W * 100, 1),
        "height_pct": round(bh / H * 100, 1),
        "aspect": round(bw / max(bh, 1), 2),
        "mask": comp,
    }


if __name__ == "__main__":
    import sys, glob, os
    paths = sys.argv[1:] or sorted(glob.glob("chroma/*.png"))
    for i, p in enumerate(paths, 1):
        r = detect_chroma_panel(p)
        name = os.path.basename(p)[:34]
        if r is None:
            print(f"[{i}] {name:36s} 검출 실패")
            continue
        print(f"[{i}] {name:36s} fill={r['fill']:.3f} "
              f"이탈도={r['rect_deviation']:.3f} 오염={r['spill_ratio']:.4f} "
              f"폭{r['width_pct']:5.1f}% 비율{r['aspect']:5.2f}")
        print(f"     꼭짓점 {r['quad']}")
