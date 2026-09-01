# Xecaps Phase A+B Closure Program

## Purpose
Close the remaining Phase A (35 tasks) and Phase B (15 tasks) production-quality gaps without creating duplicate systems.

## Engineering rule
Inspect existing functionality first. Reuse it when sound. Refactor or remove redundant implementations only after dependency and behavior checks. Every change must preserve API compatibility unless a migration is explicitly documented.

## Closure gates
- Backend lint/format/type checks pass.
- Frontend typecheck and production build pass.
- Security scans are blocking in CI.
- No known Critical/High dependency or static-analysis findings.
- Authentication refresh rotation is concurrency-safe.
- Point-in-time prediction inputs are enforced.
- Prediction provenance is recorded for every generated prediction.
- 1D/3D/5D/10D/15D/20D/30D outcome evaluation is connected to predictions.
- Backtests cannot use information after the simulation timestamp.
- AI performance is evaluated with calibration, discrimination, bias and drift metrics.
- Load-test and recovery procedures are executable and their results are recorded.
- Backup restore has been exercised successfully.
- Production release checklist is complete.

## Verification policy
A task is marked complete only when the repository contains both the implementation and an executable test, check, benchmark, or operational artifact appropriate to that task. Documentation alone is not proof of completion.

## Current priority
1. Repair CI/build blockers found by the hardening checks.
2. Complete security gates.
3. Connect prediction audit/provenance to the existing prediction pipeline.
4. Verify point-in-time correctness across all existing backtest/evaluation paths.
5. Verify AI calibration and outcome tracking using existing evaluation infrastructure.
6. Execute load, backup/restore and resilience verification.
7. Re-run the full quality matrix and publish the final Phase A+B status.
