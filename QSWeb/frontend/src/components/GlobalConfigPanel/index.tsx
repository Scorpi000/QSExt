/**
 * GlobalConfigPanel - 全局配置面板
 *
 * 嵌入 MainLayout 右侧面板的"全局配置" Tab。
 * 读写同一个 Zustand store (useGlobalConfigStore)，持久化到 QSWebConfig.yaml。
 */

import { useEffect, useState } from 'react'
import { Form, Input, Select, Button, Row, Col, Spin, Alert, message, Checkbox, Tooltip } from 'antd'
import { SaveOutlined, ReloadOutlined, InfoCircleOutlined } from '@ant-design/icons'
import { useGlobalConfigStore } from '../../stores/globalConfigStore'
import type { GlobalConfig } from '../../services/globalConfig'

const ENGINE_DEFAULTS: Record<string, Record<string, any>> = {
  CalcEngine: {},
  ParallelEngine: { n_workers: 4 },
}

const ENGINE_OPTIONS = [
  { value: 'CalcEngine', label: 'CalcEngine — 单进程计算' },
  { value: 'ParallelEngine', label: 'ParallelEngine — 多进程并行' },
]

function GlobalConfigPanel() {
  const { config, loading, error, fetchConfig, saveConfig } = useGlobalConfigStore()
  const [saving, setSaving] = useState(false)
  const [useTempCache, setUseTempCache] = useState(false)
  const [form] = Form.useForm()

  // 首次加载
  useEffect(() => {
    if (!config) {
      fetchConfig()
    }
  }, [config, fetchConfig])

  // 配置回填表单
  useEffect(() => {
    if (config) {
      const paramsList = Object.entries(config.engine.params).map(
        ([key, value]) => ({ key, value: String(value) })
      )
      const tempCache = config.use_temp_cache || false
      setUseTempCache(tempCache)
      form.setFieldsValue({
        cache_dir: config.cache_dir,
        use_temp_cache: tempCache,
        engine_type: config.engine.type,
        engine_params: paramsList.length > 0 ? paramsList : [{ key: '', value: '' }],
      })
    }
  }, [config, form])

  // 切换引擎类型时重置参数为默认值
  const handleEngineChange = (engineType: string) => {
    const defaults = ENGINE_DEFAULTS[engineType] || {}
    const paramsList = Object.entries(defaults).map(
      ([key, value]) => ({ key, value: String(value) })
    )
    form.setFieldsValue({
      engine_type: engineType,
      engine_params: paramsList.length > 0 ? paramsList : [{ key: '', value: '' }],
    })
  }

  const handleSave = async () => {
    try {
      const values = await form.validateFields()
      const engineParams: Record<string, any> = {}
      for (const row of values.engine_params || []) {
        if (row.key && row.key.trim()) {
          engineParams[row.key.trim()] = row.value ?? ''
        }
      }
      const newConfig: GlobalConfig = {
        cache_dir: values.cache_dir,
        use_temp_cache: values.use_temp_cache || false,
        engine: {
          type: values.engine_type,
          params: engineParams,
        },
      }
      setSaving(true)
      await saveConfig(newConfig)
      message.success('全局配置已保存')
    } catch (e: any) {
      if (e?.errorFields) return // 表单验证错误
    } finally {
      setSaving(false)
    }
  }

  // ─── 加载态 ────────────────────────────────────────────────
  if (loading && !config) {
    return <Spin size="small" style={{ display: 'block', margin: '24px auto' }} />
  }

  // ─── 错误态 ────────────────────────────────────────────────
  if (error && !config) {
    return (
      <Alert
        type="error"
        message="加载配置失败"
        description={error}
        showIcon
        style={{ margin: 12 }}
        action={
          <Button size="small" icon={<ReloadOutlined />} onClick={fetchConfig}>
            重试
          </Button>
        }
      />
    )
  }

  // ─── 正常态 ────────────────────────────────────────────────
  return (
    <div style={{ padding: '8px 0' }}>
      <Form
        form={form}
        layout="vertical"
        size="small"
        initialValues={{
          engine_params: [{ key: '', value: '' }],
        }}
      >
        <Form.Item
          name="cache_dir"
          label="缓存目录"
          rules={[{ required: true, message: '请输入缓存目录路径' }]}
        >
          <Input
            placeholder="例如: D:/Data/QSCache"
            disabled={useTempCache}
          />
        </Form.Item>

        <Form.Item name="use_temp_cache" valuePropName="checked">
          <Checkbox
            onChange={(e) => {
              setUseTempCache(e.target.checked)
              if (e.target.checked) {
                form.setFieldsValue({ cache_dir: '%TEMP%' })
              } else {
                form.setFieldsValue({ cache_dir: '' })
              }
            }}
          >
            使用系统临时目录
            <Tooltip title="勾选后将使用操作系统临时目录（如 %TEMP%），每次重启后缓存自动清除">
              <InfoCircleOutlined style={{ marginLeft: 4, color: '#999', fontSize: 12 }} />
            </Tooltip>
          </Checkbox>
        </Form.Item>

        <Form.Item
          name="engine_type"
          label="计算引擎"
          rules={[{ required: true, message: '请选择计算引擎' }]}
        >
          <Select options={ENGINE_OPTIONS} onChange={handleEngineChange} />
        </Form.Item>

        <Form.Item label="引擎参数">
          <Form.List name="engine_params">
            {(fields, { add, remove }) => (
              <>
                {fields.map(({ key, name, ...restField }) => (
                  <Row gutter={4} key={key} style={{ marginBottom: 4 }}>
                    <Col span={10}>
                      <Form.Item
                        {...restField}
                        name={[name, 'key']}
                        noStyle
                        rules={[
                          {
                            validator: (_, value) => {
                              const allKeys = form
                                .getFieldValue('engine_params')
                                ?.map((r: any) => r?.key)
                                .filter(Boolean)
                              if (value && allKeys?.filter((k: string) => k === value).length > 1) {
                                return Promise.reject('参数名重复')
                              }
                              return Promise.resolve()
                            },
                          },
                        ]}
                      >
                        <Input placeholder="参数名" />
                      </Form.Item>
                    </Col>
                    <Col span={10}>
                      <Form.Item {...restField} name={[name, 'value']} noStyle>
                        <Input placeholder="参数值" />
                      </Form.Item>
                    </Col>
                    <Col span={4}>
                      <Button
                        danger
                        size="small"
                        block
                        onClick={() => remove(name)}
                        disabled={fields.length === 1}
                      >
                        删
                      </Button>
                    </Col>
                  </Row>
                ))}
                <Button type="dashed" size="small" onClick={() => add({ key: '', value: '' })} block>
                  + 添加参数
                </Button>
              </>
            )}
          </Form.List>
        </Form.Item>

        <Button
          type="primary"
          icon={<SaveOutlined />}
          loading={saving}
          onClick={handleSave}
          block
          style={{ marginTop: 8 }}
        >
          保存配置
        </Button>
      </Form>
    </div>
  )
}

export default GlobalConfigPanel
