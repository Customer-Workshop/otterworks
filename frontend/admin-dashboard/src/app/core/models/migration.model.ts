// Wire shapes served by report-service (/api/v1/reports/reconciliation, /api/v1/archive/documents).

export interface ReconciliationTableRow {
  table: string;
  extracted: number;
  loaded: number;
  validated: number;
  purged: number;
  failed: number;
  rejected: number;
  validate_failed: number;
  purge_intended: number;
  purge_dry_run: boolean | null;
  closes: boolean;
}

export interface ReconciliationFailureRow {
  table: string;
  source_key: string;
  rule: string;
  stage: string;
  field: string | null;
  sqlstate: string | null;
  native_error: number | null;
  error: string | null;
  issue: string | null;
}

export interface ReconciliationClassTotal {
  table: string;
  class: string;
  source_count: number;
  target_count: number;
  source_sum: string;
  target_sum: string;
  matches: boolean;
}

export interface SessionLink {
  label: string;
  url: string;
}

export interface ReconciliationReport {
  run_id: string;
  namespace: string;
  generated_at: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  tables: ReconciliationTableRow[];
  failures: ReconciliationFailureRow[];
  class_totals: ReconciliationClassTotal[];
  sessions: SessionLink[];
  closes: boolean;
}

export interface RunSummary {
  run_id: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  closes: boolean;
}

export interface ArchiveEvent {
  audit_key: string;
  arch_key?: string;
  event_type: string;
  event_ts: string;
  actor_id: string;
  retention_class: string;
  disposition_code: string;
  client_ip: string;
  detail_text: string;
}

export interface ArchivePolicy {
  policy_code: string;
  policy_desc: string;
  retention_years: number;
  successor_code: string;
  active_flag: string;
  disposition_action: string;
  effective_ts: string;
}

export interface ArchiveVersion {
  arch_key: string;
  version_no: number;
  retention_class: string;
  last_access_ts: string;
  storage_charge: string;
  unit_rate: string;
  owner_name: string;
  disposition_dt: string;
  legal_hold: boolean;
  checksum_alg: string;
  content_sha256: string;
  byte_size: number;
  source_sys: string;
  policy?: ArchivePolicy | null;
  events: ArchiveEvent[];
}

export interface ArchiveDocument {
  doc_id: string;
  store: 'db2' | 'azuresql' | string;
  versions: ArchiveVersion[];
}

export interface ArchiveHash {
  doc_id: string;
  store: string;
  algorithm: string;
  document_hash: string;
}

export interface PeerConfig {
  peer_app_url: string;
  /** Same-origin path nginx proxies to the peer (e.g. /peer); empty when there is no peer. */
  peer_proxy_url?: string;
}

export const MIG_ISSUES: readonly string[] = [
  'MIG-01', 'MIG-02', 'MIG-03', 'MIG-04', 'MIG-05', 'MIG-06', 'MIG-07',
];
