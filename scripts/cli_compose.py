"""
CLI 래퍼 — GitHub Actions에서 이 파일을 직접 호출한다.

사용 예:
  python scripts/cli_compose.py \
      --input inputs/sample.png \
      --output outputs/composed_sample.png \
      --name-kr "서울베리굿치과" \
      --name-en "SEOUL VERY GOOD DENTAL" \
      --panel-color "#23262B" \
      --weight bold
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from compose import compose  # noqa: E402


def parse_night_glow(v):
    if v is None:
        return "auto"
    v = str(v).strip().lower()
    if v in ("auto", ""):
        return "auto"
    return v in ("1", "true", "yes", "y")


def main():
    p = argparse.ArgumentParser(description="크로마키 간판 패널에 한글 텍스트 자동 합성")
    p.add_argument("--input", required=True, help="크로마키 패널이 포함된 원본 이미지 경로")
    p.add_argument("--output", required=True, help="결과 이미지 저장 경로")
    p.add_argument("--name-kr", required=True, help="병원명 (한글)")
    p.add_argument("--name-en", default="", help="영문 부제 (선택)")
    p.add_argument("--panel-color", default="#23262B", help="패널 색상 hex")
    p.add_argument("--text-color", default="", help="글자 색상 hex (비우면 패널 밝기로 자동 결정)")
    p.add_argument("--material", default="matte",
                   choices=["matte", "glossy", "brushed_metal", "fabric"],
                   help="패널 소재")
    p.add_argument("--led-color", default="", help="LED 강조색 hex (비우면 글자색과 동일)")
    p.add_argument("--depth", default="auto", help="두께감 픽셀값, 'auto' 또는 0(끄기) 또는 정수")
    p.add_argument("--weight", default="bold", choices=["regular", "bold", "extrabold"])
    p.add_argument("--vertical", action="store_true", help="세로쓰기 (돌출간판/다닥다닥형용)")
    p.add_argument("--night-glow", default="auto", help="auto / true / false")
    p.add_argument("--tracking", type=float, default=0.03, help="자간 비율 (em 대비)")
    args = p.parse_args()

    if not os.path.exists(args.input):
        print(f"[오류] 입력 파일이 없습니다: {args.input}", file=sys.stderr)
        sys.exit(1)

    lines = [(args.name_kr, 1.0)]
    if args.name_en.strip():
        lines.append((args.name_en.strip(), 0.32))
    texts = [lines]

    os.makedirs(os.path.dirname(os.path.abspath(args.output)) or ".", exist_ok=True)

    depth = args.depth
    if depth != "auto":
        try:
            depth = int(depth)
        except ValueError:
            print(f"[오류] --depth 값이 올바르지 않습니다: {depth}", file=sys.stderr)
            sys.exit(1)

    try:
        img, geo = compose(
            args.input,
            texts,
            panel_color=args.panel_color,
            text_color=(args.text_color or None),
            weight=args.weight,
            vertical=args.vertical,
            tracking=args.tracking,
            night_glow=parse_night_glow(args.night_glow),
            material=args.material,
            led_color=(args.led_color or None),
            depth_px=depth,
            out_path=args.output,
        )
    except Exception as e:
        print(f"[오류] 합성 실패: {e}", file=sys.stderr)
        sys.exit(2)

    print(f"[완료] {'꺾인 패널(' + str(len(geo['faces'])) + '면)' if geo['folded'] else '평면 패널'} "
          f"-> {args.output}")


if __name__ == "__main__":
    main()
