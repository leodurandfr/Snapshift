export interface ViewportConfig {
  width: number
  height: number
  label: string
}

export interface Tag {
  id: string
  name: string
  color: string
}

export interface MonitoredURL {
  id: string
  url: string
  label: string | null
  viewports: ViewportConfig[]
  schedule: string
  full_page: boolean
  archive_enabled: boolean
  dismiss_cookies: boolean
  change_threshold: number
  is_active: boolean
  created_at: string
  updated_at: string
  tags: Tag[]
  last_capture_at: string | null
  last_capture_status: string | null
  last_thumbnail: string | null
}

export interface Capture {
  id: string
  url_id: string
  viewport_label: string
  viewport_width: number
  viewport_height: number
  image_path: string | null
  thumbnail_path: string | null
  archive_path: string | null
  archive_size: number | null
  diff_image_path: string | null
  diff_score: number | null
  file_size: number | null
  captured_at: string
  status: 'success' | 'error' | 'timeout'
  error_message: string | null
}

export interface CaptureJob {
  id: string
  url_id: string
  viewport_label: string
  viewport_width: number
  viewport_height: number
  status: 'pending' | 'running' | 'completed' | 'failed'
  created_at: string
  started_at: string | null
  completed_at: string | null
  error_message: string | null
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
}

export interface URLCreatePayload {
  url: string
  label?: string
  viewports?: ViewportConfig[]
  schedule?: string
  full_page?: boolean
  archive_enabled?: boolean
  dismiss_cookies?: boolean
  change_threshold?: number
  tag_ids?: string[]
}

export interface URLUpdatePayload {
  url?: string
  label?: string
  viewports?: ViewportConfig[]
  schedule?: string
  full_page?: boolean
  archive_enabled?: boolean
  dismiss_cookies?: boolean
  change_threshold?: number
  is_active?: boolean
  tag_ids?: string[]
}

export interface TagCreatePayload {
  name: string
  color?: string
}
