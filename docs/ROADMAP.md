# Development Roadmap

[PROJECT_SPEC.md](../PROJECT_SPEC.md)가 제품·금융 계약을 정의한다. 이 문서는 Phase 순서·범위·완료 조건을 정의하고 [STATUS.md](STATUS.md)는 현재 증거를 기록한다. **Phase 0~3은 main에서 완료**, Phase 4 US Portfolio Policy는 미병합 후보가 검토 중이며 **IN REVIEW / NOT DONE**이다. 단계 완료는 자동 자금 투입 승인을 뜻하지 않는다.

| Phase | 주제 | 권장 범위와 완료 조건 |
| --- | --- | --- |
| 0 | Project Bootstrap / Architecture | 완료. 최소 패키지·설정 선언·핵심 문서·pytest 환경 |
| 1 | Portfolio Foundation | 완료. 공통 포트폴리오·계좌·자산과 Ledger 재생, Decimal 계산·수동 가격 평가, SQLite 저장·재조회 및 테스트 |
| 2 | Market Data | 완료. Provider 계약과 Twelve Data 가격·FX 정규화, 출처·시각·stale 판정·오류 격리의 오프라인 검증 |
| 3 | US Portfolio Analytics | 완료. 현재 USD 계좌 평가·거래손익·비중·직접 Sector 노출·KRW 보고 환산, quote/FX 신선도 및 출처 검증. 역사적 성과와 Benchmark 방법론은 OD-03에 유지 |
| 4 | US Portfolio Policy | 인간 소유 설정 loader/validator, 범위·집중도·Risk 평가. Policy 변경 이력·권한·경계값 검증 |
| 5 | US Shadow Engine | POLICY/AI Shadow의 독립 가상 상태·체결과 Benchmark 비교. 현금흐름·비용·판단 시점 일관성 검증 |
| 6 | Research / Investment Thesis | Thesis 필드·상태·이력, Research 근거, Decision Journal과 후속 Review의 기록 기반 |
| 7 | AI Asset Copilot | AI Provider 추상화, Research·Thesis·Risk 해석과 제안. 코드 계산 결과 인용, Policy 쓰기·Broker 접근 차단 검증 |
| 8 | KR Paper Trading | 10,000,000 KRW 가상 계좌, Strategy/Risk/Execution/Broker 계약과 PaperBroker. 비용·체결·거절·중복·한도 검증 |
| 9 | KR Strategy / Backtest | 전략과 재현 가능한 Backtest, 데이터 시점·종목 집합·Entry/Exit·비용 검증. Backtest Integrity Audit |
| 10 | KR Live-market Paper Trading | Backtest를 거친 전략을 실시간 시장 조건에서 가상 실행. 성과·운영 안정성·손실·중단 기준 평가 |
| 11 | Dashboard / Daily / Weekly Report | 검증된 수치·제안·Journal Review의 화면과 보고서. UI·전달 수단·스케줄 필요성 결정 |
| 12 | Broker Integration | Provider 선정, 조회·sandbox·paper 연결, 인증·오류·대사·권한 검증. Broker / Execution Safety Audit. 실주문 활성화 없음 |
| 13 | Limited KR Live Trading | 최종 Safety Audit·인간 승인 후 1,000,000 → 3,000,000 → 5,000,000 → 최대 10,000,000 KRW. 각 단계 별도 검증·승인 |

## 순서와 단계 간 의존성

Phase 8은 Paper Trading 기반을 개발하는 단계다. 전략의 실제 검증 순서는 **Backtest → Live-market Paper Trading → 제한적 실전**이며, Phase 9와 Phase 10을 건너뛰지 않는다. 정량적 승격·중단 기준은 OD-08에서 확정하고, 성능이 확인되기 전 실제 주문 기능을 활성화하지 않는다.

Phase 5의 AI Shadow는 저장되거나 수동 제공된 제안으로 실행 계약을 검증할 수 있다. 실제 AI Provider 연결은 Phase 7이다. Phase 6의 1/3/6개월 Review 기록 요구는 Scheduler 도입을 강제하지 않는다. 자동 일정은 필요할 때 Phase 11에서 결정한다.

Phase 12에 Broker credentials나 adapter가 존재해도 실주문 권한을 의미하지 않는다. 실전 주문 활성화는 Phase 13에서 다룬다. 미국 실제 포트폴리오는 전체 로드맵에서 분석·의사결정 보조 대상으로 유지한다.

## 사용자 도달점과 실제 사용 경로 — R0 계획 제안, 승인 대기

