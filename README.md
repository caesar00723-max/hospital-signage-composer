# 병원 간판 이미지 합성 도구

크로마키(마젠타 #FF00FF) 패널이 포함된 생성 이미지에 나눔고딕 한글 병원명을
자동으로 정확하게 합성하는 도구. GitHub Actions로 구동되며, 정적 웹 폼(GitHub Pages)에서
버튼 한 번으로 실행할 수 있다.

## 처리 흐름

```
[Gemini/Grok] 크로마키 프롬프트로 이미지 생성 (수동)
      ↓
[웹 폼] 이미지 업로드 + 병원명 입력 → 저장소에 커밋 + Actions 트리거
      ↓
[GitHub Actions] scripts/cli_compose.py 실행
      ↓
[Artifact] 합성된 최종 이미지 다운로드
```

---

## 1. 저장소 설정 (최초 1회)

1. 이 폴더 전체를 새 GitHub 저장소에 push한다.
   ```bash
   git init
   git add .
   git commit -m "init: hospital signage composer"
   git branch -M main
   git remote add origin https://github.com/<owner>/<repo>.git
   git push -u origin main
   ```
2. 저장소 **Settings → Pages → Build and deployment → Source** 에서 **"GitHub Actions"** 를 선택한다.
   (브랜치/폴더 선택 방식이 아니라 Actions 배포 방식이므로 `web/` 처럼 임의 폴더를 그대로 배포할 수 있다.)
   `main`에 push하면 `.github/workflows/deploy-pages.yml`이 자동으로 `web/` 폴더를 Pages로 배포한다.
3. **Settings → Actions → General → Workflow permissions** 에서
   "Read and write permissions"까지는 필요 없다 (Artifact 업로드만 하므로 기본 read 권한으로 충분).

## 2. 토큰 발급 (최초 1회, 브라우저마다)

GitHub → 우측 상단 프로필 → **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**

| 항목 | 값 |
|---|---|
| Repository access | **Only select repositories** → 이 저장소 하나만 선택 |
| Permissions → Contents | **Read and write** |
| Permissions → Actions | **Read and write** |
| 그 외 권한 | 전부 미부여 |

발급된 토큰은 웹 폼의 "저장소 연결 설정"에 붙여넣고 저장한다. **토큰은 브라우저 localStorage에만 저장되며
저장소나 어떤 서버에도 전송되지 않는다.** 브라우저를 바꾸면 다시 붙여넣어야 한다.

> 토큰이 새어나가도 피해 범위가 이 저장소(Contents/Actions)로 한정되도록 범위를 반드시 좁혀서 발급할 것.

## 3. 사용법

1. `web/index.html`을 GitHub Pages URL로 접속 (또는 로컬에서 그냥 파일로 열어도 동작함 — API 호출은 브라우저에서 직접 나가므로)
2. 크로마키 패널이 포함된 원본 이미지를 업로드
3. 병원명(한글), 영문 부제(선택), 패널 색상, 폰트 굵기, 세로쓰기 여부 입력
4. "간판 합성 실행" 클릭 → 저장소에 이미지 커밋 + Actions 실행 요청 + 완료까지 자동으로 기다림
5. 실행이 끝나면 **같은 화면에 결과 이미지가 바로 표시**되고, 다운로드 버튼으로 저장 가능
   (GitHub 사이트로 이동할 필요 없음. Actions Artifact는 14일 보관되는 백업용으로만 남아있음)

## 4. 로컬 CLI로 직접 실행 (테스트/디버깅용)

```bash
pip install -r requirements.txt
python scripts/cli_compose.py \
  --input inputs/sample.png \
  --output outputs/composed_sample.png \
  --name-kr "서울베리굿치과" \
  --name-en "SEOUL VERY GOOD DENTAL" \
  --panel-color "#23262B" \
  --weight bold
```

옵션 전체:

| 옵션 | 설명 | 기본값 |
|---|---|---|
| `--input` | 크로마키 패널 포함 원본 이미지 | (필수) |
| `--output` | 결과 저장 경로 | (필수) |
| `--name-kr` | 병원명(한글) | (필수) |
| `--name-en` | 영문 부제 | "" |
| `--panel-color` | 패널 색상 hex | `#23262B` |
| `--text-color` | 글자색 hex (비우면 패널 밝기로 자동 결정) | 자동 |
| `--weight` | `regular` / `bold` / `extrabold` | `bold` |
| `--vertical` | 세로쓰기 (돌출간판·다닥다닥형용) | off |
| `--night-glow` | `auto` / `true` / `false` — 야간 발광 효과 | `auto` |
| `--tracking` | 자간 비율 | `0.03` |
| `--material` | `matte` / `glossy` / `brushed_metal` / `fabric` — 패널 소재 | `matte` |
| `--led-color` | LED 강조색 hex (비우면 글자색과 동일) | (글자색과 동일) |
| `--depth` | 두께감 픽셀값. `auto`(패널 높이의 5%) / `0`(끄기) / 정수 | `auto` |

### 소재 옵션 설명

| 소재 | 특징 |
|---|---|
| `matte` | 무광 아크릴. 은은한 비네트 + 미세 노이즈. 가장 무난한 기본값 |
| `glossy` | 유광 아크릴. 대각선 하이라이트 스트릭 + 강한 비네트 |
| `brushed_metal` | 헤어라인 브러시드 메탈. 가로결 노이즈 + 따뜻한 베젤톤 |
| `fabric` | 백라이트 패브릭. 아주 부드러운 확산광, 베젤 약함 |

`--led-color`는 패널 배경색과 별개로 **텍스트 발광색·테두리 하이라이트·야간 빛 번짐**에만 적용됩니다.
예: 패널은 어두운 남색인데 LED만 골드로 하고 싶을 때 `--panel-color "#1E2530" --led-color "#F2C14E"`.

`--depth`는 패널 하단에 어두운 측면(옆판)과 부드러운 낙하 그림자를 추가해 벽에서 살짝 떠 있는
박스형 간판의 두께감을 표현합니다. 값이 클수록 더 두꺼워 보입니다.

## 5. 무료 사용량 참고 (GitHub Actions)

- Public 저장소: Actions 실행시간 무제한
- Private 저장소: 월 2,000분 무료 (합성 1건당 약 30초~1분 → 하루 10건이면 월 300분 내외로 넉넉함)

## 6. 폴더 구조

```
scripts/
  detect_chroma.py   # 크로마키 영역 검출 (HSV 색상 매칭)
  fold_split.py       # 꺾인(코너 랩핑) 패널 자동 분할
  compose.py           # 텍스트 합성 엔진 (그림자/베벨/자간/야간 글로우)
  cli_compose.py       # CLI 진입점 — Actions가 이 파일을 호출
fonts/                 # 나눔고딕 3종 (OFL 라이선스)
web/                    # GitHub Pages 정적 폼
.github/workflows/
  compose-signage.yml  # workflow_dispatch — 웹 폼이 트리거
inputs/                 # 웹 폼이 원본 이미지를 커밋하는 위치
outputs/                # 로컬 테스트용 (Actions 결과물은 Artifact로 별도 관리)
```

## 7. B안이 번거로워질 경우 — A안(수동 트리거)으로 전환

웹 폼 없이도 저장소의 **Actions 탭 → Compose Signage → Run workflow** 버튼을 눌러
같은 입력 필드를 직접 채워 넣고 실행할 수 있다. 다만 이 경우 이미지 파일을 미리
`inputs/` 폴더에 커밋해둬야 한다(웹 폼의 ②단계를 GitHub 웹 UI의 파일 업로드로 대체).
