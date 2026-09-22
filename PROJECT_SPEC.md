# Project Specification

## 1. 문서의 지위와 현재 범위

이 문서는 `ai-asset-copilot`의 **authoritative specification**이다. 요구사항 충돌 시 이 문서를 기준으로 해결하며, 정책 변경은 인간의 명시적 결정으로 반영한다. README는 진입 안내, Architecture는 설계 설명, Roadmap은 단계별 작업 범위를 제공한다.

현재 단계는 **Phase 0 — Project Bootstrap / Architecture**다. 이번 산출물은 문서, 최소 Python 패키지, 선언적 기본 설정과 pytest 환경이다. 아래의 시스템 동작은 별도 표시가 없으면 **향후 구현 요구사항**이다. 문서에 기록된 안전 경계는 현재 실행 코드로 구현되어 있지 않다.

## 2. 목적과 불변 원칙

하나의 플랫폼에서 다음 두 시스템을 운영한다.

1. 미국주식: 사용자의 장기 자산운용 분석과 의사결정 보조, 실제·가상 의사결정 성과 비교.
2. 한국주식: 전략 검증용 Paper Trading을 시작으로 충분한 검증 후 제한적 자동매매.

공통 원칙:

- LLM은 계산 엔진이 아니다. 금융 수치의 authoritative source는 검증 가능한 코드와 그 입력 데이터다.
- Domain Logic과 Infrastructure, Configuration과 Business Logic을 분리한다.
- AI, Market Data, Broker Provider를 각각 추상화한다.
- 가상계좌와 실제계좌는 공통 Domain을 최대한 공유하되, 잔고·거래·실행 권한은 격리한다.
- 미국 실제 포트폴리오의 주문은 AI가 자동 실행하지 않는다.
- 한국 주문은 반드시 Strategy → Risk → Execution → Broker 순서로 처리한다.
- AI가 Portfolio Policy를 임의로 변경하거나 Risk Limit을 우회할 수 없다.

## 3. 포트폴리오 식별과 역할

| Portfolio ID | 역할 | 실행 원칙 |
| --- | --- | --- |
| `US_REAL` | 사용자의 실제 미국주식 포트폴리오 | 분석·의사결정 보조만 수행. 사용자가 외부에서 실행한 거래를 향후 반영하며 자동 주문 경로를 제공하지 않음 |
| `US_SHADOW_POLICY` | 인간이 정한 고정 Portfolio Policy를 따르는 가상 포트폴리오 | 가상 체결만 허용. 리밸런싱 규칙은 별도 결정 |
| `US_SHADOW_AI` | AI의 Tactical 제안을 실행했다고 가정하는 가상 포트폴리오 | Policy와 Risk 검증을 통과한 제안만 가상 실행. 거절된 제안도 기록 |
| `US_BENCHMARK` | VOO 등의 기준 성과와 비교하는 포트폴리오 | 기준 자산 및 비교 방식은 미결정. 실제 주문 없음 |
| `KR_PAPER` | 한국주식 전략 검증용 가상 포트폴리오 | 초기 가상 자금 **10,000,000 KRW**, 실제 증권사 주문 금지 |

포트폴리오 간 현금·포지션·성과를 섞지 않는다. 한국 실전 포트폴리오의 ID와 계좌 매핑은 실전 단계 전에 결정한다.

## 4. 미국 Portfolio Policy

Portfolio Policy는 **인간이 정한 장기 전략 정책**이다. AI는 Policy 범위 안에서만 Tactical 제안을 할 수 있다. Policy를 위반한 실제 보유 상태는 분석·경고 대상으로 기록할 수 있지만, AI의 우회 제안이나 정책 자동 변경을 허용하지 않는다.

| 자산 분류 | Target | 허용 Range |
| --- | --- | --- |
| Core ETF | 50% | 40–60% |
| Growth ETF | 15% | 10–20% |
| Individual Stocks | 25% | 15–30% |
| Cash | 10% | 5–20% |

