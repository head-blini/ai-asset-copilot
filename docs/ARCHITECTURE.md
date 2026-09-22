# Architecture

이 문서는 [PROJECT_SPEC.md](../PROJECT_SPEC.md)의 요구사항을 설계로 설명한다. 명세가 authoritative source다. **현재 구현은 Portfolio Foundation, Market Data 정규화, 현재 미국 계좌 분석이다. AI·Risk·Execution·Broker 등의 흐름은 향후 설계다.** 정책 설정 파일도 아직 실행 코드에서 읽지 않는다.

## 1. 공통 Domain과 의존성

미국 장기 자산운용과 한국 전략 검증은 계좌, 포트폴리오, 현금, 포지션, 거래, 평가 시점 등의 공통 개념을 공유한다. 시장별 거래 규칙과 제공자 통신은 별도 경계에 둔다. Domain은 AI SDK, Broker SDK, Market Data SDK, DB·ORM, 웹 프레임워크를 import하지 않는다.

Phase 3 `application`은 Repository와 MarketDataProvider 계약을 주입받아 순수 Portfolio 계산을 호출한다. 향후 다른 use case의 Risk 검사와 실행 권한은 별도 경계에서 정의한다. Infrastructure adapter가 이 계약을 구현한다.

```mermaid
flowchart LR
    APP[Application orchestration] --> DOMAIN[Domain / 계산 / 정책 계약]
    ADAPTER[AI / Market / Broker / Storage adapters] --> PORT[Domain 측 provider / repository 계약]
    APP --> PORT
    DOMAIN --> VALUE[공통 금융 개념]
```

화살표는 의존성 방향이다. 외부 제공자 응답은 경계에서 내부 데이터로 변환한다. Domain 테스트는 네트워크나 실제 계좌 없이 실행 가능해야 한다. Phase 1의 Decimal·원가·거래 시각 기준은 명세 17절에서 정했고, Phase 3는 현재 USD/KRW 보고 환산만 정했다. 역사적 성과용 FX 기준과 표시·Broker·세금 반올림은 OD-01에 남겨 두었다.

## 2. 논리적 모듈

아래는 책임 지도다. Phase 1의 `domain`, `portfolio`, `storage`, Phase 2의 `market`, Phase 3의 `application`을 구현했으며 나머지는 실제 책임이 생길 때 만든다.

| 모듈 | 책임 | 경계 |
| --- | --- | --- |
| `domain` | 공통 식별자·금융 개념·불변식·provider/repository 계약 | 외부 SDK와 저장소 구현에 독립 |
| `portfolio` | 계좌·포지션·거래·현금과 평가·손익 계산 | 계산 결과의 근거와 시점 보존 |
| `application` | Repository·Market Provider를 조합한 현재 미국 계좌 분석 | 관측 시점·통화·신선도 확인 후 순수 계산 호출 |
| `market` | 가격·FX·시장 상태의 조회 계약과 정규화 | 외부 API adapter와 순수 데이터 검증 분리 |
| `research` | Research 자료, Investment Thesis, Decision Journal | 당시 근거와 사후 결과를 구분 |
| `risk` | Portfolio Policy, 자금·포지션·손실 제한의 코드 기반 검증 | LLM 해석에 의해 판정이 바뀌지 않음 |
| `strategy` | 코드로 정의된 전략과 주문 의도 생성 | Broker 직접 호출 금지 |
| `execution` | Risk 승인 검증, 주문 상태·중복 방지·체결·취소·대사 | 승인 없는 주문 전달 금지 |
| `broker` | Mock/Paper/실제 provider의 통신·체결 adapter | 실행 모드·계좌 capability 구분 |
| `agents` | AI Provider 추상화, 자료 해석과 제안 | 계산·정책 수정·주문 실행 권한 없음 |
| `storage` | SQLite repository 구현과 향후 DB 이전 | Domain에 SQL·ORM 객체를 노출하지 않음 |
| `reports` | 검증된 데이터와 AI 설명의 보고서 구성 | 수치를 독자적으로 재계산하지 않음 |

논리적 모듈 하나에 Domain 로직과 adapter가 모두 생기면 파일 수준으로 먼저 분리한다. 필요가 확인되기 전에 다층 패키지나 프레임워크를 추가하지 않는다. Backtest와 Shadow Engine의 구체적 패키지 배치는 각각 Phase 9와 Phase 5에서 결정한다.