아래 도달점은 Phase 0–13을 대체하는 상태 체계가 아니다. 사용자 결과가 내부 API만으로 달성됐다고 판단하지 않도록 입력·대사·보고·운영 연결을 추적한다. **M1의 최소 보고를 Phase 11 전체보다 앞서 설계·구현하는 순서 조정은 승인 대기**다. 이유는 현재 분석 API만으로 실제 자산을 지속해서 입력·확인할 수 없기 때문이다. 영향은 Phase 4의 기존 완료 조건을 줄이는 것이 아니라, Phase 1–4 산출물을 사용자가 확인할 수 있는 입력·보고 경로와 연결하는 추가 작업이다. Phase 11의 Dashboard/Daily/Weekly Report 전체 범위는 유지한다. Phase 4의 미해결 기준이 닫히기 전 Phase 5의 실질 구현은 시작하지 않는다.

| 도달점 | 사용자 결과 | 기존 Phase 및 선행 연결 |
| --- | --- | --- |
| M0 기준선 정리 | 같은 원격 코드와 테스트·CI 증거로 개발·검토 | R0 문서/CI. Policy 후보는 main과 별도 유지 |
| M1 미국 자산 상태 보고 | 실제 입력을 검증·대사한 현재 평가와 Policy 결과를 출처·시각·누락과 함께 확인 | Phase 1–4의 Ledger/SQLite, Market Data, Analytics, Policy. OD-13의 입력·정정·중복·대사와 최소 보고 경로, OD-04의 시세 권리·신선도 결정 필요. Policy 결과는 P4 gate 이후 |
| M2 미국 장기투자 비서 | 보유기업 근거·Thesis·Journal·AI 해석과 가상 비교 | Phase 5–7. Phase 5 Shadow와 Benchmark를 유지하고 OD-03 비교 방법론 및 당시 자료 보존 필요. 미국 실제 주문 없음 |
| M3 한국 검증된 모의운영 | 재현 가능한 전략 검증 후 실시간 가상 자동매매 | Phase 8–10의 Paper → Backtest → Live-market Paper 검증. Phase 12의 Broker API 가능성 조사·읽기 전용 검증은 OD-14 의존성으로 조기 확인 가능; 실주문 활성화 아님 |
| M4 통합 운영 준비 | 보고·감시·알림·권한·재시작·대사·백업 복구 | Phase 11–12의 보고와 Broker 안전 감사. 기본 비밀 관리·장애 기록·대사는 앞선 단계부터 필요; 운영 완료 조건과 채널은 설계·검증 필요 |
| M5 제한 한국 실거래 | 사전 승인 범위의 실제 자동매매와 운영 기록 | Phase 13의 최종 Safety Audit, 독립 Risk gate, 인간 승인, 기존 단계별 금액 제한·중단 기준 필요 |
| 지속 운영 | 정기 점검·변경 재검증·실패 전략 중단·개선 | v1 이후 운영. 추가 자금·전략은 별도 승인 |

현재 main의 `SQLiteStore`/Repository는 프로그래밍 입력 경로, `TwelveDataMarketDataProvider`는 외부 가격·FX 관측 adapter, `USPortfolioAnalyzer`는 프로그래밍 분석 경로다. 사용자용 import/계좌 대사/보고 실행기는 아직 없다. 각 도달점은 실제 입력과 실패 처리, 결과 전달, 운영 증거가 있을 때 확인한다.

## Phase 1 권장 구현 범위

Phase 1 구현 기준과 완료 검증 범위의 기록이다. OD-01과 OD-06 중 Foundation에 필요한 결정을 해결했다.

1. 포트폴리오·계좌·자산·통화·거래·포지션의 최소 Domain과 식별 규칙을 정한다. 다섯 초기 Portfolio ID를 지원하고 계좌별 상태를 분리한다.
2. 금액·수량의 Decimal 정밀도와 반올림, Cost Basis·Average Price·Realized/Unrealized PnL의 기준, 거래 시간과 평가 시점을 결정한다.
3. 수동 입력 또는 테스트 fixture의 거래·가격으로 현금, 보유 수량, 원가, 기본 평가와 손익을 코드로 계산한다. 외부 가격·FX API는 Phase 2에서 연결한다.
4. Repository 계약과 최소 SQLite Schema를 결정하고 저장·재조회·트랜잭션의 일관성을 검증한다. ORM 필요성은 별도로 판단한다.
5. 입출금·매수·매도·수수료·소수 수량·잘못된 입력·계좌 간 격리와 저장 왕복을 테스트한다. 확정하지 않은 금융 이벤트는 명시적으로 지원하지 않는 것으로 처리한다.

