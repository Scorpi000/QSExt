/**
 * 策略代码编辑器 —— Monaco Editor 封装
 */
import React, { useCallback } from 'react'
import { Button, Space, Typography, message, Input, Modal } from 'antd'
import { SaveOutlined, PlayCircleOutlined, EyeOutlined } from '@ant-design/icons'
import type { StrategySearchResult } from '../../services/strategy'
import { importStrategy, previewStrategyImport } from '../../services/strategy'

const { Text } = Typography

interface StrategyEditorProps {
  code: string
  onChange: (code: string) => void
  isNew: boolean
  selectedStrategy: StrategySearchResult | null
}

const StrategyEditor: React.FC<StrategyEditorProps> = ({
  code,
  onChange,
  isNew,
  selectedStrategy,
}) => {
  // 保存策略
  const handleSave = useCallback(async () => {
    const filename = selectedStrategy?.Name || undefined
    try {
      const result = await importStrategy(code, filename)
      if (result.valid) {
        message.success(`策略已保存: ${result.filepath}`)
      }
    } catch (err: any) {
      message.error(`保存失败: ${err?.response?.data?.detail || err.message}`)
    }
  }, [code, selectedStrategy])

  // 预览元信息
  const handlePreview = useCallback(async () => {
    try {
      const result = await previewStrategyImport(code)
      if (result.valid) {
        Modal.info({
          title: '策略元信息预览',
          width: 600,
          content: (
            <pre style={{ fontSize: 12, maxHeight: 400, overflow: 'auto' }}>
              {JSON.stringify(result.meta, null, 2)}
            </pre>
          ),
        })
      } else {
        Modal.error({
          title: '元信息验证失败',
          content: (
            <ul>
              {result.errors.map((e, i) => (
                <li key={i}>{e}</li>
              ))}
            </ul>
          ),
        })
      }
    } catch (err: any) {
      message.error(`预览失败: ${err.message}`)
    }
  }, [code])

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* 工具栏 */}
      <div
        style={{
          padding: '8px 12px',
          borderBottom: '1px solid #f0f0f0',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}
      >
        <Space>
          <Text strong>
            {isNew ? '新建策略' : selectedStrategy?.Name || '策略编辑器'}
          </Text>
          {selectedStrategy?.QSID && (
            <Text type="secondary" style={{ fontSize: 12 }}>
              QSID: {selectedStrategy.QSID.slice(0, 16)}...
            </Text>
          )}
        </Space>
        <Space>
          <Button icon={<EyeOutlined />} size="small" onClick={handlePreview}>
            预览元信息
          </Button>
          <Button type="primary" icon={<SaveOutlined />} size="small" onClick={handleSave}>
            保存策略
          </Button>
        </Space>
      </div>

      {/* 编辑器区域 —— 使用 textarea 作为 Monaco 的简化替代 */}
      <div style={{ flex: 1, minHeight: 0 }}>
        <textarea
          value={code}
          onChange={(e) => onChange(e.target.value)}
          style={{
            width: '100%',
            height: '100%',
            border: 'none',
            resize: 'none',
            padding: '12px',
            fontFamily: "'Cascadia Code', 'Fira Code', 'Consolas', monospace",
            fontSize: 13,
            lineHeight: 1.6,
            tabSize: 4,
            outline: 'none',
            background: '#1e1e1e',
            color: '#d4d4d4',
          }}
          spellCheck={false}
        />
      </div>
    </div>
  )
}

export default StrategyEditor