### Phase 2 Market Data 경계

`market.provider.MarketDataProvider`는 Asset 목록에서 asset_id별 `MarketQuote`를, 통화 방향에서 `FxQuote`를 얻는 계약이다. 내부 quote 타입과 순수 신선도 판정은 `market.models`, 공통 오류는 `market.errors`, Twelve Data HTTP·응답 파싱과 명시적 asset_id→symbol/exchange resolver는 `market.twelve_data`에 둔다. 다른 provider도 내부 타입과 계약을 따를 수 있다. 첫 adapter는 미국 USD 주식·ETF 가격과 FX를 조회하며 한국 가격 adapter는 없다. 표준 라이브러리 `urllib`에 명시적 timeout과 주입 가능한 HTTP 함수를 사용하므로 추가 runtime dependency 없이 네트워크 없는 adapter 테스트를 수행한다. API key는 Authorization 헤더로 전송해 URL에 포함하지 않는다.

Twelve Data `/quote`는 기본 `1day`의 `close`와 마지막 1분 캔들 시각이 섞이지 않도록 `interval=1min`을 명시한다. 응답의 `timestamp`와 `last_quote_at`이 동일한 1분 캔들을 가리킬 때만 그 캔들 시작 시각을 `as_of`로 쓴다. 둘이 없거나 다르면 `as_of=None`이다. 이 시각은 정확한 마지막 거래 시각이 아니며 가격 기준을 보수적으로 나타낸다. `/exchange_rate`의 `timestamp`는 환율 시각이다. 출처는 `twelve_data`이고 모든 내부 시간은 UTC다. `as_of=None`이면 최신 가격임을 입증할 수 없으므로 stale다. 호출자가 기준 시각과 `max_age`를 지정하고 투자용 threshold는 아직 정하지 않는다. `FxQuote.rate`는 base 1단위당 quote 통화 단위다. 제공자 오류를 명시적 Market Data 오류로 바꾸며 가상 가격 자동 fallback은 없다.

Portfolio `value_at_prices()`는 여전히 순수 함수다. Phase 3 orchestration에서 quote의 asset_id·통화·신선도·시점을 확인한 뒤 `{asset_id: Decimal}`을 만들어 전달한다. FX는 USD Ledger에 적용하지 않고 KRW 보고 값에만 사용한다. 최신 quote cache/과거 가격 history 테이블은 만들지 않았다. 데이터 라이선스, 시세 지연, 수정주가, 상장폐지, point-in-time 보장 및 실제 투자용 freshness 정책은 OD-04에 남긴다.

### Phase 3 현재 상태 분석

`USPortfolioAnalyzer`는 계좌 원장과 관련 Asset을 Repository에서 읽고 `replay()`로 상태를 재구성한다. 열린 Position의 asset_id별 `MarketQuote`를 조회하여 ID·통화·가격·출처·`as_of`와 명시된 `max_quote_age`를 검증한다. 실패한 quote가 하나라도 있으면 평가를 반환하지 않는다. USD/KRW `FxQuote`도 방향·환율·시각·신선도를 검증한다. 그 후 기존 `value_at_prices()`를 호출한다. 계산기는 Provider 또는 저장소를 import하지 않으며 Market adapter도 계산기를 호출하지 않는다.

결과는 불변 `PortfolioAnalysis`다. `evaluated_at`은 UTC로 정규화하고, Position마다 quote의 `as_of`·`fetched_at`·source를 보존한다. FX에도 별도 시각·출처를 보존하고, 사용한 quote/FX max age와 strict freshness 통과 상태를 남긴다. 단일 `market_as_of`를 합성하지 않는다. STOCK·ETF·현금 노출은 계좌 총 USD 평가액 대비 비율이다. Sector는 직접 STOCK 분류만 합산하며 미분류 STOCK과 ETF 평가액을 따로 보인다. ETF holdings look-through는 없다. USD/KRW는 보고 환산액만 만들고 USD 원장·Cost Basis를 바꾸지 않는다.