완료 조건은 동일 입력에서 재현 가능한 기본 계산, 계좌 격리, 저장 후 동일 상태 복원, 금융 규칙의 문서화와 테스트다. 현재 상태 분석은 Phase 3에서 구현했다. 역사적 성과, Policy 실행, Shadow, AI, Strategy, Broker 실행은 데이터와 계약이 확보되는 후속 단계에서 추가한다.

## 모델과 검수

일반 구현은 Sol Medium, 복잡한 구현은 Sol High를 사용한다. Architecture·금융 구조는 Astra Medium 또는 High로 검토한다. Phase 0은 Astra High로 진행한다.

Backtest Integrity Audit, Broker / Execution Safety Audit, 실제 자금 연결 전 최종 Safety Audit에는 Astra Extra High를 사용한다. 모델 사용 원칙의 원장은 PROJECT_SPEC이며, Audit만으로 인간의 자금 투입 승인을 대체하지 않는다.

제공자, 금융 계산 규칙, 정책 운영 방식, 한국 거래 비용·위험 한도, 실전 승격 기준 등의 미결정 사항은 [Open Decisions](../PROJECT_SPEC.md#15-open-decisions)에서 추적한다.

## Phase 4 canonical acceptance criteria

main의 기존 Phase 4 조건인 **인간 소유 설정 loader/validator, 범위·집중도·Risk 평가, Policy 변경 이력·권한·경계값 검증**을 아래처럼 검증한다. 후보에서 구현된 일부 평가만으로 범위 전체를 완료 처리하지 않는다. 각 상태와 근거는 STATUS에 둔다.

| ID | 완료 조건 | 필요한 근거 |
| --- | --- | --- |
| P4-01 | 인간 소유 설정을 Decimal로 읽고 단위·합계·범위·한도·schema를 검증한다. 미지의 키/잘못된 값은 거부한다 | 정상 설정과 오타·누락·잘못된 타입·한도 모순 테스트 |
| P4-02 | `individual_position_max`와 concentration warning은 개별 STOCK에 적용한다. Core ETF target을 개별주 한도로 잘못 제한하지 않는다 | STOCK 경계값, ETF 제외, 명명·설정·문서 일치 |
| P4-03 | `individual_stocks_total_max`를 실제 총 STOCK 평가에 사용한다 | 복수 STOCK 합계, 미분류 STOCK 포함, ETF 제외, 정확한 Decimal 경계값 |
| P4-04 | Direct Sector와 Cash Range를 평가하고 미분류 STOCK을 명시한다 | cash 포함 분모, sector UNKNOWN, ETF look-through 없음, 현금 양 끝 경계 |
| P4-05 | 선언된 Core ETF / Growth ETF / Individual Stocks / Cash Target 및 Range의 평가 계약과 구현을 갖춘다 | 명시적 Core/Growth 분류 입력, 중복·미분류 처리, 범위/목표 평가 테스트. ticker로 추측하지 않음 |
| P4-06 | 인간 Policy의 변경 이력·버전·적용 시점을 보존하고 과거 평가가 당시 설정에 연결된다 | 설정 버전 문자열 이상의 변경/적용 기록 및 재현 테스트 |
| P4-07 | 인간의 Policy 변경 승인과 AI의 Policy 쓰기·Risk 우회 금지를 강제하는 경계를 검증한다 | 승인·거부·권한 우회 방지 테스트. frozen 객체나 파일 주석만으로 충족하지 않음 |
| P4-08 | 분석/정책 경계, 불변성, 결정론, Decimal 비교, 데이터 부족 시 UNKNOWN을 검증한다 | Repository/Provider/clock 없는 evaluator, 전체 회귀와 실패 경계 테스트 |
| P4-09 | 모든 조건 PASS, review 완료, main merge/push 및 STATUS 갱신 | 실제 전체 테스트 결과, 정확한 SHA와 merge 확인 |

P4-05/06/07/09는 후보에서도 OPEN이다. ETF Core/Growth 분류, 정책 변경 이력·권한을 임의 금융 수치나 단순 actor 문자열로 채우지 않는다. ETF holdings look-through는 현재 지원하지 않으며 직접 STOCK sector 범위와 구분한다. 후보의 과거 Phase 4 완료 표기는 원래 조건을 충족한 근거가 아니므로 현재 판단에 사용하지 않는다. Phase 5 US Shadow Engine은 Phase 4 gate 통과 후 착수한다.
