# ai-asset-copilot

개인용 AI 자산운용 비서. 주택 구매·노후 준비를 위한 개인 현금흐름·월간 예산과 미국주식 장기투자 보조, 한국주식 전략 검증·Paper Trading을 다룬다. BUD-01 오프라인 계산기는 main에 반영됐고 BUD-02~04는 계획 단계이며 [BUD-01~04 계획](docs/ROADMAP.md#budget--cashflow-planning-확장)에서 추적한다. 향후 주 화면은 모바일·PC 웹앱, 텔레그램은 제한된 알림·조회이며 초기 실행 환경은 맥미니다. 목표 금액·시점과 개인화 전략은 미정이다.

`main`에는 **Phase 3 — US Portfolio Analytics**까지 구현했다. 계좌 원장과 검증된 가격·FX를 연결하여 미국 USD 계좌의 현재 평가, 직접 Sector 노출, KRW 보고 환산을 계산한다. Phase 4 Policy Engine은 별도 미병합 후보이며 IN REVIEW / NOT DONE이다. 현재 투자 기능은 Python API이고 BUD-01은 로컬 예제 명령과 WEB-01 루프백 미리보기로 실행한다. 실제 계좌 자료 입력·대사, 운영 사용자 보고서, 주문, 역사적 성과 분석은 없다.

## 개발 시작

Python **3.11 이상**을 사용한다. 아래 `python3.11`은 설치된 3.11 이상 Python 명령으로 바꿀 수 있다.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest
```

단위 테스트에는 환경 변수가 필요 없다. 실제 Twelve Data adapter를 사용할 때만 `TWELVE_DATA_API_KEY`가 필요하다. `.env` 자동 로더는 없다. 기본 정책과 한국 Paper Trading 자금은 `config/`에 선언되어 있고 `main`의 실행 코드에서는 아직 읽지 않는다. 실제 계좌 자료나 API 키를 저장소에 넣지 않는다.

## BUD-01 오프라인 예산 계산기

main의 수동 가상 KRW 입력·순수 계산기·보고는 다음 한 명령으로 확인한다.

```bash
.venv/bin/python examples/budget_monthly_offline.py --scenario all
```

`normal`, `cash_gap`, `unknown_goal`, `overspend`, `extra_reservation`, `overdue_salary`, `goal_conflict`을 각각 `--scenario`에 넣어 따로 실행할 수 있다. 예제 자료는 [공유 생성 함수](src/asset_copilot/budget/examples.py)의 `sample_input()`을 CLI와 웹이 함께 사용한다. 보고는 월초 원안, 확인된 현금 기준의 현재 여유·부족, 미래 예정 입금을 포함한 예상 여유, 목표 배정 후 날짜별 가용현금을 구분한다. 이 값과 신규 투자 제안은 승인이나 장중 잔고 보장이 아니다. 목표 필요 적립액의 두 자리 표시는 읽기 위한 반올림이며 API의 `Decimal` 결과는 반올림하지 않는다. 은행·카드·Toss, DB 저장, AI, 송금·주문 연결은 없다. 이 오프라인 계산기는 main 기능이다. 실제 계좌·운영 경로는 별도 검증이 필요하다.

## WEB-01 로컬 예산 미리보기

별도 웹 extra를 설치하면 Python 코드를 수정하지 않고 브라우저에서 직접 입력·수정·재계산할 수 있다. 기본 화면의 금융 값은 미설정이다. 예제는 선택할 때만 불러오며 모두 가상 자료다.
목표의 이번 달 배정은 ‘아직 정하지 않음’(계산에 필요한 입력으로 남음), ‘배정 없음 · 0원’(명시적 0원), ‘금액 입력’으로 구분한다. 목표금액과 기한의 빈칸은 미정으로 유지한다.

```bash
python -m pip install -e '.[web]'
asset-copilot-budget-web
# 브라우저에서 http://127.0.0.1:8765/ 접속
# 종료: 실행 터미널에서 Ctrl+C
```

WEB-01은 PR #6의 검토된 head를 일반 merge commit으로 `main`에 채택한 로컬 기능이다. 기본 바인딩은 `127.0.0.1:8765`다. 웹 없이 기존 BUD-01 계산기와 CLI를 쓸 수 있다. 화면과 결과는 **저장되지 않는 미리보기**이고 새로고침하면 직접 입력 화면으로 돌아간다. 인증·원격접속·휴대폰 접속·운영 복구는 제공하지 않는다. 모바일 폭 검증은 화면 배치 검증일 뿐 실제 휴대폰 원격접속 완료가 아니다. 송금·환전·주문이나 개인화 투자 추천도 제공하지 않는다. 병합과 테스트 성공은 운영 배포 승인이 아니다.

웹 회귀 테스트는 `python -m pip install -e '.[web-test]'` 후 `python -m pytest tests/test_budget_web.py`로 실행한다. 브라우저 검증은 `python -m playwright install chromium`으로 Chromium을 설치한 뒤 서버 실행 중 `python tests/browser_budget_web_smoke.py`로 수행한다. 이 검증은 PC/모바일 폭의 실제 브라우저 경로와 [데스크톱](docs/images/budget-web-desktop.png)·[모바일](docs/images/budget-web-mobile.png) 가상 화면 증거를 만든다.

## 문서

- [AGENTS.md](AGENTS.md): 작업·검증·Phase 완료 규칙
- [PROJECT_SPEC.md](PROJECT_SPEC.md): authoritative specification — 요구사항과 개발 기준
- [Architecture](docs/ARCHITECTURE.md): 모듈 책임, 의존성, 데이터·주문 흐름
- [Roadmap](docs/ROADMAP.md): Phase 0–13 범위·완료 조건, 사용자 도달점과 BUD-01~04 범위
- [Status](docs/STATUS.md): main과 후보의 구분, 테스트·CI 증거, Phase 4 미해결 조건

미결정 사항은 PROJECT_SPEC의 Open Decisions에서 관리한다. Ledger 및 SQLite 사용 계약과 한계는 Architecture에 기록했다.
