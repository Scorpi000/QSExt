/**
 * QSArgs JSON Schema 动态表单组件
 *
 * 根据 QSArgs 的 Pydantic JSON Schema 自动渲染表单，
 * 使用 @rjsf/antd (react-jsonschema-form)。
 * frozen=True 字段渲染为禁用状态，exclude=True 字段不展示。
 */

import { useEffect, useState } from 'react'
import { Spin, Empty, message, Alert } from 'antd'
import Form from '@rjsf/antd'
import validator from '@rjsf/validator-ajv8'
import { getArgsSchema } from '../../services/registry'

interface ArgFormProps {
  /** 算子 class_name: module.path.ClassName */
  className?: string
  /** 直接传入的 JSON Schema（优先级高于 className） */
  schema?: Record<string, any>
  /** 表单数据变化回调 */
  onChange?: (data: any) => void
  /** 提交回调 */
  onSubmit?: (data: any) => void
  /** 初始值 */
  formData?: Record<string, any>
}

function ArgForm({ className, schema: propSchema, onChange, onSubmit, formData }: ArgFormProps) {
  const [schema, setSchema] = useState<Record<string, any> | null>(propSchema || null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (propSchema) {
      setSchema(propSchema)
      return
    }
    if (!className) {
      setSchema(null)
      return
    }

    setLoading(true)
    setError(null)
    getArgsSchema(className)
      .then((data) => {
        setSchema(data as unknown as Record<string, any>)
      })
      .catch((err) => {
        const msg = err?.response?.data?.message || err?.message || '加载参数 Schema 失败'
        setError(msg)
        message.error(msg)
      })
      .finally(() => {
        setLoading(false)
      })
  }, [className, propSchema])

  if (!className && !propSchema) {
    return <Empty description="选择算子后可配置参数" image={Empty.PRESENTED_IMAGE_SIMPLE} />
  }

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: 20 }}>
        <Spin tip="加载参数配置..." />
      </div>
    )
  }

  if (error) {
    return <Alert type="error" message={error} showIcon />
  }

  if (!schema || Object.keys(schema).length === 0) {
    return <Empty description="无参数可配置" image={Empty.PRESENTED_IMAGE_SIMPLE} style={{ padding: '16px 0' }} />
  }

  // 提取 properties 作为表单 schema
  const formSchema: Record<string, any> = {
    type: 'object',
    properties: schema.properties || {},
  }

  if (schema.required) {
    formSchema.required = schema.required
  }

  return (
    <div style={{ padding: '8px 0' }}>
      <Form
        schema={formSchema}
        validator={validator}
        formData={formData}
        onChange={(e) => onChange?.(e.formData)}
        onSubmit={(e) => onSubmit?.(e.formData)}
        onError={(errors) => console.debug('Form validation errors:', errors)}
        noHtml5Validate
        showErrorList={false}
      >
        {/* 不渲染默认提交按钮，由外部控制 */}
        <div style={{ display: 'none' }} />
      </Form>
    </div>
  )
}

export default ArgForm
