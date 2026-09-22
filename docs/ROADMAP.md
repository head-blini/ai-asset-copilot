# Development Roadmap

[PROJECT_SPEC.md](../PROJECT_SPEC.md)가 authoritative specification이다. 이 문서는 그 로드맵을 구현 범위와 완료 조건으로 구체화한다. **Phase 0~3은 완료**, 다음 단계는 Phase 4 US Portfolio Policy다. 단계 완료는 자동 자금 투입 승인을 뜻하지 않는다.

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
