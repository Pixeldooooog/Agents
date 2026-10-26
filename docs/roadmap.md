# Roadmap

## Current direction

Build and verify the complete Agent system baseline before finalizing the personal-agent product. TypeScript runtime cutover is complete; behavioral parity, durable execution and product acceptance remain separate gates.

- [Agent system baseline and acceptance matrix](agent-system-baseline.md) owns architecture, contracts and K01–K18 acceptance.
- [Implementation roadmap](kevin-implementation-roadmap.md) owns delivery dependencies.
- [Kevin product architecture](kevin-product-architecture-plan.md) describes the full personal product target.

## Delivery gates

| Gate | Outcome |
|---|---|
| B0 | Capability mapping, contracts, supported-environment matrix and technical spikes |
| B1 | Bounded runs, model/tool contracts, authorization and real execution isolation |
| B2 | Durable work, recovery, user intervention, budgets and supervised local service |
| B3 | Memory, artifacts, client consistency, complete restore and integration evidence |
| P1 | Personal identity, goals/plans, routines, attention policy and product definition |
| P2 | Product interaction, connection management and device authorization |
| P3 | CLI, naming/config migration, self-hosting and platform-specific release acceptance |
| C1 | Cloud execution with independently verified trust and reliability boundaries |

Existing Web/Terminal clients provide validation surfaces during B0–B3. Coding, research and periodic monitoring validate composition throughout; final product pages follow baseline acceptance. Existing tools must be audited against the registry rather than described as read/list-only.

## Evidence

Track implementation, local tests, real provider/connector tests, platform isolation and release verification separately. No gate is complete merely because its document or package directory exists.

2026-10-26 范围更新：沙箱后端独立暂缓，保留平台 executor/策略接口；本地默认不要求 Docker。继续其他基线建设，详见 [执行器 ADR](baseline/adr-001-local-execution.md)。
