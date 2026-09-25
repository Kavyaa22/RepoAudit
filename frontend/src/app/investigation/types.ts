export interface IsolatedTarget {
  path: string;
  scope: 'backend' | 'frontend' | 'common';
  feature_name: string;
  action_name: string;
  relevance_score: number;
  matched_reason: string;
}

export interface Hypothesis {
  hypothesis_id: string;
  category: string;
  title: string;
  description: string;
  likelihood_score: number;
  confidence_level: 'HIGH' | 'MEDIUM' | 'LOW';
  evidence_signals: string[];
  contradicting_signals: string[];
  suspect_files: string[];
  next_best_check: string;
}

export interface CodePatch {
  patch_id: string;
  file_path: string;
  original_snippet: string;
  proposed_snippet: string;
  unified_diff: string;
  explanation: string;
  confidence_score: number;
  status: 'draft' | 'applied_clean' | 'checks_passed' | 'unverified';
  verification_summary: string;
}

export interface EvidenceAssessment {
  score: number;
  tier: 'A' | 'B' | 'C' | 'D';
  route: 'clarify' | 'locate' | 'full';
  signals: string[];
  gaps: string[];
  guidance: string;
}

export interface InvestigationPhase {
  name: string;
  status: 'completed' | 'partial' | 'blocked';
  detail: string;
  duration_ms?: number;
}

export interface InvestigationMetrics {
  evidence_tier: 'A' | 'B' | 'C' | 'D';
  evidence_score: number;
  locate_top_score: number;
  locate_target_count: number;
  hypothesis_category: string;
  hypothesis_confidence: string;
  patch_statuses: string[];
  llm_used: boolean;
  llm_fallback: boolean;
  turn: number;
  total_duration_ms: number;
  phase_durations_ms: Record<string, number>;
  correlation_leads: string[];
}

export interface InvestigationResult {
  investigation_id: string;
  project_name: string;
  status: 'SUCCESS' | 'PARTIAL' | 'FAILED';
  summary_verdict: string;
  evidence: EvidenceAssessment;
  phases: InvestigationPhase[];
  snapshot_label: string;
  isolated_targets: IsolatedTarget[];
  primary_root_cause: Hypothesis | null;
  all_hypotheses: Hypothesis[];
  remediation_steps: string[];
  code_patches: CodePatch[];
  metrics?: InvestigationMetrics;
  clarification_questions?: string[];
  repro_checklist?: string[];
  turn?: number;
  artifact_path?: string;
}

export interface LiveArtifactPayload {
  kind: 'console' | 'network' | 'backend_trace' | 'timing' | 'screenshot_note' | 'other';
  content: string;
}

export interface IssueReportPayload {
  project_name: string;
  branch: string;
  project_id?: string;
  feature_name?: string;
  action_name?: string;
  expected_behavior?: string;
  actual_behavior?: string;
  environment?: string;
  severity?: string;
  issue_description: string;
  error_log?: string;
  live_artifacts?: LiveArtifactPayload[];
  investigation_id?: string;
  repo_path?: string;
  turn?: number;
}