`trading_pnl`은 매매 실현손익과 열린 Position의 미실현손익의 합이다. DIVIDEND는 현금을 늘리지만 이 거래 손익에는 포함되지 않는다. 따라서 이 값은 총 투자수익률이 아니다. 과거 가격·snapshot history가 없어 CAGR·Max Drawdown·Volatility·Sharpe·Benchmark 성과를 만들지 않는다. 휴장일·주말을 고려한 freshness, 배당 포함 성과와 현금흐름 조정 방식은 OD-03/OD-04의 후속 결정이다. 실제 개인 거래 및 SQLite DB는 Git에서 제외한다.

## 3. 미국 분석과 네 포트폴리오

```mermaid
flowchart TD
    DATA[사용자 거래 / Market Data / FX] --> CALC[코드 기반 Portfolio 계산]
    CALC --> SNAP[시점이 명시된 Portfolio Snapshot]
    SNAP --> REAL[US_REAL 분석]
    SNAP --> POLICY[US_SHADOW_POLICY]
    SNAP --> AI[AI Tactical 제안]
    AI --> CHECK[Policy / Risk 검증]
    CHECK --> SHADOW[US_SHADOW_AI 가상 실행]
    BENCH[기준 자산 데이터] --> BASE[US_BENCHMARK]
    REAL --> COMPARE[성과 / 위험 비교]
    POLICY --> COMPARE
    SHADOW --> COMPARE
    BASE --> COMPARE
    AI --> JOURNAL[Decision Journal]
    REAL --> JOURNAL
    COMPARE --> REVIEW[1 / 3 / 6개월 Review]
    JOURNAL --> REVIEW
```

각 포트폴리오는 독립 상태를 갖는다. 다이어그램의 Snapshot은 공통 입력 형태를 뜻하며 동일 잔고를 공유한다는 뜻이 아니다. 초기 상태·입출금 대응 방식은 OD-03에서 정한다. `US_REAL`은 사용자의 외부 거래를 반영하고 시스템이 실제 주문을 자동 발행하지 않는다.

`US_SHADOW_POLICY`는 인간의 장기 Policy와 코드로 정한 리밸런싱 규칙을 따른다. `US_SHADOW_AI`는 당시 AI 제안과 Policy/Risk 검증 결과를 연결한다. 제안 시점 이후의 체결 가능 정보와 비용을 사용해 가상 실행하며, 미래 정보로 과거 제안을 개선하지 않는다. 두 Shadow는 실제 Broker 주문으로 라우팅할 수 없어야 한다.

성과 비교는 Total Return, Max Drawdown, Volatility, Sharpe Ratio, Cash Ratio, Concentration, Sector Exposure를 포함한다. 계산식·가격/FX 시점·통화·비용·배당·현금흐름 규칙은 동일한 비교 기준으로 명시하며, 아직 미정인 방식은 OD-03에서 해결한다.

## 4. 인간 Policy와 AI 경계

Policy 값은 [기본 설정](../config/us_portfolio_policy.toml)에 선언되어 있다. 코드에 수치를 복제하지 않는다. Phase 4에서 단위·합계·범위·한도 간 일관성 등을 검증하는 설정 loader와 evaluator를 만든다.

향후 application은 인간이 승인한 Policy 버전을 읽어 Risk Engine에 전달한다. AI에는 분석에 필요한 읽기 전용 데이터만 제공하며, Policy 저장소 쓰기 권한과 Broker credentials를 제공하지 않는다. Policy 변경 경로는 AI 제안 경로에서 분리하고 인간의 변경 이력과 적용 시점을 남긴다. 이를 강제하는 구체적 권한 구조는 OD-02에서 결정한다.

AI 출력은 검증되지 않은 입력으로 취급한다. Research 문서나 모델 응답 안의 명령은 시스템 권한을 변경할 수 없다. 금융 계산, Risk Limit 및 Order Quantity는 코드에서 생성한 결과를 사용한다. LLM이 임의로 작성한 수치를 잔고·손익·Risk 판정으로 저장하지 않는다.

## 5. 한국 주문 흐름과 모드 격리

```mermaid
flowchart LR
    SIGNAL[Strategy Engine] --> RISK[Risk Engine]
    RISK -->|승인된 주문 의도| EXEC[Execution Engine]
    RISK -->|거절 사유| RECORD[검증 기록]
    EXEC --> ADAPTER[Broker Adapter]
    ADAPTER --> PAPER[PaperBroker / 가상 체결]
    ADAPTER -. Phase 13 승인 후 .-> LIVE[KoreanBroker / 제한적 실전]
```

