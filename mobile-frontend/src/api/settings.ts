import api from './client'

export interface Settings {
  download_dir: string
  max_concurrent: number
  proxy?: string
  cookie_browser?: string
  output_template: string
  ffmpeg_path?: string
  embed_metadata: boolean
  embed_thumbnail: boolean
  write_subs: boolean
  sub_languages: string
  theme: string
}

export async function getSettings(): Promise<Settings> {
  const res = await api.get('/api/settings')
  return res.data
}

export async function updateSettings(settings: Partial<Settings>): Promise<Settings> {
  const res = await api.put('/api/settings', settings)
  return res.data
}

export async function checkFfmpeg(): Promise<{ available: boolean; path: string | null }> {
  const res = await api.get('/api/system/ffmpeg')
  return res.data
}

export async function openFile(path: string): Promise<{ success: boolean; error?: string }> {
  const res = await api.post('/api/system/open-file', { path })
  return res.data
}

export async function openFolder(path: string): Promise<{ success: boolean; error?: string }> {
  const res = await api.post('/api/system/open-folder', { path })
  return res.data
}
