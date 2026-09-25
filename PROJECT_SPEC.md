# Project Specification

## 1. 문서의 지위와 현재 범위

이 문서는 `ai-asset-copilot`의 **authoritative specification**이다. 요구사항 충돌 시 이 문서를 기준으로 해결하며, 정책 변경은 인간의 명시적 결정으로 반영한다. README는 진입 안내, Architecture는 설계 설명, Roadmap은 단계별 작업 범위를 제공한다.

현재 구현 완료 단계는 **Phase 3 — US Portfolio Analytics**다. 계좌별 Ledger와 Market Data를 application 계층에서 연결해 미국 USD 계좌의 현재 상태를 분석한다. 각 절의 Phase 0 산출물 설명은 당시 범위의 기록이다. AI·Broker·주문 경계는 여전히 향후 구현 요구사항이다.

ChatGPT 웹은 설계·우선순위·중요 검토, Codex는 구현·테스트·문서 작업을 돕는 개발 도구다. 어느 쪽도 제품의 런타임 승인 주체가 아니다. 런타임에는 코드가 입력과 관측을 검증하고 금융 계산·Policy·Risk 판정을 담당한다. AI 응답은 별도 검증 전에는 제안·설명에 그친다. 인간의 Policy 변경 승인과 한국 실전 단계별 승인은 개발 도구의 응답으로 대체되지 않는다.

## 2. 목적과 불변 원칙

하나의 플랫폼에서 다음 세 영역을 연결한다. 개인 예산은 제품 범위에 추가된 **후속 요구사항**이며 현재 구현된 기능이 아니다.

자산 증식의 사용자 목적은 **주택 구매와 노후 준비**다. 목표금액·시점·손실 감당 범위·맞춤 투자 전략은 아직 정하지 않았다. “돈은 많을수록 좋다”는 공격적 투자나 최대 위험의 승인이 아니다. 같은 현금을 주택자금과 노후자금에 동시에 배정하지 않는다. 목표금액·기한이 없어도 확인된 소득·지출·현금 상태는 보고하고, 목표 적립 필요액은 `UNKNOWN`과 필요한 정보를 반환한다.

1. 개인 재무: 실수령 소득, 예정 현금흐름, 생활비·자유지출·필수 상환, 비상자금·목표저축, 미국 장기투자·한국 전략용 자금의 월간 예산을 계산하고 실적 대비 수정안을 제안한다.
2. 미국주식: 사용자의 장기 자산운용 분석과 의사결정 보조, 실제·가상 의사결정 성과 비교.
3. 한국주식: 전략 검증용 Paper Trading을 시작으로 충분한 검증 후 제한적 자동매매.

공통 원칙:

- LLM은 계산 엔진이 아니다. 금융 수치의 authoritative source는 검증 가능한 코드와 그 입력 데이터다.
- Domain Logic과 Infrastructure, Configuration과 Business Logic을 분리한다.
- AI, Market Data, Broker Provider를 각각 추상화한다.
- 가상계좌와 실제계좌는 공통 Domain을 최대한 공유하되, 잔고·거래·실행 권한은 격리한다.
- 미국 실제 포트폴리오의 주문은 AI가 자동 실행하지 않는다.
- 한국 주문은 반드시 Strategy → Risk → Execution → Broker 순서로 처리한다.
- AI가 Portfolio Policy를 임의로 변경하거나 Risk Limit을 우회할 수 없다.

### 개인 예산의 금융·데이터 계약 — 후속 구현 요구사항

첫 구현은 **개인 1명, KRW, 한 달**의 수동 입력으로 한정한다. 월 합계와 별도로 급여 입금일·납부일·목표 납입 가능일에 따른 날짜별 가용현금을 계산한다. 금액은 유한한 `Decimal`로 다루고 평가·기록 시점, 통화, 출처를 보존한다. 출처와 환율 시점이 없는 다른 통화 금액은 합산하지 않는다. 누락은 숫자 0과 다르다. 완전한 입력에서 확인된 부족액은 금액과 원인을 보여주고, 필수 입력이 없으면 판단 불가와 필요한 정보를 보여준다. 적자를 자동 대출, 주식 매도 또는 비상자금 해제로 메우지 않는다.

