/**
 * Canonical audit-log action vocabulary.
 *
 * Closes #111 (action-name mismatch between route and DB CHECK constraint).
 * This list is the single source of truth; migration 019 mirrors it and the
 * test in tests/integration/audit-log-vocabulary.test.ts proves they agree.
 *
 * If you add a value here you MUST also update the CHECK constraint in the
 * next migration — otherwise inserts will succeed at the route layer but
 * fail at the database layer.
 */
export const AUDIT_LOG_ACTIONS = [
  "LOGIN",
  "LOGOUT",
  "SIMULATION_RUN",
  "REPORT_EXPORT",
  "REPORT_VIEW",
  "SETTINGS_CHANGE",
  "API_KEY_CREATED",
  "API_KEY_REVOKED",
  "PROJECT_CREATED",
  "PROJECT_DELETED",
  "MEMBER_INVITED",
  "PLAN_CHANGED",
  "DATA_EXPORT",
  "TASK_CREATE",
  "TASK_UPDATE",
  "TASK_DELETE",
] as const;

export type AuditLogAction = (typeof AUDIT_LOG_ACTIONS)[number];

export const AUDIT_LOG_ACTION_SET: ReadonlySet<string> = new Set<string>(AUDIT_LOG_ACTIONS);
