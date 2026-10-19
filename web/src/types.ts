export interface User {
  id: number;
  first_name: string;
  username: string | null;
  is_owner: boolean;
  notifications_enabled: boolean;
  preference_version: number;
  language_code: "ru" | "en" | "kk";
}
export interface Service {
  id: string;
  title: string;
  summary: string;
  examples: string[];
}
export interface Attachment {
  id: string;
  filename: string;
  size_bytes: number;
  state: string;
  error_code: string | null;
}
export interface Attachments {
  version: number;
  count: number;
  bytes: number;
  max_files: number;
  max_file_bytes: number;
  max_total_bytes: number;
  items: Attachment[];
}
export type DraftFields = Record<
  "service_id" | "name" | "description" | "budget" | "deadline",
  string
>;
export interface Draft {
  id: string;
  version: number;
  fields: Partial<DraftFields>;
  updated_at: string;
  attachments: Attachments;
}
export interface Proposal {
  version: number;
  scope: string;
  result: string;
  price_minor: number;
  currency: string;
  deadline: string;
  revision_terms: string;
  created_at: string;
}
export interface Delivery {
  version: number;
  description: string;
  url: string;
  created_at: string;
}
export interface HistoryEvent {
  id: number;
  kind: string;
  actor: string;
  created_at: string;
  data: Record<string, unknown>;
}
export interface Project {
  id: number;
  service_id: string | null;
  service_title: string;
  name: string;
  description: string;
  budget: string;
  deadline: string;
  workflow: string;
  status: string;
  status_label: string;
  next_action: string;
  version: number;
  proposal_version: number;
  accepted_proposal_version: number | null;
  delivery_version: number;
  close_reason: string | null;
  created_at: string;
  updated_at: string;
  allowed_actions: string[];
  proposal: Proposal | null;
  accepted_proposal: Proposal | null;
  proposals: Proposal[];
  delivery: Delivery | null;
  history: HistoryEvent[];
  has_older_history: boolean;
  attachments: Attachments;
  client?: { id: number; username: string | null; phone: string | null };
}
export interface PageData<T> {
  items: T[];
  total: number;
  offset: number;
  limit: number;
}
export interface Summary {
  total: number;
  counts: Record<string, number>;
  needs_response: number;
  waiting_client: number;
  in_progress: number;
  review: number;
}
export interface Notification {
  id: number;
  state: string;
  kind: string;
  project_id: number;
  attempts: number;
  error_code?: string;
  retry_blocked_reason?: string | null;
  can_retry?: boolean;
  created_at?: string;
}
export interface Config {
  brand: string;
  owner_username: string;
  file_limits: {
    count: number;
    file_bytes: number;
    total_bytes: number;
    extensions: string[];
  };
}