Strategy는 주문 의도만 만든다. Risk는 계좌 상태와 설정에 따라 코드로 제한을 평가하고, 거절 사유와 평가 입력을 남긴다. Execution은 Risk 승인과 실행 모드·계좌가 일치하는지 확인하고 주문을 Broker Adapter에 전달한다. Strategy·AI가 Execution 또는 Broker에 직접 접근해 검증을 생략할 수 없는 의존성 구조를 유지한다.

주문 수량 계산의 상세 분담은 OD-07에서 정하되, Strategy가 제안한 수량을 그대로 신뢰하지 않는다. 최종 수량·가격 조건·현금 예약·한도 검증은 코드가 맡는다. 승인 후 계좌 상태가 바뀌었을 때의 재검사, 동시 주문 자금 예약, 중복 키, 통신 실패 후 재시도와 대사는 Execution 계약에서 반드시 다룬다. 유효한 승인을 확인할 수 없으면 주문을 진행하지 않는다.

PaperBroker는 Commission, Tax, Slippage, Partial Fill, Rejected Order, Market Hours, Available Cash, Position Limit, Daily Loss Limit, Duplicate Order Protection을 실제와 유사하게 다룰 수 있어야 한다. Risk의 제한 판정과 Broker의 체결 결과는 별도 기록으로 보존한다. 구체적인 값과 모델은 OD-05/07에서 정의한다.

MockBroker는 단위 테스트 대역, PaperBroker는 가상 실행 구현이다. 둘 다 실제 Broker로 암묵적으로 fallback하지 않는다. 실전 credentials를 넣거나 provider를 바꾸는 것만으로 `KR_PAPER`가 실전 계좌로 전환되어서는 안 된다. 실전은 별도 포트폴리오 식별·인간 승인·검증을 요구한다.

## 6. Broker 계약

개념상 `get_accounts`, `get_balance`, `get_positions`, `get_orders`, `place_order`, `cancel_order`를 제공한다. 메서드의 데이터 타입, 동기/비동기 방식, 오류 모델과 capability 계약은 구현 전에 결정한다. Phase 0에 interface stub을 만들지 않는다.

MockBroker, PaperBroker, KoreanBroker, USBroker는 가능한 adapter 예시다. 제공자 선정은 미결정이다. 조회 권한과 주문 권한은 구분하며, USBroker를 도입해도 `US_REAL` 자동 주문을 허용하지 않는다. Phase 12는 조회·sandbox·paper 중심의 연결과 장애 검증을 수행하고, Phase 13 이전에는 실제 주문 기능을 활성화하지 않는다.

## 7. 저장과 재현성

SQLite로 시작하고 repository 계약 뒤에 DB 구현을 둔다. Domain은 연결 문자열, 테이블, ORM에 의존하지 않는다. PostgreSQL 이전을 자동으로 보장한다고 가정하지 않으며, 이후 SQL 차이·트랜잭션·정밀도·동시성·마이그레이션 검증이 필요하다. Phase 0에는 DB 파일·Schema·SQLAlchemy를 추가하지 않는다.

향후 Portfolio Snapshot, Policy 버전, 가격/FX의 기준 시점과 출처, 전략 버전, AI 입력·제안, Risk 결과, 주문·체결, Journal/Thesis를 관련 식별자로 연결한다. 이는 데이터 요구사항이며 현재 DB Schema를 확정하는 것이 아니다. 과거 의사결정의 입력을 사후 최신 값으로 교체하지 않는다.

Backtest는 당시 존재하고 사용 가능했던 종목·정보를 사용한다. 신호 생성 시점과 체결 가능 시점을 구분하고 Entry/Exit 가격·Fee·Tax·Slippage·기업행사 처리 가정을 저장한다. Live-market Paper Trading에서 동일한 Strategy/Risk 계약을 재사용하여, 과거 시뮬레이션과 실시간 조건의 차이를 측정한다.

## 8. 현재 구조와 후속 확장

