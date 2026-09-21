import api from './client'

export interface DownloadRequest {
  urls: string[]
  download_dir?: string
  format_option: {
    mode: string
    format_string?: string
    resolution?: string
  }
  cookie_browser?: string
  cookie_file?: string
  proxy?: string
  subtitle_options: {
    enabled: boolean
    languages: string
    auto_subs: boolean
    sub_format: string
    embed_subs: boolean
  }
  output_template: string
  metadata?: {
    title?: string
    artist?: string
    album?: string
  }
  write_thumbnail: boolean
  embed_thumbnail: boolean
  embed_metadata: boolean
  extra_args?: string[]
}

export interface DownloadTask {
  id: string
  url: string
  status: string
  title?: string
  thumbnail?: string
  progress_pct: number
  speed?: string
  eta?: string
  filename?: string
  filesize?: string
  error?: string
  created_at: number
  completed_at?: number
}

export async function createDownload(req: DownloadRequest): Promise<{ task_ids: string[] }> {
  const res = await api.post('/downloads', req)
  return res.data
}

export async function listDownloads(status = 'all'): Promise<DownloadTask[]> {
  const res = await api.get('/downloads', { params: { status } })
  return res.data
}

export async function cancelDownload(taskId: string): Promise<void> {
  await api.delete(`/downloads/${taskId}`)
}

export async function extractInfo(url: string): Promise<any> {
  const res = await api.post('/downloads/info', { url })
  return res.data
}
