# ai-asset-copilot

개인용 AI 자산운용 비서. 미국주식 장기 자산운용 보조와 한국주식 전략 검증·Paper Trading을 하나의 플랫폼에서 다룬다.

현재 **Phase 1 — Portfolio Foundation** 단계다. 계좌별 Transaction Ledger, Decimal 기반 재생·수동 가격 평가, SQLite 저장을 제공한다. 외부 가격·FX API와 주문 기능은 아직 없다.

## 개발 시작

Python **3.11 이상**을 사용한다. 아래 `python3.11`은 설치된 3.11 이상 Python 명령으로 바꿀 수 있다.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest
```

현재 환경 변수 설정은 필요 없다. `.env.example`은 향후 설정 안내용이며 `.env` 자동 로더는 없다. 기본 정책과 한국 Paper Trading 자금은 `config/`에 선언되어 있고 아직 실행 코드에서 읽지 않는다.

## 문서

- [PROJECT_SPEC.md](PROJECT_SPEC.md): authoritative specification — 요구사항과 개발 기준
- [Architecture](docs/ARCHITECTURE.md): 모듈 책임, 의존성, 데이터·주문 흐름
- [Roadmap](docs/ROADMAP.md): Phase별 구현 범위와 완료 조건

미결정 사항은 PROJECT_SPEC의 Open Decisions에서 관리한다. Ledger 및 SQLite 사용 계약과 한계는 Architecture에 기록했다.