```text
ai-asset-copilot/
├── README.md
├── PROJECT_SPEC.md
├── .gitignore
├── .env.example
├── pyproject.toml
├── config/
│   ├── us_portfolio_policy.toml
│   └── kr_paper.toml
├── docs/
│   ├── ARCHITECTURE.md
│   └── ROADMAP.md
├── src/
│   └── asset_copilot/
│       ├── __init__.py
│       ├── domain/
│       │   ├── __init__.py
│       │   ├── models.py
│       │   └── repositories.py
│       ├── portfolio/
│       │   ├── __init__.py
│       │   └── calculator.py
│       └── storage/
│           ├── __init__.py
│           └── sqlite.py
└── tests/
    ├── test_bootstrap.py
    ├── test_portfolio_domain.py
    └── test_sqlite_repositories.py
```

Phase 1에서 `src/asset_copilot/domain/{models,repositories}.py`, `portfolio/calculator.py`, `storage/sqlite.py`를 추가했다. 그 이후 실제 use case가 생기는 순서대로 확장한다. `config/`는 현재 저장소 내 선언 파일이며 설치 패키지의 runtime resource 계약은 아직 없다. `.env.example`에는 실제 환경 변수나 credentials를 요구하지 않는다.

## 9. 검증 전략

Phase 0은 설치된 패키지 import와 pytest 실행만 smoke test로 확인했다. Phase 1은 Ledger의 손계산 fixture, 잘못된 입력, 재생 순서, 계좌 격리, SQLite 정밀도 왕복·재개방·불변 트리거·복수 연결에서의 이중 지출 거부를 검증한다. 이 테스트로 주문 안전성이 검증되었다고 주장하지 않는다.

후속 Phase에서는 금융 계산의 단위·반올림·불변식, Policy 경계값, 계좌 간 격리, 비용·부분 체결·주문 거절, 중복 주문·재시도·통신 실패·대사, point-in-time 데이터와 Backtest 재현성을 단계에 맞게 검증한다. 실제 계좌 연결 전에는 Broker / Execution Safety Audit과 최종 Safety Audit을 별도로 수행한다.