| Risk 항목 | 초기 설정 |
| --- | --- |
| 개별 종목 최대 비중 | 15% |
| Concentration Warning | 12% |
| Sector 최대 비중 | 35% |
| 전체 Individual Stocks 최대 비중 | 30% |

초기 값은 `config/us_portfolio_policy.toml`에 선언한다. 비율 단위는 percentage points로, `50`은 50%를 뜻한다. 향후 코드가 이 설정을 읽고 검증하며 수치를 Business Logic에 hard coding하지 않는다. 정책 요구사항과 초기 설정 값은 함께 검토·변경한다.

설정 파일에 쓰인 version은 추적용 식별자다. 파일만으로 수정 권한이 강제되지는 않는다. 향후 AI의 쓰기 권한을 차단하고, 인간의 승인·정책 버전·적용 시점·변경 이력을 보존해야 한다. 과거 판단과 시뮬레이션에는 당시 정책 버전을 연결한다.

분류 체계, 비중 산정 기준, ETF Sector look-through, 경고·한도의 경계값 처리, 리밸런싱 시점과 위반 상태에서의 복구 규칙은 OD-02에서 결정한다. Phase 0에는 정책 평가·리밸런싱·검증기를 구현하지 않는다.

## 5. 코드와 LLM의 책임

다음 값의 계산과 판정은 코드가 담당한다.

- Portfolio Value, Position Weight
- Cost Basis, Average Price
- Realized PnL, Unrealized PnL
- Cash Ratio, Sector Exposure, FX Exposure
- Benchmark Performance
- Order Quantity, Risk Limit

LLM은 Research, Investment Thesis 검증, 시장 변화 해석, Portfolio Risk 해석, Scenario 생성, 투자 의사결정 보조, 과거 Decision Review를 담당한다. 계산된 값을 인용할 때 입력·기준 시점·출처를 유지하며, 데이터가 없거나 오래되면 그 한계를 드러내야 한다.

LLM은 다음 권한을 갖지 않는다.

- Portfolio 숫자를 스스로 계산하여 authoritative source로 제공
- Policy 수정 또는 Risk Limit 우회
- Broker API 직접 호출
- 실제 주문 직접 실행

AI 출력은 제안·설명 데이터다. 실행 가능 여부와 수량은 코드가 별도로 검증·계산하며, LLM 응답의 지시문으로 실행 권한을 부여하지 않는다.

## 6. 미국 의사결정 검증

`REAL vs SHADOW_POLICY vs SHADOW_AI vs BENCHMARK`를 같은 평가 기준으로 비교하여 AI가 실제 의사결정을 개선하는지 검증한다.

최소 비교 지표는 Total Return, Max Drawdown, Volatility, Sharpe Ratio, Cash Ratio, Concentration, Sector Exposure다. 단순 수익률만으로 AI의 기여를 판단하지 않는다.

비교 결과에는 기간, 평가 통화, 가격·FX 기준 시점, 현금흐름, 배당·기업행사, 수수료·세금·슬리피지 가정을 명시한다. 초기 자본과 외부 입출금의 대응, 수익률 방식, 거래 시점, Benchmark 선택, 무위험 수익률과 연율화 기준은 OD-03에서 확정한다. 불완전한 데이터나 서로 다른 가정을 숨겨 비교하지 않는다.

## 7. Decision Journal과 Investment Thesis

Decision Journal은 향후 다음 정보를 연결한다.

- 어떤 질문이 있었는지와 질문 시점
- AI 제안과 모델·입력 자료 식별 정보
- 사용자 실제 선택 및 판단 이유
- 당시 Portfolio 상태와 시장 상태
- Investment Thesis 및 당시 버전
- 적용 Policy, Risk 검토와 가상·실제 결과의 연결
- 이후 결과와 1개월 / 3개월 / 6개월 후 Decision Review

당시 기록과 사후 평가를 구분하고, 사후 정보로 당시 판단을 덮어쓰지 않는다. 검토 일정과 알림은 이후 단계에서 결정하며 Phase 0에 Scheduler를 추가하지 않는다.

