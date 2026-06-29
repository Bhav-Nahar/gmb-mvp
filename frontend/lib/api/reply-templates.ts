import { api } from '../api';

export interface ReplyTemplate {
  id: number;
  organization_id: number;
  star_rating: number;
  title: string;
  body: string;
  display_order: number;
  created_by_user_id: number | null;
  usage_count: number;
  created_at: string;
  updated_at: string;
}

export interface CreateTemplatePayload {
  star_rating: number;
  title: string;
  body: string;
  display_order?: number;
}

export interface UpdateTemplatePayload {
  title?: string;
  body?: string;
  display_order?: number;
}

// Per-star limits — must match backend STAR_RATING_LIMITS
export const STAR_RATING_LIMITS: Record<number, number> = {
  1: 5,
  2: 3,
  3: 3,
  4: 3,
  5: 5,
};

export async function fetchTemplates(): Promise<ReplyTemplate[]> {
  return api.get<ReplyTemplate[]>('/reply-templates/');
}

export async function createTemplate(payload: CreateTemplatePayload): Promise<ReplyTemplate> {
  return api.post<ReplyTemplate>('/reply-templates/', payload);
}

export async function updateTemplate(id: number, payload: UpdateTemplatePayload): Promise<ReplyTemplate> {
  return api.put<ReplyTemplate>(`/reply-templates/${id}`, payload);
}

export async function deleteTemplate(id: number): Promise<{ auto_reply_disabled: boolean }> {
  return api.delete(`/reply-templates/${id}`);
}

// Org-wide auto-reply: replies to new 4-5★ reviews from a template automatically.
export const MIN_TEMPLATES_FOR_AUTO_REPLY = 2;

export interface AutoReplyStatus {
  enabled_at: string | null;
  positive_template_count: number;
  min_required: number;
}

export async function getAutoReplyStatus(): Promise<AutoReplyStatus> {
  return api.get<AutoReplyStatus>('/reply-templates/auto-reply');
}

export async function setAutoReply(enabled: boolean): Promise<{ status: string; enabled_at?: string | null }> {
  return api.post(`/reply-templates/auto-reply/${enabled ? 'enable' : 'disable'}`);
}

// Variables offered in the editor's "Insert" toolbar (mirrors backend INSERTABLE_VARIABLES).
export const INSERTABLE_VARIABLES = [
  'reviewer_name', 'first_name', 'location_name', 'city', 'phone', 'website', 'rating',
];

export interface TemplateAnalytics {
  last_used: Record<string, string>; // template_id -> ISO date
  auto_replies_30d: number;
}

export async function getTemplateAnalytics(): Promise<TemplateAnalytics> {
  return api.get<TemplateAnalytics>('/reply-templates/analytics');
}
