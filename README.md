# ai-asset-copilot

개인용 AI 자산운용 비서. 미국주식 장기 자산운용 보조와 한국주식 전략 검증·Paper Trading을 하나의 플랫폼에서 다룬다.

현재 **Phase 3 — US Portfolio Analytics**까지 구현했다. 계좌 원장과 검증된 가격·FX를 연결하여 미국 USD 계좌의 현재 평가, 직접 Sector 노출, KRW 보고 환산을 계산한다. 주문 기능과 역사적 성과 분석은 없다.

## 개발 시작

Python **3.11 이상**을 사용한다. 아래 `python3.11`은 설치된 3.11 이상 Python 명령으로 바꿀 수 있다.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest
```

단위 테스트에는 환경 변수가 필요 없다. 실제 Twelve Data adapter를 사용할 때만 `TWELVE_DATA_API_KEY`가 필요하다. `.env` 자동 로더는 없다. 기본 정책과 한국 Paper Trading 자금은 `config/`에 선언되어 있고 아직 실행 코드에서 읽지 않는다.

## 문서

- [PROJECT_SPEC.md](PROJECT_SPEC.md): authoritative specification — 요구사항과 개발 기준
- [Architecture](docs/ARCHITECTURE.md): 모듈 책임, 의존성, 데이터·주문 흐름
- [Roadmap](docs/ROADMAP.md): Phase별 구현 범위와 완료 조건

미결정 사항은 PROJECT_SPEC의 Open Decisions에서 관리한다. Ledger 및 SQLite 사용 계약과 한계는 Architecture에 기록했다.