미국 개별주 Thesis에는 Why I Own, Investment Thesis, Bull Case, Base Case, Bear Case, Key Risks, Invalidation Conditions, Thesis Status를 관리한다. 상태는 `STRENGTHENED`, `UNCHANGED`, `WEAKENED`, `BROKEN`이다. AI는 단순 가격 변화보다 Thesis의 근거·위험·무효화 조건 변화를 중심으로 분석한다. 상태 변화는 자동 매도 명령이 아니다.

이번 Phase에는 Journal과 Thesis의 모델·저장·평가 기능을 구현하지 않는다.

## 8. 한국 Paper Trading과 자금 확대

`KR_PAPER`의 초기 가상 자금은 **10,000,000 KRW**다. 선언은 `config/kr_paper.toml`에 두며 실제 자금과 연결하지 않는다.

Paper Trading은 실제 거래와 최대한 유사하게 Commission, Tax, Slippage, Partial Fill, Rejected Order, Market Hours, Available Cash, Position Limit, Daily Loss Limit, Duplicate Order Protection을 고려해야 한다. 구체적인 수수료·세율·체결 모델·한도는 임의로 정하지 않고 OD-05로 남긴다.

전략별 검증과 자금 투입 순서는 다음과 같다.

**Backtest → Live-market Paper Trading → 1,000,000 KRW 실전 → 3,000,000 KRW → 5,000,000 KRW → 최대 10,000,000 KRW**

Paper Trading에서 전략 성능이 확인되기 전에는 실제 주문 기능을 활성화하지 않는다. 각 단계는 자동 승격하지 않으며, 사전에 정한 검증 기준과 인간의 명시적 승인을 요구한다. 실제 자금 연결 전 최종 Safety Audit을 수행한다. 정량적 성능·기간·손실 기준과 중단 조건은 OD-08에서 결정한다.

개발 로드맵의 Phase 8은 Paper Trading 기반을 만들고, Phase 9는 전략·Backtest를 구현하며, Phase 10은 Live-market Paper Trading으로 검증한다. 기반 기능을 만드는 순서가 전략의 검증 순서를 바꾸지 않는다.

## 9. Strategy / Risk / Execution / Broker

향후 주문 흐름은 반드시 다음과 같다.

**Strategy Engine → Risk Engine → Execution Engine → Broker Adapter**

- Strategy: 전략 입력으로부터 주문 의도 생성. Broker 호출 권한 없음.
- Risk: Policy와 계좌 상태, 자금·포지션·손실 한도로 주문을 승인 또는 거절. 이유와 사용한 상태를 남김.
- Execution: 검증된 승인에 따라 주문 생명주기, 중복 방지, 부분 체결, 취소·재시도·결과 대사를 관리.
- Broker Adapter: 제공자별 통신과 응답 변환. 전략 결정이나 Risk 우회 권한 없음.

미승인·만료·불완전한 주문은 Execution이 진행하지 않는 구조를 설계한다. LLM은 이 체인을 직접 호출하는 실행 주체가 될 수 없고, Broker credentials를 전달받지 않는다. 상세 승인 표현·검증 계약과 상태 전이는 후속 Phase에서 정의한다.

## 10. Backtest Integrity

Backtest는 Look-ahead Bias, Survivorship Bias, 미래 데이터 참조, 잘못된 Entry/Exit Price, Fee·Tax·Slippage 누락을 방지해야 한다.

당시 사용 가능했던 데이터와 종목 집합을 사용하고, 신호 시점과 체결 가능 시점을 구분하며, 데이터 시점·기업행사 처리·거래비용·체결 가정을 기록한다. 전략 실행과 평가를 재현할 수 있어야 한다. 검증 자료가 부족한 경우 그 한계를 결과에 표시한다.

Backtest 성능만으로 실제 자금 투입을 결정하지 않는다. Live-market Paper Trading과 이후 제한적 실전 검증을 순서대로 거쳐야 한다.

## 11. Provider와 기술 방향

