# Hinthar System Audit Findings

The full cross-repo audit (security → correctness → performance) lives in the dashboard docs:

**[SYSTEM_AUDIT_FINDINGS.md](../../Hinthar-Dashboard/hinthar-dashboard/docs/SYSTEM_AUDIT_FINDINGS.md)**

Historical 2026-08-07 snapshot. Matching, owner hubs, and owner-read timetables are documented in `API_STANDARDS.md`, not in that audit table.

If that relative path does not resolve in your checkout layout, open:

`Hinthar-Dashboard/hinthar-dashboard/docs/SYSTEM_AUDIT_FINDINGS.md`

## Top SMS-specific items (summary)

| ID | Severity | Issue |
|----|----------|--------|
| SEC-C1 | Critical | `DEBUG` defaults True → mock auth bypass (`mock_token_*`) |
| SEC-C2 | Critical | Live DB/Clerk secrets in local `.env` (gitignored, still rotate) |
| SEC-H1 | High | `is_active=False` users still authenticate |
| SEC-H2 | High | `check_in_token` returned in student list payloads for staff |
| PERF-H1 | High | Session list always prefetches all attendances |
| PERF-H3 | High | Student analytics `range=all` builds huge day arrays |

See the dashboard report for evidence, impact, and recommended fixes.