- 세전 소득과 실수령 소득을 구분한다. 실수령액에서 이미 공제된 세금·보험료 등을 다시 지출로 차감하지 않는다. 실제 입금, 확정된 예정 수입, 불확실한 수입을 구분하며 불확실한 성과급은 확정 배정의 재원으로 삼지 않는다. 기존 현금 잔액은 소득이 아니고, 미실현 투자이익이나 대출금도 소득이 아니다.
- 본인 계좌 간 이동과 투자계좌 입출금은 연결된 이동으로 표현하여 개인 전체의 소득·소비를 만들지 않는다. 카드 사용 시 소비를 인식하고 카드대금 지급 시 현금흐름을 인식하되 같은 소비를 두 번 합산하지 않는다. 부채 원금 상환과 이자·수수료를 분리하여 납부 현금, 소비, 순자산 변화의 의미를 섞지 않는다.
- 목표에는 유형·현재까지의 보호 잔액·우선순위와 실제 납입 가능일을 둔다. 금액·기한은 미정일 수 있으며, 이때 필요 적립액을 0으로 만들지 않고 `UNKNOWN`과 필요한 입력을 반환한다. 금액·기한이 있으면 이번 기간 필요 적립액을 계산한다. 미래 투자수익을 목표 달성 재원으로 임의 가정하지 않는다. 기존 비상자금·목표자금 잔액과 신규 적립액을 구분하고 같은 돈을 목표 사이에 중복 배정하지 않는다. 저축·투자 예산 배정은 용도 **예약**이며 실제 이체 완료나 자산 취득이 아니다.
- 월초 원안과 월중 잔여 예산을 구분한다. 이미 소비·납부·배정한 금액을 재계산에서 다시 가용 재원으로 놓지 않는다. 기간별 잔여 현금과 전체 월간 미배정액·부족액을 별도로 설명한다.

생활비 상·하한, 비상자금 목표, 목표저축 우선순위, 미국·한국 투자 배분 비율, 초과지출 조정과 월 이월 규칙은 **사용자 소유 설정**이다. 실제 사용자 값이 없는 현재는 미설정이며, 가상 예제 값은 테스트 입력일 뿐 승인이 아니다. 초기 계산은 명시적 규칙을 적용하여 배정액·미배정액·부족액을 드러낸다. 임의 최적화 함수로 생활 수준이나 목표 순서를 바꾸지 않는다.

목표·보호자금 정책이 미정이면 확인된 현금흐름과 목표 설계에 필요한 정보를 나눠 보고한다. 전체 잔액을 확정된 투자 가능액으로 제시하지 않는다. 아래 50/15/25/10 및 네 자산군은 현재 미국 Policy 개발 사례이며 개인화된 주택·노후 투자 추천에 자동 적용하지 않는다. 범용 전략 엔진으로 전면 재작성하는 결정도 아니다.

### 사용 경로 — 향후 제품 요구사항

모바일·PC 대응 **웹앱이 주 사용 경로**이고, 텔레그램은 알림과 허용된 간단한 조회에 한정한다. 초기 계산·보고 프로그램은 맥미니에서 실행한다. 브라우저와 텔레그램 연결의 수명은 계산·기록 프로그램의 수명과 분리한다. 초기에는 로컬 접근을 검증하고 인증·원격접속·장애 복구는 별도로 설계·검증한다. 웹 프레임워크는 미정이다. 이 요구가 네이티브 앱, 공개 배포, 텔레그램 금융 승인, 자동 송금·실주문 권한을 뜻하지 않는다.

예산 초안, 인간 승인본, 실제 사용액, 수정 제안은 별도 상태다. 재계산은 승인본·과거 입력·과거 결과를 덮어쓰지 않는다. 승인된 월 투자예산의 잔여액과 실제 가용현금은 각각 충족해야 하는 제약이다. 한국 월 **추가배정** 예산, 한국 계좌 **운용자본**, 주문·손실 한도는 다른 값이며 월 배정액을 매매 회전 한도로 해석하지 않는다. BUD-03에서 예약·완료·취소·만료의 중복 배정 방지와 실제 승인 경계를 검증한다. 예산 승인은 송금·환전·주문 권한이 아니다. 실제 이동은 관측·대사되기 전까지 완료로 표시하지 않는다. PAPER/SHADOW 가상 자금은 개인 실제 현금을 소비하지 않는다. 미국 실제 자동주문 금지와 한국 단계별 검증·승인은 그대로 유지한다. AI는 코드 계산 결과를 설명하고 수정안을 제안할 수 있으나 승인 정책·보호자금·Risk 한도를 직접 변경할 수 없다.

