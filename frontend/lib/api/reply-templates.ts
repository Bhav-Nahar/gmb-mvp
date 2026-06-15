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

export async function deleteTemplate(id: number): Promise<void> {
  return api.delete(`/reply-templates/${id}`);
}
