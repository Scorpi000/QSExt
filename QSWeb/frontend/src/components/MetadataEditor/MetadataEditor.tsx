import { useState, useEffect, useRef } from 'react'
import { Input, Button, Row, Col, message } from 'antd'
import { PlusOutlined, DeleteOutlined, SaveOutlined } from '@ant-design/icons'

interface MetadataEditorProps {
  title: string
  metadata: Record<string, any>
  onSave: (data: Record<string, any>) => Promise<void>
}

interface Entry {
  key: string
  value: string
  originalKey?: string
}

function MetadataEditor({ title, metadata, onSave }: MetadataEditorProps) {
  const [entries, setEntries] = useState<Entry[]>([])
  const [saving, setSaving] = useState(false)
  const originalKeysRef = useRef<Set<string>>(new Set())

  useEffect(() => {
    if (metadata && Object.keys(metadata).length > 0) {
      const filtered = Object.entries(metadata)
        .filter(([, value]) => value !== null)
        .map(([key, value]) => ({ key, value: String(value ?? ''), originalKey: key }))
      setEntries(filtered)
      originalKeysRef.current = new Set(Object.keys(metadata))
    } else {
      setEntries([])
      originalKeysRef.current = new Set()
    }
  }, [metadata])

  const handleKeyChange = (index: number, newKey: string) => {
    setEntries((prev) => {
      const next = [...prev]
      next[index] = { ...next[index], key: newKey }
      return next
    })
  }

  const handleValueChange = (index: number, newValue: string) => {
    setEntries((prev) => {
      const next = [...prev]
      next[index] = { ...next[index], value: newValue }
      return next
    })
  }

  const handleDelete = (index: number) => {
    setEntries((prev) => prev.filter((_, i) => i !== index))
  }

  const handleAdd = () => {
    setEntries((prev) => [...prev, { key: '', value: '' }])
  }

  const handleSave = async () => {
    const data: Record<string, any> = {}
    const seenKeys = new Set<string>()
    const currentKeys = new Set<string>()

    for (const entry of entries) {
      const k = entry.key.trim()
      if (!k) continue
      if (seenKeys.has(k)) {
        message.warning(`键名 "${k}" 重复，已跳过`)
        continue
      }
      seenKeys.add(k)
      currentKeys.add(k)
      data[k] = entry.value
    }

    // 被删除的原始条目设为 null，表示删除该元数据
    for (const origKey of originalKeysRef.current) {
      if (!currentKeys.has(origKey)) {
        data[origKey] = null
      }
    }

    setSaving(true)
    try {
      await onSave(data)
      message.success('元数据已保存')
      originalKeysRef.current = new Set(currentKeys)
    } catch {
      // 错误已在 api 拦截器中处理
    } finally {
      setSaving(false)
    }
  }

  const isEmpty = entries.length === 0 && !saving

  return (
    <div style={{ padding: '8px 0' }}>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 8,
        }}
      >
        <span style={{ fontWeight: 500, fontSize: 13 }}>{title}</span>
        <Button
          type="primary"
          size="small"
          icon={<SaveOutlined />}
          loading={saving}
          onClick={handleSave}
        >
          保存
        </Button>
      </div>
      {isEmpty ? (
        <div style={{ color: '#999', fontSize: 12, padding: '4px 0' }}>
          暂无元数据，点击下方"添加"按钮新增
        </div>
      ) : (
        entries.map((entry, index) => (
          <Row key={index} gutter={8} style={{ marginBottom: 4 }}>
            <Col span={8}>
              <Input
                size="small"
                placeholder="键名"
                value={entry.key}
                onChange={(e) => handleKeyChange(index, e.target.value)}
              />
            </Col>
            <Col span={14}>
              <Input
                size="small"
                placeholder="值"
                value={entry.value}
                onChange={(e) => handleValueChange(index, e.target.value)}
              />
            </Col>
            <Col span={2}>
              <Button
                type="text"
                size="small"
                danger
                icon={<DeleteOutlined />}
                onClick={() => handleDelete(index)}
              />
            </Col>
          </Row>
        ))
      )}
      <Button
        type="dashed"
        size="small"
        icon={<PlusOutlined />}
        onClick={handleAdd}
        style={{ marginTop: 4 }}
        block
      >
        添加
      </Button>
    </div>
  )
}

export default MetadataEditor