- 주 언어: Python. Phase 0 개발 기준은 Python 3.11 이상이다.
- 초기 Database: SQLite. 필요하면 PostgreSQL로 이전할 수 있도록 Domain이 DB·ORM에 의존하지 않게 한다.
- Test: pytest. 금융 계산은 외부 API·LLM·DB 없이 테스트할 수 있어야 한다.
- AI / Broker / Market Data Provider는 별도 adapter와 Domain이 정의하는 계약으로 연결한다. 제공자는 미결정이다.
- 가상·실제 계좌가 공통 Domain을 사용하되 execution mode와 계좌 식별은 명시적으로 분리한다.
- FastAPI와 Streamlit은 실제 필요성이 생기기 전까지 추가하지 않는다.

Broker의 향후 인터페이스 개념은 `get_accounts`, `get_balance`, `get_positions`, `get_orders`, `place_order`, `cancel_order`다. 인자·반환값·동기/비동기 계약은 아직 결정하지 않는다.

구현 예시는 MockBroker, PaperBroker, KoreanBroker, USBroker다. MockBroker는 테스트 대역, PaperBroker는 가상 체결, 나머지는 외부 제공자 adapter를 뜻한다. 공통 인터페이스가 있다고 모든 포트폴리오에 주문 권한이 생기는 것은 아니다. `US_REAL`은 조회·반영만 허용하며 자동 주문 대상이 아니다. Phase 0에 Broker 인터페이스나 구현 클래스를 만들지 않는다.

## 12. Roadmap

| Phase | 주제 |
| --- | --- |
| 0 | Project Bootstrap / Architecture |
| 1 | Portfolio Foundation |
| 2 | Market Data |
| 3 | US Portfolio Analytics |
| 4 | US Portfolio Policy |
| 5 | US Shadow Engine |
| 6 | Research / Investment Thesis |
| 7 | AI Asset Copilot |
| 8 | KR Paper Trading |
| 9 | KR Strategy / Backtest |
| 10 | KR Live-market Paper Trading |
| 11 | Dashboard / Daily / Weekly Report |
| 12 | Broker Integration |
| 13 | Limited KR Live Trading |

단계별 완료 조건은 [docs/ROADMAP.md](docs/ROADMAP.md)에 기록한다. Phase 12의 Broker 연결 자체로 실전 주문을 허용하지 않는다. 실전 주문 활성화는 Phase 13의 별도 승인과 검증을 전제로 한다.

## 13. 개발 모델 운용

| 업무 | 사용 원칙 |
| --- | --- |
| 일반 구현 | Sol Medium |
| 복잡한 구현 | Sol High |
| 중요한 Architecture / 금융 구조 검토 | Astra Medium 또는 High |
| Backtest Integrity Audit | Astra Extra High |
| Broker / Execution Safety Audit | Astra Extra High |
| 실제 자금 연결 전 최종 Safety Audit | Astra Extra High |

대부분의 실제 구현은 Sol이 담당하고 Astra는 설계와 중요 검수에 집중한다. 이번 Phase 0의 지정 모델은 Astra High다. 이 표는 개발 작업의 모델 운용 원칙이며, 제품에서 사용할 AI Provider·모델 선택은 별도 Open Decision이다.

## 14. Phase 0 산출물과 제외 범위

산출물: README, 이 명세, Architecture, Roadmap, `.gitignore`, `.env.example`, `pyproject.toml`, `src/asset_copilot/`, `tests/`, 기본 정책·가상 자금 선언용 `config/`.

`domain`, `portfolio`, `market`, `research`, `risk`, `strategy`, `execution`, `broker`, `agents`, `storage`, `reports`는 향후 논리적 모듈이다. 실제 구현이 필요할 때 패키지를 생성한다. `scripts/` 역시 실행할 도구가 생길 때 생성한다. 빈 Python 파일을 미리 대량 생성하지 않는다.

이번 Phase에서는 다음을 구현하거나 의존성으로 추가하지 않는다: OpenAI API, LLM Agent, Market Data API, 증권사 API, 실제 주문, 자동매매, Portfolio Calculator, DB Schema, SQLAlchemy, Backtesting, Technical Indicator, Dashboard, FastAPI, Streamlit, Scheduler.

