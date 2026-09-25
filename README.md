# ai-asset-copilot

개인용 AI 자산운용 비서. 주택 구매·노후 준비를 위한 개인 현금흐름·월간 예산과 미국주식 장기투자 보조, 한국주식 전략 검증·Paper Trading을 다룬다. 예산은 **미구현 제품 범위**이며 [BUD-01~04 계획](docs/ROADMAP.md#budget--cashflow-planning-확장)에서 추적한다. 향후 주 화면은 모바일·PC 웹앱, 텔레그램은 제한된 알림·조회이며 초기 실행 환경은 맥미니다. 목표 금액·시점과 개인화 전략은 미정이다.

`main`에는 **Phase 3 — US Portfolio Analytics**까지 구현했다. 계좌 원장과 검증된 가격·FX를 연결하여 미국 USD 계좌의 현재 평가, 직접 Sector 노출, KRW 보고 환산을 계산한다. Phase 4 Policy Engine은 별도 미병합 후보이며 IN REVIEW / NOT DONE이다. 현재 기능은 Python API이고 실제 계좌 자료 입력·대사, 사용자 보고서, 주문, 역사적 성과 분석은 없다.

## 개발 시작

Python **3.11 이상**을 사용한다. 아래 `python3.11`은 설치된 3.11 이상 Python 명령으로 바꿀 수 있다.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest
```

단위 테스트에는 환경 변수가 필요 없다. 실제 Twelve Data adapter를 사용할 때만 `TWELVE_DATA_API_KEY`가 필요하다. `.env` 자동 로더는 없다. 기본 정책과 한국 Paper Trading 자금은 `config/`에 선언되어 있고 `main`의 실행 코드에서는 아직 읽지 않는다. 실제 계좌 자료나 API 키를 저장소에 넣지 않는다.

## BUD-01 오프라인 예산 후보

이 브랜치의 수동 가상 KRW 입력·순수 계산기·보고는 다음 한 명령으로 확인한다.

```bash
.venv/bin/python examples/budget_monthly_offline.py --scenario all
```

`normal`, `cash_gap`, `unknown_goal`, `overspend`, `extra_reservation`, `overdue_salary`, `goal_conflict`을 각각 `--scenario`에 넣어 따로 실행할 수 있다. 입력은 [예제 파일](examples/budget_monthly_offline.py)의 `sample_input()`에서 수정한다. 보고는 월초 원안, 확인된 현금 기준의 현재 여유·부족, 미래 예정 입금을 포함한 예상 여유, 목표 배정 후 날짜별 가용현금을 구분한다. 이 값과 신규 투자 제안은 승인이나 장중 잔고 보장이 아니다. 목표 필요 적립액의 두 자리 표시는 읽기 위한 반올림이며 API의 `Decimal` 결과는 반올림하지 않는다. 은행·카드·Toss, DB 저장, AI, 웹, 송금·주문 연결은 없다. 이 후보는 main 기능이 아니다.

## 문서

- [AGENTS.md](AGENTS.md): 작업·검증·Phase 완료 규칙
- [PROJECT_SPEC.md](PROJECT_SPEC.md): authoritative specification — 요구사항과 개발 기준
- [Architecture](docs/ARCHITECTURE.md): 모듈 책임, 의존성, 데이터·주문 흐름
- [Roadmap](docs/ROADMAP.md): Phase 0–13 범위·완료 조건, 사용자 도달점과 BUD-01~04 범위
- [Status](docs/STATUS.md): main과 후보의 구분, 테스트·CI 증거, Phase 4 미해결 조건

미결정 사항은 PROJECT_SPEC의 Open Decisions에서 관리한다. Ledger 및 SQLite 사용 계약과 한계는 Architecture에 기록했다.
