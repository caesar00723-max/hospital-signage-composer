"""
꺾인(코너 랩핑) 패널의 접힘선 검출 및 면 분할  v2

v1은 경계선 기울기 변화(2차 미분)로 접힘점을 찾았으나
끝단의 튀는 픽셀에 취약해 접힘점과 꼭짓점이 모두 어긋났다.

v2는 '분할 선형회귀'를 사용한다.
  - 후보 접힘 x마다 상/하 경계선을 좌·우 두 직선으로 나눠 피팅
  - 잔차 합이 최소인 x를 접힘점으로 채택
  - 단일 직선 피팅 잔차와 비교해 개선폭이 작으면 '평면'으로 판정
  - 꼭짓점은 개별 픽셀이 아니라 '피팅된 직선 위의 값'으로 산출 → 노이즈 무관

반환 형식은 사변형 리스트 — 평면이면 1개, 꺾이면 2개.
"""
import numpy as np


def _edges(mask):
    W = mask.shape[1]
    xs, top, bot = [], [], []
    for x in range(W):
        col = np.where(mask[:, x])[0]
        if col.size:
            xs.append(x); top.append(col.min()); bot.append(col.max())
    return np.array(xs), np.array(top, float), np.array(bot, float)


def _fit(x, y):
    """1차 직선 피팅 → (기울기, 절편, 잔차제곱합)"""
    if len(x) < 3:
        return 0.0, 0.0, np.inf
    A = np.vstack([x, np.ones_like(x, dtype=float)]).T
    sol, *_ = np.linalg.lstsq(A, y, rcond=None)
    m, c = float(sol[0]), float(sol[1])
    resid = float(np.sum((y - (m * np.asarray(x, float) + c)) ** 2))
    return m, c, resid


def analyze(mask, min_gain=0.35, min_angle_deg=3.0, margin_frac=0.12):
    """접힘 여부와 면(사변형) 목록을 반환."""
    xs, top, bot = _edges(mask)
    if xs.size < 40:
        return None
    x0, x1 = int(xs.min()), int(xs.max())

    _, _, r_top1 = _fit(xs, top)
    _, _, r_bot1 = _fit(xs, bot)
    base = r_top1 + r_bot1

    m = max(int(xs.size * margin_frac), 10)
    best = None
    for i in range(m, xs.size - m):
        _, _, ra_t = _fit(xs[:i], top[:i]); _, _, rb_t = _fit(xs[i:], top[i:])
        _, _, ra_b = _fit(xs[:i], bot[:i]); _, _, rb_b = _fit(xs[i:], bot[i:])
        tot = ra_t + rb_t + ra_b + rb_b
        if best is None or tot < best[0]:
            best = (tot, i)
    if best is None:
        return None

    tot, idx = best
    gain = (base - tot) / max(base, 1e-9)
    fold_x = int(xs[idx])

    mt_a, ct_a, _ = _fit(xs[:idx], top[:idx]); mt_b, ct_b, _ = _fit(xs[idx:], top[idx:])
    mb_a, cb_a, _ = _fit(xs[:idx], bot[:idx]); mb_b, cb_b, _ = _fit(xs[idx:], bot[idx:])

    sa, sb = (mt_a + mb_a) / 2, (mt_b + mb_b) / 2
    angle = float(np.degrees(abs(np.arctan(sa) - np.arctan(sb))))
    folded = (gain >= min_gain) and (angle >= min_angle_deg)

    def line_quad(xl, xr, mt, ct, mb, cb):
        return [(int(xl), int(round(mt * xl + ct))),
                (int(xr), int(round(mt * xr + ct))),
                (int(xr), int(round(mb * xr + cb))),
                (int(xl), int(round(mb * xl + cb)))]

    if folded:
        faces = [line_quad(x0, fold_x, mt_a, ct_a, mb_a, cb_a),
                 line_quad(fold_x, x1, mt_b, ct_b, mb_b, cb_b)]
    else:
        mt, ct, _ = _fit(xs, top)
        mb, cb, _ = _fit(xs, bot)
        faces = [line_quad(x0, x1, mt, ct, mb, cb)]

    return {"folded": bool(folded), "faces": faces,
            "fold_x": fold_x if folded else None,
            "angle_deg": round(angle, 2),
            "gain": round(float(gain), 3),
            "x_range": (x0, x1)}


if __name__ == "__main__":
    import sys, glob, os
    from detect_chroma import detect_chroma_panel
    paths = sys.argv[1:] or sorted(glob.glob("chroma/*.png"))
    for p in paths:
        r = detect_chroma_panel(p)
        name = os.path.basename(p)
        if r is None:
            print(f"{name}: 패널 검출 실패"); continue
        a = analyze(r["mask"])
        if a is None:
            print(f"{name}: 분석 실패"); continue
        if a["folded"]:
            print(f"{name}: 꺾임 — 접힘 x={a['fold_x']}, 각도={a['angle_deg']}°, "
                  f"개선율={a['gain']:.3f}, 면 {len(a['faces'])}개")
        else:
            print(f"{name}: 평면 — 각도={a['angle_deg']}°, 개선율={a['gain']:.3f}")
        for i, q in enumerate(a["faces"], 1):
            print(f"   면{i} {q}")