기본 설정 loader·validator도 이번 Phase에 만들지 않는다. 런타임 dependency는 없고 개발용 pytest와 패키지 빌드용 setuptools만 선언한다. 자동 commit / push는 하지 않는다.

## 15. Open Decisions

아래 항목은 구현 직전 관련 Phase에서 인간과 결정하고 이 문서를 갱신한다. 값이나 계약이 정해지기 전 임의의 운영 기본값으로 활성화하지 않는다.

| ID | 미결정 사항 | 결정 시점 |
| --- | --- | --- |
| OD-01 | 금융 수치의 Decimal 정밀도·반올림, Cost Basis 방식, 수수료 배분, FX 환산 기준, 자산·계좌 식별, 거래 및 기업행사 표현, 시간대·평가 시점 | Phase 1, Market Data 연결 전 보완 |
| OD-02 | 자산·Sector 분류와 ETF look-through, 비중 분모, Risk 한도 적용 대상, 경계값 포함 여부, 리밸런싱 트리거·거래 우선순위, 위반 상태 복구, 인간 Policy 변경 승인·버전 적용 방식 | Phase 4; Shadow 실행 전 |
| OD-03 | Benchmark 자산, 초기 자본·입출금 대응, 배당 재투자, TWR/MWR 등 수익률 기준, 비교 통화·기간·체결 가정, Sharpe 무위험 수익률·연율화, 집중도 정의 | Phase 3–5 |
| OD-04 | Market Data Provider, 데이터 라이선스·지연·수정주가·상장폐지 종목·point-in-time coverage, FX 출처, AI Provider·모델과 개인정보 전송 범위 | Market Data: Phase 2, AI: Phase 7 |
| OD-05 | 한국 시장 Commission·Tax·Slippage, 체결·호가·유동성·Partial Fill 모델, Market Hours, 결제·가용 현금 규칙, Position/Daily Loss Limit 수치·기준 | Phase 8; Phase 9–10 전에 검증 |
| OD-06 | Repository 계약, DB Schema·마이그레이션·트랜잭션, SQLite 동시성, PostgreSQL 이전 기준 | Phase 1 및 저장 요구 확장 시 |
| OD-07 | 주문·Risk 승인 계약, idempotency key, 동시 주문 시 자금 예약, 승인 유효성 재검사, 재시도·대사·중단·복구, Broker Provider와 capability·계좌 권한 | Phase 8; Phase 12 연결 전 Safety Audit |
| OD-08 | 전략 평가 기간·승격 기준·허용 손실, 단계별 인간 승인, 실전 계좌 ID, 자금 한도의 정의, 증액·감액·중단·rollback 기준 | Phase 10; Phase 13 자금 연결 전 확정 |
| OD-09 | Journal/Thesis 버전·보존·검토 일정, AI 제안 채택·보류·거절의 표현, 개인정보 보관과 삭제 | Phase 6–7 |
| OD-10 | Backtest 전략·universe·검증 구간·재현 규칙·과적합 통제, 데이터 불완전 시 실험 제외 기준 | Phase 9 |
| OD-11 | Dashboard 기술, Daily/Weekly Report 전달 수단·일정·Scheduler 필요성 | Phase 11 |
| OD-12 | 의존성 lock·재현 가능한 개발 환경 및 CI·지원 Python 버전 조합 | 후속 개발 환경 확장 시 |

## 16. Phase 0 완료 기준

- 기존 Repository 상태를 확인한 후 필요한 파일만 생성한다.
- 최소 패키지를 개발 환경에 설치하고 pytest smoke test를 통과한다.
- 초기 Policy 설정과 KR 가상 자금 선언이 이 명세와 일치한다.
- 문서 간 로드맵·안전 경계·미구현 범위의 충돌을 검토한다.
- 변경 파일, 테스트 결과, Git 상태, Phase 1 권장 범위와 미결정 사항을 보고한다.
