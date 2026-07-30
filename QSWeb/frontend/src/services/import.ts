/**
 * 因子脚本导入 API
 */

import api from './api'

export interface ImportPreviewResult {
  success: boolean
  meta: Record<string, any>
  warnings: string[]
  has_def_factor: boolean
  has_meta: boolean
}

export interface ImportResult {
  success: boolean
  filename: string
  saved_path: string
  meta: Record<string, any>
  warnings: string[]
  has_def_factor: boolean
  has_meta: boolean
  was_renamed: boolean
  original_filename: string
  task_id: string | null
  register_hint: string | null
}

/** 预览导入：仅 AST 解析，不存储 */
export const previewImport = (code: string, filename?: string) => {
  const form = new FormData()
  form.append('code', code)
  form.append('filename', filename || 'factor.py')
  return api.post<ImportPreviewResult>('/factors/import/preview', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

/** 执行导入：解析 + 存储 */
export const importFactor = (code: string, filename: string) => {
  const form = new FormData()
  form.append('code', code)
  form.append('filename', filename)
  return api.post<ImportResult>('/factors/import', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

/** 上传文件导入 */
export const importFactorFile = (file: File) => {
  const form = new FormData()
  form.append('file', file)
  return api.post<ImportResult>('/factors/import', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}