미결정 사항의 원장은 [PROJECT_SPEC의 Open Decisions](../PROJECT_SPEC.md#15-open-decisions)다. 이 문서에서 임의의 제공자, 수익률 계산식, 위험 한도 또는 실전 승인 기준을 추가하지 않는다.

## 10. Phase 1 Ledger와 SQLite 구현

Portfolio는 운용 목적, Account는 Ledger와 잔고의 독립 경계다. Account는 하나의 Portfolio에 연결되며 Portfolio 하나에 Account 여러 개를 만들 수 있다. 계좌 간 거래·현금·포지션을 합쳐 재생하지 않는다. `AccountType`은 상태 구분용이고 Phase 1 계산에 계좌별 특례를 만들지 않는다.

`Transaction`은 frozen Domain record다. 계좌별 양의 연속 `sequence`는 안정적인 기록 순번이며 동일한 `executed_at`의 tie-breaker다. 시간대가 있는 `executed_at`은 금융 이벤트의 발생 시각이다. Domain의 `replay` 함수는 먼저 sequence의 완전성·유일성을 검증하고, 그다음 `(executed_at ASC, sequence ASC)` 순으로 Accounting 상태를 계산한다. 뒤늦게 발견된 과거 거래도 다음 sequence로 기록할 수 있다. 전체 이력의 어느 시점에서든 현금 부족·초과 매도·통화 불일치 등이 생기면 추가를 거부한다. 거래는 한 통화·한 계좌·선택적인 한 자산에 속한다.

Replay 결과는 불변 `AccountSnapshot`이며 Cash, 현재 Position, 평균 원가, 잔여 Cost Basis, Total Invested Cost, 누적 Realized PnL을 포함한다. 수동 asset_id→Decimal 가격 mapping을 넣는 별도 함수가 시장가치·Unrealized PnL·총가치·Position Weight·Cash Ratio를 계산한다. Snapshot을 authoritative 저장 상태로 쓰지 않는다. 모든 열린 Position의 asset_id 가격이 필요하고, 추가로 조회된 가격은 무시한다. 같은 ticker를 가진 자산도 ID별로 평가한다. Provider symbol/ticker를 Domain Asset ID로 resolve하는 책임은 Phase 2 Market Data에 둔다.

`domain/repositories.py`는 Portfolio·Account·Asset·Transaction Repository 계약을 정의한다. `storage/sqlite.py`의 adapter는 네 테이블과 계좌별 sequence 유일 제약을 사용한다. Decimal 컬럼은 `TEXT`이고 Python Decimal을 `str()`로 직렬화한 뒤 `Decimal()`로 복원한다. SQLite NUMERIC/REAL affinity로 인한 이진 부동소수 변환을 피한다. 거래 UPDATE/DELETE는 DB 트리거가 거부한다.

`TransactionRepository.append`는 `BEGIN IMMEDIATE`로 쓰기 잠금을 얻은 후 해당 계좌의 기록을 읽고, 새 이벤트를 포함한 전체 Ledger를 유효 시각 순으로 Domain replay하여 검증하고, 성공하면 INSERT 후 commit한다. 과거 시점 backfill도 이 검증을 통과하면 저장하며 실패 시 rollback한다. 각 연결은 foreign key 검사를 켠다. 별도 연결을 통한 이중 지출도 순서대로 검증한다. 이것은 Phase 1의 단순한 동시성 계약이며 실제 주문 실행·예약·대사는 OD-07 범위다. 직접 DB 접근으로 규칙을 우회하지 않는 것이 application 계약이며, SQLite 파일에 대한 운영 권한 통제는 별도 과제다.

Cost Basis는 이동 가중평균 분석 값이다. 부분 매도의 처분 원가는 그 시점 잔여 원가 비율로 배분하고 최종 매도에서는 잔여 원가 전부를 제거한다. Dividend는 원가를 바꾸지 않는다. Cash Asset은 만들지 않았다. Cash는 거래 이벤트에서 파생되는 단일 통화 계좌 상태이고, Asset 테이블은 거래·배당 대상 STOCK/ETF를 표현하기 때문이다. Tax Lot, 기업행사와 역사적 성과용 FX·가격 시점 기준은 후속 Phase에서 정의한다.

## 11. Phase 1 감사에서 보완한 경계

- 시간 정렬은 `executed_at.astimezone(UTC)`와 sequence를 사용한다. DST 종료 때 같은 timezone 객체의 wall-clock 순서가 실제 순서와 달라지는 문제를 피한다. 저장은 offset을 포함한 ISO 시각을 사용하며, 재생 전후 같은 금융 시각으로 해석한다.
- 나눗셈 정밀도는 `max(80, 분자 계수 자릿수 + 4 × 분모 계수 자릿수)`다. 유한소수의 약분된 분모는 2와 5의 거듭제곱이므로 이 상한으로 유한소수 결과를 보존할 수 있다. 소수 지수는 유효숫자에 중복 반영하지 않는다. 순환소수의 매우 작은 배분 오차는 잔여 원가에 남고, 마지막 매도에서 잔여 원가 전부를 사용한다. Decimal context의 모든 설정과 오류 trap을 명시한다.
- 조회된 Asset의 `id`가 mapping key와 다르면 거부한다. 같은 ticker·다른 거래소의 자산은 여전히 각 ID로 처리한다.
- COMMIT을 예외 처리 범위에 포함하고, 중단 예외도 rollback 후 다시 전달한다. `SQLITE_BUSY`로 commit이 실패한 뒤 미완료 INSERT와 잠금이 남는 것을 방지한다. `recursive_triggers`를 켜 REPLACE도 불변 트리거를 거치게 한다.
- 기존 테스트에 반복 소수 수량 매도·재진입·다중 자산 손익·과도한 매도 수수료·DST 왕복·실제 commit 경합·동시 append를 추가했다. Phase 1 원장과 저장 검증이며, Broker 주문 예약·재시도·대사 검증을 대체하지 않는다.

남은 제한: `SQLiteStore.connection`은 관리·진단용 raw connection을 노출하므로 application은 Repository 계약만 사용해야 한다. 외부 연결이나 직접 SQL로 새 이벤트 삽입·설정 변경을 하는 것은 불변식 보장 범위 밖이다. 전체 replay 기반 append의 장기 성능, Ledger 숫자 입력의 자릿수·지수 자원 한도, migration·backup 운영은 후속 결정이 필요하다. Market Quote에는 currency·기준 시각·출처가 있지만 순수 Portfolio 가격 mapping에는 없으므로 Phase 3 application이 quote 검증과 변환을 맡는다.
