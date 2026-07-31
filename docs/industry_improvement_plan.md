# Lending Platform Improvement Plan

This document summarizes priority remediation and enhancement tasks to align the platform with industry practices for lending management software. Items are grouped by domain and include recommended next steps.

## 1. Security & Configuration Hardening
- **Secrets management:** Move the Django secret key, email passwords, and integration credentials into an environment-specific secrets manager (e.g., AWS Secrets Manager, Azure Key Vault) instead of committing them to source control. The current settings module exposes the production secret key and SMTP password with `DEBUG` enabled, which violates PCI DSS and GDPR expectations for protecting authentication factors.【F:settings_local.py†L1-L92】【F:settings_local.py†L248-L258】
- **Production readiness flags:** Disable `DEBUG`, define restricted `ALLOWED_HOSTS`, and configure HTTPS-related security headers before launch to prevent information leakage and clickjacking.【F:settings_local.py†L10-L44】【F:settings_local.py†L100-L122】
- **Least-privilege permissions:** Replace the unconditional `True` responses in the custom user model’s `has_perm`/`has_module_perms` helpers with Django’s standard permission checks so that backend users cannot escalate privileges silently.【F:accounts/models.py†L61-L83】
- **Fix recursive status properties:** Correct `User.is_confirmed` so it returns the stored boolean flag rather than recursing on itself, ensuring identity assurance logic behaves as intended during onboarding and credit decisions.【F:accounts/models.py†L85-L101】

## 2. Data Protection & Privacy
- **Govern personally identifiable information:** The user profile stores passports, national IDs, drivers licences, salaries, and employment data along with public URLs. Introduce encryption at rest, signed download URLs with expirations, and data retention policies to satisfy GDPR, CCPA, and regional privacy acts. Also audit templates that surface raw URLs to ensure access control and auditing.【F:accounts/models.py†L109-L181】【F:accounts/templates/profile.html†L112-L118】
- **Limit hard-coded distribution lists:** External email addresses are embedded directly in settings; migrate them to configurable distribution groups and ensure opt-in tracking to comply with CAN-SPAM and similar regulations.【F:settings_local.py†L45-L87】【F:settings_local.py†L200-L244】

## 3. API & Integration Governance
- **Make external APIs idempotent and read-only where required:** Current GET endpoints for `/api/userprofiles`, `/api/allloans`, and `/api/statements` mutate database records by forcing a DCC status update. Adjust them to follow REST conventions (GET must not change state) and protect them with token-based authentication and rate limiting.【F:api/views.py†L12-L36】
- **Strengthen authentication responses:** The login API returns `user.username`, which is undefined for the custom email-based user model. Refactor to emit stable identifiers and include MFA/OTP hooks before issuing session cookies.【F:api/views.py†L38-L65】

## 4. Workflow Resilience & Task Processing
- **Remove HTTP request dependencies from Celery tasks:** Background jobs such as `download_tc` accept Django request objects and render templates directly, which is unsafe for async workers and prevents job replay. Refactor tasks to operate on model identifiers and fetch their own context, adding retry/idempotency controls around email and PDF generation.【F:loan/tasks.py†L37-L107】
- **Handle external command execution safely:** PDF generation shells out to `wkhtmltopdf` without sandboxing or output validation. Introduce error handling, timeout controls, and file-system isolation to protect workers from command injection and runaway processes.【F:loan/tasks.py†L24-L70】

## 5. Operational Excellence
- **Centralize configuration via environment-specific settings:** Split settings into base/staging/production modules that derive from environment variables, enabling twelve-factor deployments and easier CI/CD pipelines.【F:settings_local.py†L1-L122】
- **Introduce automated testing and CI/CD:** Add unit and integration tests across lending workflows, Celery tasks, and API endpoints, then wire them into a CI pipeline (GitHub Actions, GitLab CI) to prevent regressions before regulatory audits.
- **Implement observability and audit logging:** Extend Celery and view logic to emit structured logs for loan state transitions, API access, and notification dispatches so that compliance teams can trace customer-impacting events.

## 6. Compliance & Governance Roadmap
- Document data flows and retention schedules for regulators, including how long identity documents are stored and who can access them.
- Establish maker-checker controls for loan approvals, arrears classification, and write-offs to meet credit risk management guidelines.
- Schedule regular penetration testing and vulnerability management aligned with ISO 27001/PCI DSS change-management cycles.

These recommendations should be prioritized alongside a security triage to remediate exposed secrets immediately, followed by architectural and process changes that drive long-term compliance.
