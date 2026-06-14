# 🤖 Robot Intelligence Daily (RID)

로봇/Physical AI 업계 글로벌 뉴스 자동 수집·분석·대시보드

## 기능

- **Global Top 10** — 전 세계 로봇 뉴스 티어 가중치 스코어링
- **지역별 Top 10** — 한국 / 미국 / 중국 독립 집계 + Regional Delta
- **Weak Signal 탐지** — 30일 평균 대비 언급량 급등 기업 조기 포착
- **Narrative Shift** — 업계 담론 프레이밍 변화 추적
- **Geopolitical Signal** — KR/US/CN 정책·규제 동향
- **전시회 캘린더** — 글로벌 로봇 전시회·컨퍼런스 정보
- **PDF 생성** — Intelligence Brief / Top 10 / 지역별 / 전체 리포트
- **파일링** — 북마크 + 태그 + 보고서 export
- **중복 제거** — 유사도 기반 자동 dedup

## 세팅 순서

### 1. GitHub Repository 생성

```
GitHub → New repository
이름: robot-intelligence-daily
Public (GitHub Pages 무료 사용)
README 체크하지 말고 생성
```

### 2. 파일 업로드

이 폴더 전체를 repo에 업로드:
```
robot-intelligence-daily/
├── index.html
├── requirements.txt
├── data/
│   └── news.json        (초기 빈 파일)
├── scripts/
│   ├── fetch.py
│   ├── analyze.py
│   ├── exhibitions.py
│   └── keywords.yml
└── .github/
    └── workflows/
        └── daily.yml
```

**방법 1 — GitHub 웹 업로드:**
```
repo → Add file → Upload files → 드래그앤드롭
```

**방법 2 — git 명령어:**
```bash
git clone https://github.com/{username}/robot-intelligence-daily
cp -r * robot-intelligence-daily/
cd robot-intelligence-daily
git add .
git commit -m "Initial commit"
git push
```

### 3. GitHub Pages 활성화

```
repo → Settings → Pages
Source: Deploy from a branch
Branch: main / (root)
Save
```

URL: `https://{username}.github.io/robot-intelligence-daily`

### 4. Anthropic API Key 등록

```
repo → Settings → Secrets and variables → Actions
→ New repository secret
Name: ANTHROPIC_API_KEY
Secret: sk-ant-...
```

### 5. 첫 실행 (수동)

```
repo → Actions 탭
→ "Robot Intelligence Daily" 워크플로우
→ "Run workflow" 버튼
→ Run workflow 클릭
```

약 2~3분 후 data/news.json이 업데이트되고 대시보드에 실제 데이터가 표시됩니다.

### 6. 자동 실행 확인

매일 KST 07:00 (UTC 22:00)에 자동 실행됩니다.
Actions 탭에서 실행 로그 확인 가능.

## 비용

| 항목 | 비용 |
|------|------|
| GitHub (public repo + Pages + Actions) | **무료** |
| Claude API (하루 ~300건 분석) | **$0.3~0.5/일** |
| RSS 뉴스 소스 | **무료** |
| **월 합계** | **약 $10~15** |

## 키워드/소스 수정

`scripts/keywords.yml` 파일에서:
- 티어별 기업/키워드 추가·삭제
- RSS 소스 URL 변경
- 중복 제거 임계값 조정

## 로컬 테스트

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
python scripts/fetch.py
python scripts/analyze.py
python scripts/exhibitions.py
# data/news.json 확인
```