첫 구현에서 은행·카드 API, Toss 연동, 세금 계산, 대출 최적화, 다중통화 예산, 실시간 결제 차단, 자동 송금·환전·주문은 제외한다. Toss 증권 API가 급여·은행·카드 내역을 제공한다고 가정하지 않는다. 구현 순서와 검증 조건은 [BUD-01~04](docs/ROADMAP.md#budget--cashflow-planning-확장)에서 관리한다.

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

초기 값은 `config/us_portfolio_policy.toml`에 선언한다. 비율 단위는 percentage points로, `50`은 50%를 뜻한다. 현재 네 자산군과 50/15/25/10은 개발 중인 미국 Policy 지원 사례이며, 개인별 주택·노후 목표의 승인된 최적 배분이나 범용 투자 전략이 아니다. 향후 코드가 이 설정을 읽고 검증하며 수치를 Business Logic에 hard coding하지 않는다. 정책 요구사항과 초기 설정 값은 함께 검토·변경한다.

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
- AI / Broker / Market Data Provider는 별도 adapter와 내부 계약으로 연결한다. Market Data의 첫 adapter는 Twelve Data이며 AI·Broker 제공자는 미결정이다.
- 가상·실제 계좌가 공통 Domain을 사용하되 execution mode와 계좌 식별은 명시적으로 분리한다.
- FastAPI와 Streamlit은 실제 필요성이 생기기 전까지 추가하지 않는다.

현재 라이브러리 API와 테스트는 계좌·거래 저장 및 현재 USD 계좌 분석을 제공하지만, 실제 계좌 자료를 안전하게 입력·대사하는 사용자 경로, 결과를 전달하는 화면·보고서, 운영 스케줄·감시·백업은 아직 제공하지 않는다. 미국 자산 상태를 실제로 사용할 수 있으려면 입력 주체와 형식, 중복·정정·대사 규칙, 가격·FX 사용 권리와 freshness, 출처·시각·누락을 표시하는 최소 보고 경로를 정하고 검증해야 한다. 이 연결 계획은 ROADMAP의 M1에 추적한다. 계좌 식별 및 자료 반입 방식은 아래 Open Decisions에서 정한다.

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

작업 시작 시 [OpenAI 공식 모델 문서](https://developers.openai.com/api/docs/models)와 [Codex 코드 생성 안내](https://developers.openai.com/api/docs/guides/code-generation)에서 실행 시점의 최신 Codex 가용 모델을 확인한다. 아래 모델명은 현재 기준이며 향후 낡을 수 있다. 실제 선택은 비용·속도보다 작업의 위험도와 복잡도를 우선한다.

| 업무 | 사용 원칙 |
| --- | --- |
| 복잡한 구현 기본 | GPT-6 Sol / High |
| 중요한 Architecture / 금융 구조 검토 | GPT-6 Sol / XHigh |
| Backtest Integrity Audit | GPT-6 Sol / XHigh 또는 Max |
| Broker / Execution Safety Audit | GPT-6 Sol / XHigh 또는 Max |
| 실제 자금 연결 전 최종 Safety Audit | GPT-6 Sol / XHigh 또는 Max |
| 반복적이고 범위가 좁은 작업 | 필요 시 GPT-6 Luna 사용 가능 |

AI끼리의 합의는 검증 증거가 아니다. 테스트·CI·실행 결과를 우선한다. 이 표는 개발 작업의 모델 운용 원칙이며, 제품에서 사용할 AI Provider·모델 선택은 별도 Open Decision이다.

## 14. Phase 0 산출물과 제외 범위

산출물: README, 이 명세, Architecture, Roadmap, `.gitignore`, `.env.example`, `pyproject.toml`, `src/asset_copilot/`, `tests/`, 기본 정책·가상 자금 선언용 `config/`.

`domain`, `portfolio`, `market`, `research`, `risk`, `strategy`, `execution`, `broker`, `agents`, `storage`, `reports`는 향후 논리적 모듈이다. 실제 구현이 필요할 때 패키지를 생성한다. `scripts/` 역시 실행할 도구가 생길 때 생성한다. 빈 Python 파일을 미리 대량 생성하지 않는다.

이번 Phase에서는 다음을 구현하거나 의존성으로 추가하지 않는다: OpenAI API, LLM Agent, Market Data API, 증권사 API, 실제 주문, 자동매매, Portfolio Calculator, DB Schema, SQLAlchemy, Backtesting, Technical Indicator, Dashboard, FastAPI, Streamlit, Scheduler.

기본 설정 loader·validator도 이번 Phase에 만들지 않는다. 런타임 dependency는 없고 개발용 pytest와 패키지 빌드용 setuptools만 선언한다. 자동 commit / push는 하지 않는다.

## 15. Open Decisions

아래 항목은 구현 직전 관련 Phase에서 인간과 결정하고 이 문서를 갱신한다. 값이나 계약이 정해지기 전 임의의 운영 기본값으로 활성화하지 않는다.

| ID | 미결정 사항 | 결정 시점 |
| --- | --- | --- |
| OD-01 | Phase 1 확정: Decimal만 사용, 중간 통화 반올림 없음, 이동 가중평균 원가, 매수 수수료 원가 포함·매도 수수료 실현손익 차감, 불투명 문자열 ID, 시간대가 있는 금융 이벤트 시각과 계좌별 기록 sequence. Phase 3 현재 분석에는 명시적 `evaluated_at`과 개별 quote `as_of`를 보존한다. 미결정: 표시·Broker·세금 반올림, 역사적 성과용 FX·가격 시점 기준, 추가 기업행사 | Phase 1·3 일부 확정; 나머지는 해당 Phase에서 결정 |
| OD-02 | 자산·Sector 분류와 ETF look-through, 비중 분모, Risk 한도 적용 대상, 경계값 포함 여부, 리밸런싱 트리거·거래 우선순위, 위반 상태 복구, 인간 Policy 변경 승인·버전 적용 방식 | Phase 4; Shadow 실행 전 |
| OD-03 | Benchmark 자산, 초기 자본·입출금 대응, 배당 재투자, TWR/MWR 등 수익률 기준, 비교 통화·기간·체결 가정, Sharpe 무위험 수익률·연율화, 집중도 정의 | Phase 3–5 |
| OD-04 | Phase 2 확정: 첫 Market Data adapter는 Twelve Data, 내부 계약은 provider-neutral, 가격·FX quote의 출처·통화·시점 및 오류 경계 정의. 미결정: 데이터 라이선스·지연·수정주가·상장폐지 종목·point-in-time coverage의 투자용 적합성, 투자용 freshness threshold, AI Provider·모델과 개인정보 전송 범위 | Market Data 일부 Phase 2 확정; 투자 사용 전 데이터 검증, AI: Phase 7 |
| OD-05 | 한국 시장 Commission·Tax·Slippage, 체결·호가·유동성·Partial Fill 모델, Market Hours, 결제·가용 현금 규칙, Position/Daily Loss Limit 수치·기준 | Phase 8; Phase 9–10 전에 검증 |
| OD-06 | Phase 1 확정: 4개 Repository 계약, SQLite 4개 테이블·거래 불변 트리거, Decimal TEXT 저장, Ledger append의 `BEGIN IMMEDIATE` 검증·저장. 미결정: Schema migration, 장기 동시성·성능, PostgreSQL 이전 기준 | Phase 1 일부 확정; 저장 요구 확장 시 보완 |
| OD-07 | 주문·Risk 승인 계약, idempotency key, 동시 주문 시 자금 예약, 승인 유효성 재검사, 재시도·대사·중단·복구, Broker Provider와 capability·계좌 권한 | Phase 8; Phase 12 연결 전 Safety Audit |
| OD-08 | 전략 평가 기간·승격 기준·허용 손실, 단계별 인간 승인, 실전 계좌 ID, 자금 한도의 정의, 증액·감액·중단·rollback 기준 | Phase 10; Phase 13 자금 연결 전 확정 |
| OD-09 | Journal/Thesis 버전·보존·검토 일정, AI 제안 채택·보류·거절의 표현, 개인정보 보관과 삭제 | Phase 6–7 |
| OD-10 | Backtest 전략·universe·검증 구간·재현 규칙·과적합 통제, 데이터 불완전 시 실험 제외 기준 | Phase 9 |
| OD-11 | Dashboard 기술, Daily/Weekly Report 전달 수단·일정·Scheduler 필요성 | Phase 11 |
| OD-12 | 의존성 lock·재현 가능한 개발 환경 및 CI·지원 Python 버전 조합 | 후속 개발 환경 확장 시 |
| OD-13 | 실제 미국 계좌 거래·보유 자료의 입력 방식, 계좌 식별·정정·중복·대사 및 누락 처리, 사용자에게 전달할 최소 보고 형식·채널·주기 | M1 연결 설계; Phase 4 완료 조건을 낮추지 않음 |
| OD-14 | 한국 Broker 후보(Toss 포함)의 실제 API·조회/모의/주문 capability, 인증·약관·데이터 권리, 거래 주기와 운영 가능 시간 | Phase 8–12 설계; 실주문은 Phase 13 승인 후 |
| OD-15 | 사용자 소유 예산 정책의 실제 금액·상하한·비상자금 목표·저축 우선순위·투자 비율·초과지출 조정 및 월 이월 규칙. 가상 예제는 승인 값이 아님 | BUD-01 입력 계약 확정 전 |
| OD-16 | 개인 재무 내역의 수동 입력 형식, 카드·부채·계좌 이동 연결 식별자, 정정·환불·중복 제거·개인정보 보관과 백업/복원 기준 | BUD-01 최소 입력, BUD-02 저장 설계 전 |
| OD-17 | 예산 승인 주체·기록, 자금 예약의 원자성·만료·취소·대사, 실제 가용현금과 투자 Policy/Risk 연결 조건 | BUD-03 및 실제 자금 연결 전 |
| OD-18 | 주택·노후 목표금액·시점, 손실 감당 범위와 개인화 투자 전략. 미정 목표는 적립액 UNKNOWN으로 두고 기존 미국 Policy 예시를 자동 추천하지 않음 | 목표 설계 및 개인화 투자 판단 전 |
| OD-19 | 웹 프레임워크, 로컬 접근·인증·원격접속·복구, 텔레그램 허용 조회 범위와 개인정보 보호 | 사용자 웹·알림 연결 설계 전 |

## 16. Phase 0 완료 기준

- 기존 Repository 상태를 확인한 후 필요한 파일만 생성한다.
- 최소 패키지를 개발 환경에 설치하고 pytest smoke test를 통과한다.
- 초기 Policy 설정과 KR 가상 자금 선언이 이 명세와 일치한다.
- 문서 간 로드맵·안전 경계·미구현 범위의 충돌을 검토한다.
- 변경 파일, 테스트 결과, Git 상태, Phase 1 권장 범위와 미결정 사항을 보고한다.

## 17. Phase 1 Portfolio Foundation 계약

Portfolio는 운용 목적 또는 전략 단위이며 `id`, `name`만 가진다. Account는 Ledger와 잔고의 독립 경계이며 하나의 Portfolio에 속한다. 여러 Account가 한 Portfolio에 속할 수 있다. `REAL`, `SHADOW`, `PAPER`, `BENCHMARK` 유형과 `USD`, `KRW` 통화를 지원한다. 특정 Portfolio ID에 계산 규칙을 묶지 않는다.

**Transaction Ledger가 Source of Truth**다. Account에 현금·평가액·손익을 authoritative persisted field로 두지 않는다. `DEPOSIT`, `WITHDRAW`, `BUY`, `SELL`, `DIVIDEND`는 불변 이벤트다. `executed_at`은 시간대가 있는 실제 금융 이벤트 시각이며 Accounting replay의 첫 번째 정렬 키다. 각 Account의 양의 연속 `sequence`는 안정적인 기록 순번이자 동일 시각의 tie-breaker다. Ledger 전체의 sequence 완전성·유일성을 먼저 확인한 다음 `(executed_at ASC, sequence ASC)` 순으로 재생한다. 늦게 발견된 과거 거래는 다음 sequence로 추가할 수 있지만, 전체 금융 이력을 재생했을 때 모든 불변식이 성립해야 저장한다. 과거 이벤트 수정·삭제 대신 향후 correction/reversal event 확장을 검토한다. 현재 correction 기능은 없다.

현금 이벤트에는 양수 `amount`를 사용한다. `DEPOSIT`과 `WITHDRAW`는 자산 없이 기록하며 `DIVIDEND`는 지급 자산 ID를 요구하고 원가를 바꾸지 않는다. 거래에는 양수 Decimal `quantity`와 `price`, 음수가 아닌 Decimal `fee`를 쓴다. BUY에 필요한 현금은 `quantity × price + fee`이며 수수료를 취득 원가에 포함한다. SELL은 보유량을 초과할 수 없고, 당시 이동 평균 원가로 처분 원가를 배분한다. 실현손익은 `매도금액 − 처분 원가 − 매도 수수료`다. 전량 매도하면 수량·잔여 원가를 정확히 0으로 정리한다. 입금 없이 초기 잔고를 생성하지 않는다. 따라서 `KR_PAPER`의 선언된 10,000,000 KRW도 향후 실제 사용 시에는 `DEPOSIT` 이벤트로 기록해야 한다.

금액·가격·수량·원가·손익은 모두 Decimal이다. SQLite에는 소수 값을 `TEXT`로 직렬화해 부동소수 변환 없이 왕복한다. 덧셈·곱셈은 입력 자릿수에 맞는 충분한 정밀도로 처리한다. 나눗셈은 유한소수 결과를 보존할 수 있는 계수 자릿수 기준을 사용하며, 무한소수일 때 최소 80 유효숫자와 `ROUND_HALF_EVEN`을 사용한다. 반복 부분 매도의 소수 지수를 유효숫자로 다시 더해 정밀도가 지수적으로 증가하지 않도록 한다. 이 내부 나눗셈 경계는 cents 반올림이나 세금 규칙이 아니다. 부분 매도 후 남은 원가는 이전 원가에서 배분 원가를 뺀 값으로 유지한다. 현재 context뿐 아니라 mutable `DefaultContext`의 변경도 계산에 영향을 주지 않는다. 표현 범위를 벗어나면 Overflow/Underflow를 조용히 허용하지 않는다.

수동 asset_id→Decimal 가격 mapping으로 현재 보유 Position의 시장가치·미실현손익·계좌 총가치·Position Weight·Cash Ratio를 계산한다. 미실현손익은 실현손익과 분리한다. 열린 Position의 asset_id 가격이 빠지면 평가를 거부하며, 추가 가격은 허용한다. Ticker는 표시 정보이며 같은 ticker의 서로 다른 Asset도 각각의 ID로 평가한다. 계좌 총가치가 0이면 Cash Ratio는 정의되지 않아 `None`이다. Provider symbol/ticker를 Domain Asset ID로 연결하는 작업과 가격 데이터의 신선도·시점은 Phase 2에서 다룬다.

Phase 1의 Cost Basis는 **Portfolio Analytics용 이동 가중평균**이다. 미국 세금 신고용 Tax Lot 회계로 간주하지 않는다. FIFO·Specific Identification·Broker statement 기준은 미래 Tax/Lot Engine의 범위다. Asset은 STOCK·ETF만 나타내며 Cash는 별도 자산이 아니라 계좌 Ledger의 파생 상태로 둔다. FX 변환도 수행하지 않고 다른 통화의 거래·자산을 거부한다.

Repository 계약은 Domain 측에 두고 SQLite adapter는 이를 구현한다. 저장소는 새 거래를 계좌별 Ledger와 함께 검증한 뒤 원자적으로 추가한다. 현재 Schema는 최초 버전이며 마이그레이션 도구나 PostgreSQL 구현은 없다. 이 Foundation은 수동으로 기록한 거래를 계산하기 위한 것이며 실제 주문을 실행하지 않는다.

Phase 1 감사 보완: `executed_at` 정렬 시 UTC의 실제 시각을 비교하여 DST 중복 시간의 순서와 저장 전후 재생 결과를 일치시킨다. Asset mapping의 키는 연결된 `Asset.id`와 같아야 한다. SQLite append는 INSERT뿐 아니라 COMMIT 실패와 실행 중단에도 rollback하고, adapter 연결에서는 recursive trigger를 활성화하여 `INSERT OR REPLACE`의 삭제 단계에도 Ledger 불변 트리거가 적용되게 한다.

## 18. Phase 2 Market Data 계약

`MarketDataProvider`는 복수 Asset의 최신 가격을 `asset_id → MarketQuote`로 돌려주고, 방향이 명시된 `FxQuote`를 조회하는 provider-neutral 계약이다. Portfolio Domain의 canonical identity는 계속 `asset_id`다. Twelve Data adapter에 전달하는 `asset_id → (provider symbol, exchange)` mapping은 명시적으로 등록하며, Asset.ticker에서 암묵적으로 생성하지 않는다. 첫 adapter는 Twelve Data의 미국 USD 주식·ETF `/quote`와 통화쌍 `/exchange_rate`를 사용한다. API key는 `TWELVE_DATA_API_KEY` 환경변수에서 읽을 수 있으며 HTTP Authorization 헤더로 전송한다. URL·코드·설정·테스트에 실제 키를 저장하지 않는다.

`MarketQuote`는 asset_id, 양의 유한 Decimal 가격, 통화, `as_of`, `fetched_at`, 출처를 가진다. `FxQuote`는 기준 통화 1단위당 상대 통화 단위의 양의 유한 Decimal 환율과 같은 시점·출처 정보를 가진다. 예를 들어 USD/KRW 1370은 1 USD = 1370 KRW다. `as_of`는 제공자가 확인한 시장 가격의 기준 시각이며 제공하지 않으면 `None`이다. `fetched_at`은 시스템 조회 시각이다. 둘은 시간대가 있어야 하며 UTC로 정규화한다. Twelve Data `/quote`는 `interval=1min`으로 조회한다. `close`가 속한 1분 캔들의 시작을 나타내는 `timestamp`와 마지막 1분 캔들을 나타내는 `last_quote_at`이 모두 존재하고 같을 때만 이 보수적인 캔들 기준 시각을 `as_of`로 사용한다. 하나라도 없거나 다르면 `as_of=None`이다. 이는 마지막 개별 거래의 정확한 시각을 뜻하지 않는다.

신선도는 quote에 영구 boolean으로 저장하지 않는다. 호출자가 제공한 평가 시각과 `max_age`로 순수 판정하며, 미상 또는 미래의 `as_of`는 stale로 판정한다. 투자용 age threshold와 장 마감·FX별 정책은 미결정이다. 인증·한도·잘못된 symbol·응답 손상·네트워크·시간 초과는 adapter의 명시적 오류로 격리하며 mock 가격으로 자동 대체하지 않는다. 숫자는 JSON에서 float를 경유하지 않고 Decimal로 읽으며 길이·크기를 제한한다. Phase 1의 `value_at_prices()`는 변경하지 않는다. Phase 3 orchestration이 quote currency·시점·신선도를 검증하고 `{asset_id: Decimal price}`를 넘긴다. Market Quote 저장 테이블과 과거 데이터 엔진은 Phase 2에 추가하지 않았다.

## 19. Phase 3 현재 미국 계좌 분석 계약

`application.USPortfolioAnalyzer`는 Account·Transaction·Asset Repository와 MarketDataProvider를 주입받아 **한 USD Account**의 Ledger를 재생한다. Portfolio ID 또는 계좌명을 계산 규칙에 하드코딩하지 않는다. 열린 Position의 Asset ID로 가격을 조회하고, quote의 ID·통화·양의 Decimal 가격·출처·`as_of`를 검증한 뒤 기존 `value_at_prices()`에 가격 mapping을 전달한다. USD/KRW FX의 방향·양의 Decimal 환율·출처·`as_of`도 확인한다. 필요한 quote 또는 FX가 누락되거나 기준 시각을 알 수 없거나 미래·stale이면 현재 평가를 거부한다. `max_quote_age`와 `max_fx_age`는 호출자가 명시하며 실제 운영 임계값은 OD-04에 남긴다. 거래가 `evaluated_at` 이후에 실행되었다면 그 평가를 거부한다.

불변 `PortfolioAnalysis`에는 UTC `evaluated_at`, 현금·투자자산·계좌 USD 평가액, 남은 취득 원가, 거래 실현·미실현손익, Position별 수량·평균원가·가격·가치·비중, 현금·STOCK·ETF 노출, 직접 분류된 STOCK Sector 노출과 미분류 STOCK·ETF 평가액, 개별 quote 및 FX의 출처·`as_of`·`fetched_at`, 적용한 freshness 한도와 통과 상태를 담는다. 전부 USD 계좌 자산이므로 USD 노출은 계좌 총가치의 100%로 표현하되 0 가치 계좌의 비율은 정의하지 않는다. `trading_pnl = trading_realized_pnl + unrealized_pnl`은 **거래 손익**으로만 해석한다. DIVIDEND는 Ledger 현금을 늘리지만 이 값에는 포함되지 않는다. 이를 총 투자수익률이나 세후 성과로 표시하지 않는다.

Direct Sector Exposure는 Sector가 명시된 STOCK의 직접 평가액만 합산한다. ETF의 Sector 필드가 있더라도 구성종목 look-through로 취급하지 않는다. USD/KRW 환산은 `USD 계좌 평가액 × USD/KRW 환율`의 KRW **보고 값**이며 USD Ledger 원가를 바꾸거나 FX PnL을 계산하지 않는다. 분석용 개인 거래·보유 정보와 로컬 DB는 Git에 저장하지 않는다. `data/`는 ignore 상태를 유지한다. NYSE/Nasdaq 휴장일을 반영하지 않는 단순 elapsed-time freshness는 정상 종가도 stale로 거절할 수 있으며, calendar-aware 정책은 후속 결정이다.

Phase 3는 현재 상태 분석이다. 과거 가격·계좌 snapshot 이력이 없으므로 연율수익률·CAGR·Drawdown·Volatility·Sharpe·장기 Benchmark 비교는 계산하지 않는다. Benchmark 선택, 배당 포함 수익률, 현금흐름 조정 및 역사적 성과 방법론은 OD-03의 Open Decision으로 남긴다. AI·Broker·주문·리밸런싱 기능도 없다.

### Phase 3 감사: 시점·관측·오류 계약

- `evaluated_at`은 호출자가 현재 분석 시작 시점에 지정하는 **Ledger cutoff 및 freshness 기준 시각**이다. 조회 완료 시각이나 역사적 point-in-time 보장을 뜻하지 않는다. `as_of <= evaluated_at`과 `as_of <= fetched_at`을 요구하지만, 호출 후 fetch가 끝날 수 있으므로 `fetched_at <= evaluated_at`은 요구하지 않는다. `fetched_at`을 가격 시각으로 대체하지 않는다. 과거 evaluated_at을 입력해도 당시 알려져 있던 정보의 재현을 보장하지 않으며, historical analytics에는 별도 observation availability·revision·Ledger snapshot 계약이 필요하다. Provider clock의 실제 정확성은 adapter 책임이며 임의의 clock-skew 허용치를 만들지 않는다.
- 검증에 사용한 불변 Quote 자체를 보존하여 가격과 provenance를 같은 observation에 묶는다. Provider의 반환 mapping이 이후 갱신되어도 분석 결과의 출처·시각이 바뀌지 않는다. 요청하지 않은 extra quote는 무시하며 필수 quote의 누락은 계속 거부한다.
- 빈 계좌도 현재 결과 계약상 유효한 USD/KRW 환율과 provenance를 제공하므로 FX 조회·검증을 수행한다. 0 USD = 0 KRW라는 산술에 환율이 필요한 것은 아니다. FX 장애 시 빈 계좌 분석도 실패하는 제약을 유지하며, 환율을 1 또는 0으로 꾸미지 않는다. 향후 FX 없는 분석을 지원하려면 환율·출처·freshness의 부재를 명시하는 별도 계약이 필요하다.
- Direct Sector의 비중 분모는 **현금을 포함한 계좌 총가치**다. 직접 분류 STOCK + 미분류 STOCK + ETF 평가액은 투자자산 평가액과 일치한다. `usd_exposure`는 계좌 평가 통화의 비중이며, 기업 매출 통화나 ETF 내부 자산의 경제적 FX 노출을 측정하지 않는다.
- 각 exposure는 해당 평가액 / 계좌 총가치다. 금액 합계는 정확하게 보존하지만 순환소수 비율은 17절의 Decimal 나눗셈 정밀도를 따르므로 비율 합계의 미세한 잔차는 가능하다. 합계를 1로 만들려고 특정 분류의 비중을 임의 보정하지 않는다. Policy 경계값 비교 방식은 OD-02에서 정한다.
- Provider의 `MarketDataError` 하위 오류는 원인을 보존하여 그대로 전파한다. 계좌·관측의 의미 검증 실패는 `AnalysisError`, Ledger 불변식 위반은 기존 replay의 `ValueError`다. Repository의 저장소 장애는 그 계층의 오류로 전파한다. 실패 시 부분 분석이나 가상 가격을 반환하지 않는다.
