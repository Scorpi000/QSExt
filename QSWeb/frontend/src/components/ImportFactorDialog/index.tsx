/**
 * ImportFactorDialog - 因子脚本导入对话框
 *
 * 支持上传 .py 文件或粘贴代码，AST 静态验证后预览元信息，确认导入。
 */

import { useState, useEffect } from 'react'
import {
  Modal,
  Tabs,
  Upload,
  Input,
  Button,
  Descriptions,
  Tag,
  Space,
  message,
  Alert,
  Spin,
  Tooltip,
} from 'antd'
import { InboxOutlined } from '@ant-design/icons'
import type { UploadProps } from 'antd'
import api from '../../services/api'
import { previewImport, importFactor, importFactorFile } from '../../services/import'
import type { ImportPreviewResult, ImportResult } from '../../services/import'

const { Dragger } = Upload
const { TextArea } = Input

interface ImportFactorDialogProps {
  open: boolean
  onClose: () => void
  initialCode?: string // 从 AI 助手传入的代码
  initialFilename?: string
}

function ImportFactorDialog({ open, onClose, initialCode, initialFilename }: ImportFactorDialogProps) {
  const [activeTab, setActiveTab] = useState<string>('paste')
  const [code, setCode] = useState(initialCode || '')
  const [filename, setFilename] = useState(initialFilename || 'factor.py')
  // 预览状态
  const [previewing, setPreviewing] = useState(false)
  const [preview, setPreview] = useState<ImportPreviewResult | null>(null)

  // 导入状态
  const [importing, setImporting] = useState(false)
  const [registering, setRegistering] = useState(false)
  const [registerTaskId, setRegisterTaskId] = useState<string | null>(null)
  const [registerError, setRegisterError] = useState<string | null>(null)

  // 轮询注册任务状态
  useEffect(() => {
    if (!registerTaskId) return
    let cancelled = false
    const poll = async () => {
      try {
        const res = await api.get(`/tasks/${registerTaskId}`) as any
        if (cancelled) return
        if (res.status === 'completed') {
          message.success(`因子已注册到图数据库`)
          setRegistering(false)
          setRegisterTaskId(null)
          handleReset()
          onClose()
        } else if (res.status === 'failed') {
          setRegistering(false)
          setRegisterError(res.error || '注册失败，请查看后端日志')
        }
      } catch {
        // 继续轮询
      }
      if (!cancelled && registerTaskId) setTimeout(poll, 2000)
    }
    poll()
    return () => { cancelled = true }
  }, [registerTaskId])

  // 重置
  const handleReset = () => {
    setCode('')
    setFilename('factor.py')
    setPreview(null)
    setActiveTab('paste')
    setRegistering(false)
    setRegisterTaskId(null)
    setRegisterError(null)
  }

  // 处理粘贴代码
  const handleCodeChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setCode(e.target.value)
    setPreview(null)
  }

  // 处理文件上传
  const handleUpload: UploadProps['customRequest'] = async (options) => {
    const file = options.file as File
    if (!file.name.endsWith('.py')) {
      message.error('仅支持 .py 文件')
      options.onError?.(new Error('invalid extension'))
      return
    }
    setFilename(file.name)

    // 读取文件内容
    const reader = new FileReader()
    reader.onload = (e) => {
      const content = e.target?.result as string
      setCode(content)
      options.onSuccess?.(content)
    }
    reader.onerror = () => {
      options.onError?.(new Error('read error'))
    }
    reader.readAsText(file)
  }

  // 预览：AST 解析
  const handlePreview = async () => {
    if (!code.trim()) {
      message.warning('请先粘贴代码或上传文件')
      return
    }
    setPreviewing(true)
    try {
      const result = await previewImport(code, filename)
      setPreview(result as unknown as ImportPreviewResult)
    } catch (err: any) {
      message.error(err?.response?.data?.message || err?.message || '预览失败')
    } finally {
      setPreviewing(false)
    }
  }

  // 确认导入
  const handleImport = async () => {
    if (!code.trim()) {
      message.warning('请先粘贴代码或上传文件')
      return
    }
    setImporting(true)
    try {
      const result = await importFactor(code, filename)
      const data = result as unknown as ImportResult
      if (data.success) {
        message.success(`脚本已保存到: ${data.saved_path}`)
        if (data.task_id) {
          setRegistering(true)
          setRegisterTaskId(data.task_id)
          // 不关闭对话框，等待注册完成
        } else {
          if (data.register_hint) {
            message.info(data.register_hint, 8)
          }
          handleReset()
          onClose()
        }
      } else {
        message.error('导入失败')
      }
    } catch (err: any) {
      message.error(err?.response?.data?.message || err?.message || '导入失败')
    } finally {
      setImporting(false)
    }
  }

  // 渲染元信息预览
  const renderMeta = (meta: Record<string, any>) => {
    const fields: { label: string; key: string; render?: (v: any) => React.ReactNode }[] = [
      { label: '因子表', key: 'TargetTable' },
      { label: 'ID 类型', key: 'IDType' },
      { label: '作者', key: 'Author' },
      { label: '描述', key: 'Description' },
      { label: '最大回溯', key: 'MaxLookBack' },
      {
        label: '依赖因子',
        key: 'FactorDeps',
        render: (v: any) => {
          if (!v || typeof v !== 'object' || Object.keys(v).length === 0) return '-'
          return (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {Object.entries(v).map(([table, factors]: [string, any]) => (
                <div key={table} style={{ fontSize: 11 }}>
                  <Tag color="purple" style={{ marginBottom: 2 }}>{table}</Tag>
                  <div style={{ paddingLeft: 8 }}>
                    {Array.isArray(factors)
                      ? factors.map((f: any) => {
                          if (typeof f === 'string') return <Tag key={f} style={{ fontSize: 10 }}>{f}</Tag>
                          if (typeof f === 'object' && f !== null) {
                            const name = f.Name || f.name || JSON.stringify(f)
                            const alias = f.Alias || f.alias
                            return (
                              <Tag key={name} style={{ fontSize: 10 }}>
                                {name}{alias ? ` → ${alias}` : ''}
                              </Tag>
                            )
                          }
                          return <Tag key={String(f)} style={{ fontSize: 10 }}>{String(f)}</Tag>
                        })
                      : <span style={{ color: '#888', fontSize: 10 }}>{String(factors)}</span>
                    }
                  </div>
                </div>
              ))}
            </div>
          )
        },
      },
      {
        label: '依赖数据库',
        key: 'DBDeps',
        render: (v: any) =>
          v && typeof v === 'object'
            ? Object.keys(v).map((k) => <Tag key={k} color="blue">{k}</Tag>)
            : '-',
      },
      {
        label: '标签',
        key: 'Tags',
        render: (v: any) =>
          Array.isArray(v) ? v.map((t: string) => <Tag key={t}>{t}</Tag>) : '-',
      },
    ]

    return (
      <Descriptions column={1} size="small" bordered style={{ marginTop: 12 }}>
        {fields
          .filter((f) => meta[f.key] !== undefined && meta[f.key] !== null && meta[f.key] !== '')
          .map((f) => (
            <Descriptions.Item key={f.key} label={f.label} labelStyle={{ fontSize: 12, fontWeight: 500 }} contentStyle={{ fontSize: 12 }}>
              {f.render ? f.render(meta[f.key]) : String(meta[f.key])}
            </Descriptions.Item>
          ))}
      </Descriptions>
    )
  }

  return (
    <Modal
      title="导入因子脚本"
      open={open}
      onCancel={() => {
        handleReset()
        onClose()
      }}
      width={700}
      footer={
        registering ? (
          <Space>
            <Spin size="small" />
            <span style={{ fontSize: 13, color: '#1890ff' }}>正在注册到图数据库...</span>
          </Space>
        ) : registerError ? (
          <Space>
            <Button onClick={() => { setRegisterError(null); handleReset(); onClose(); }}>关闭</Button>
          </Space>
        ) : (

          <Space>
            <Button onClick={() => { handleReset(); onClose(); }}>取消</Button>
            <Button onClick={handlePreview} loading={previewing} disabled={!code.trim()}>
              预览
            </Button>
            <Tooltip title={!preview ? '请先点击"预览"验证脚本' : !preview.success ? '脚本验证未通过，请查看错误信息' : ''}>
              <Button type="primary" onClick={handleImport} loading={importing} disabled={!preview?.success}>
                确认导入
              </Button>
            </Tooltip>
          </Space>
        )
      }
      destroyOnClose
    >
      {registerError && (
        <Alert
          type="error"
          message="注册失败"
          description={registerError}
          closable
          onClose={() => setRegisterError(null)}
          style={{ marginBottom: 16 }}
        />
      )}

      <Tabs activeKey={activeTab} onChange={setActiveTab} items={[
        {
          key: 'paste',
          label: '粘贴代码',
          children: (
            <div>
              <div style={{ marginBottom: 8 }}>
                <span style={{ fontSize: 13, fontWeight: 500 }}>文件名: </span>
                <Input
                  style={{ width: 250 }}
                  size="small"
                  value={filename}
                  onChange={(e) => setFilename(e.target.value)}
                  placeholder="factor.py"
                />
              </div>
              <TextArea
                rows={12}
                value={code}
                onChange={handleCodeChange}
                placeholder={`# -*- coding: utf-8 -*-\n"""因子名称: ...\n描述: ...\n"""\nfrom typing import List\nfrom QSExt.FactorDef.FactorDefContent import FactorDefInput\n...`}
                style={{ fontFamily: 'monospace', fontSize: 12 }}
              />
            </div>
          ),
        },
        {
          key: 'upload',
          label: '上传文件',
          children: (
            <Dragger
              accept=".py"
              maxCount={1}
              customRequest={handleUpload}
              onChange={(info) => {
                if (info.file.status === 'done') {
                  message.success(`${info.file.name} 上传成功`)
                } else if (info.file.status === 'error') {
                  message.error(`${info.file.name} 上传失败`)
                }
              }}
              showUploadList={{ showRemoveIcon: false }}
            >
              <p className="ant-upload-drag-icon">
                <InboxOutlined />
              </p>
              <p className="ant-upload-text">点击或拖拽 .py 文件到此区域</p>
              <p className="ant-upload-hint">仅支持符合 FactorDef 框架规范的 Python 脚本</p>
            </Dragger>
          ),
        },
      ]} />

      {/* 预览区域 */}
      <Spin spinning={previewing}>
        {preview && preview.success && (
          <div style={{ marginTop: 16 }}>
            <Alert
              type="success"
              message={`验证通过: defFactor ${preview.has_def_factor ? '✓' : '✗'} | __FACTOR_META__ ${preview.has_meta ? '✓' : '✗'}`}
              style={{ marginBottom: 12 }}
            />

            {preview.warnings.length > 0 && (
              <Alert
                type="warning"
                message="警告信息"
                description={preview.warnings.map((w, i) => <div key={i}>• {w}</div>)}
                style={{ marginBottom: 12 }}
              />
            )}

            {preview.has_meta && renderMeta(preview.meta)}

          </div>
        )}

        {preview && !preview.success && (
          <Alert type="error" message="验证失败" style={{ marginTop: 16 }} />
        )}
      </Spin>
    </Modal>
  )
}

export default ImportFactorDialog
