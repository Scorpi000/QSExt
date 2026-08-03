/**
 * EvalModulePicker - 挖掘评估模块选择器
 *
 * 照搬回测工作台 ModulePicker 的完整交互模式：
 * 下拉选择模块 → 弹窗配置（标签 + 价格因子 + 截面ID + 参数 + Transform + 方向）。
 * 因子选择由 GP 自动处理，无需用户选择。
 * 只保留 SectionFactor 分类的回测模块。
 */

import { useState, useEffect, useCallback } from 'react'
import { Select, Button, Modal, Form, Input, InputNumber, Switch, Space, message, List, Tag, Popconfirm, Radio } from 'antd'
import { PlusOutlined, DeleteOutlined, SettingOutlined } from '@ant-design/icons'
import { getFrameworkConfig } from '../../services/mining'
import { getSectionIdSources, type ParamDef, type SectionIdSource } from '../../services/backtest'
import { useFactorPoolStore } from '../../stores/factorPoolStore'

// ─── 类型 ────────────────────────────────────────────────────

export interface EvalModuleInfo {
  key: string
  name: string
  description: string
  params: ParamDef[]
  requires_price: boolean
  requires_descriptor_ids: boolean
}

export interface EvalModuleConfigItem {
  module: string
  instance_label: string
  params: Record<string, any>
  /** 截面 ID 模式 */
  section_mode: 'auto' | 'source' | 'custom'
  section_source?: string | null
  section_ids?: string[] | null
  /** 价格因子（逐模块独立配置） */
  price_ref?: { conn_id: string; table_name: string; factor_name: string } | null
}

export interface EvalPickerValue {
  modules: EvalModuleConfigItem[]
  transform: string
  sign: 'greater' | 'less'
}

interface EvalModulePickerProps {
  value?: EvalPickerValue
  onChange?: (value: EvalPickerValue) => void
  disabled?: boolean
  /** 截面 ID 源列表（从 backtest 配置加载） */
  sectionSources?: SectionIdSource[]
}

const DEFAULT_VALUE: EvalPickerValue = {
  modules: [],
  transform: 'abs_ic_ir',
  sign: 'greater',
}

// ─── 参数字段渲染 ────────────────────────────────────────────

function renderParamField(param: ParamDef) {
  switch (param.type) {
    case 'int': return <InputNumber style={{ width: '100%' }} placeholder={param.description || param.label} />
    case 'float': return <InputNumber style={{ width: '100%' }} step={0.01} placeholder={param.description || param.label} />
    case 'str': return <Input placeholder={param.description || param.label} />
    case 'bool': return <Switch />
    case 'select': return (
      <Select
        placeholder={param.description || param.label}
        options={param.options?.map((o: string) => ({ value: o, label: o })) || []}
      />
    )
    default: return <Input placeholder={param.description || param.label} />
  }
}

// ─── 组件 ────────────────────────────────────────────────────

function EvalModulePicker({ value = DEFAULT_VALUE, onChange, disabled, sectionSources = [] }: EvalModulePickerProps) {
  const poolItems = useFactorPoolStore((s) => s.items)
  const current = value || DEFAULT_VALUE

  const [modules, setModules] = useState<EvalModuleInfo[]>([])
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [selectedModule, setSelectedModule] = useState<EvalModuleInfo | null>(null)
  const [editingIndex, setEditingIndex] = useState<number | null>(null)
  const [form] = Form.useForm()

  // 弹窗内状态
  const [pickedPriceId, setPickedPriceId] = useState<string | null>(null)
  const [sectionMode, setSectionMode] = useState<'auto' | 'source' | 'custom'>('auto')
  const [sectionSource, setSectionSource] = useState<string | null>(null)
  const [customIds, setCustomIds] = useState('')
  const [selectKey, setSelectKey] = useState(0)

  // 加载 SectionFactor 模块列表
  const loadModules = useCallback(async () => {
    setLoading(true)
    try {
      const config = await getFrameworkConfig('gp') as unknown as Record<string, any>
      setModules((config?.eval_modules || []) as EvalModuleInfo[])
    } catch { /* handled */ }
    finally { setLoading(false) }
  }, [])
  useEffect(() => { loadModules() }, [loadModules])

  // 打开配置弹窗
  const openConfig = (moduleKey: string, index: number | null = null) => {
    const mod = modules.find((m) => m.key === moduleKey)
    if (!mod) return
    setSelectedModule(mod)
    setEditingIndex(index)
    setSectionMode('auto')
    setSectionSource(null)
    setCustomIds('')

    const defaults: Record<string, any> = {}
    mod.params.forEach((p) => {
      if (p.default !== undefined && p.default !== null) defaults[p.name] = p.default
    })

    if (index !== null && current.modules[index]) {
      const existing = current.modules[index]
      form.resetFields()
      form.setFieldsValue({
        _label: existing.instance_label,
        ...existing.params,
      })
      setSectionMode(existing.section_mode || 'auto')
      setSectionSource(existing.section_source || null)
      setCustomIds((existing.section_ids || []).join(', '))
      // 还原价格因子：从 price_ref 反查全局池 ID
      if (existing.price_ref) {
        const ref = existing.price_ref
        const matched = poolItems.find((p) =>
          p.ref?.conn_id === ref.conn_id &&
          p.ref?.table_name === ref.table_name &&
          p.label === ref.factor_name
        )
        setPickedPriceId(matched?.id || null)
      } else {
        setPickedPriceId(null)
      }
    } else {
      form.resetFields()
      form.setFieldsValue({ ...defaults, _label: '' })
      setPickedPriceId(null)
    }
    setModalOpen(true)
  }

  // 确认
  const handleConfirm = () => {
    if (!selectedModule) return
    form.validateFields().then((formValues: any) => {
      const paramNames = new Set(selectedModule.params.map((p) => p.name))
      const params: Record<string, any> = {}
      for (const [key, val] of Object.entries(formValues)) {
        if (paramNames.has(key)) params[key] = val
      }

      // 截面 ID
      let sectionIds: string[] | null = null
      if (sectionMode === 'custom' && customIds.trim()) {
        sectionIds = customIds.split(',').map((s) => s.trim()).filter(Boolean)
        if (sectionIds.length === 0) sectionIds = null
      }

      // 价格因子（逐模块）
      let priceRef: EvalModuleConfigItem['price_ref'] = null
      if (selectedModule.requires_price) {
        const priceItem = pickedPriceId ? poolItems.find((item) => item.id === pickedPriceId) : null
        if (!priceItem) {
          message.warning('该模块需要选择价格因子')
          return
        }
        priceRef = {
          conn_id: priceItem.ref.conn_id || '',
          table_name: priceItem.ref.table_name || '',
          factor_name: priceItem.label,
        }
      }

      const item: EvalModuleConfigItem = {
        module: selectedModule.key,
        instance_label: formValues._label || '',
        params,
        section_mode: sectionMode,
        section_source: sectionMode === 'source' ? sectionSource : null,
        section_ids: sectionIds,
        price_ref: priceRef,
      }

      const newModules = [...current.modules]
      if (editingIndex !== null) {
        newModules[editingIndex] = item
      } else {
        newModules.push(item)
      }

      // Transform & sign 为共享配置
      onChange?.({
        ...current,
        modules: newModules,
      })

      setModalOpen(false)
      setSelectedModule(null)
      setEditingIndex(null)
      setSelectKey((k) => k + 1)
      form.resetFields()
    })
  }

  // 删除
  const handleDelete = (index: number) => {
    const newModules = [...current.modules]
    newModules.splice(index, 1)
    onChange?.({ ...current, modules: newModules })
  }

  const factorOptions = poolItems.map((item) => ({
    value: item.id,
    label: `${item.label} [${item.source === 'registry' ? '注册中心' : '因子库'}]`,
  }))

  return (
    <div>
      {/* 已添加模块列表 */}
      {current.modules.length > 0 && (
        <List
          size="small"
          style={{ marginBottom: 8 }}
          dataSource={current.modules}
          renderItem={(cfg, idx) => {
            const mod = modules.find((m) => m.key === cfg.module)
            const paramStr = Object.entries(cfg.params || {})
              .filter(([, v]) => v !== undefined && v !== null && v !== '')
              .map(([k, v]) => `${k}=${v}`).join(', ')
            const sectionLabel = cfg.section_mode === 'source' ? `截面源:${cfg.section_source}`
              : cfg.section_mode === 'custom' ? `自定义ID` : '自动'
            return (
              <List.Item
                actions={[
                  <Button key="edit" size="small" icon={<SettingOutlined />}
                    disabled={disabled}
                    onClick={() => openConfig(cfg.module, idx)} />,
                  <Popconfirm key="del" title="确定移除？"
                    onConfirm={() => handleDelete(idx)}>
                    <Button size="small" danger icon={<DeleteOutlined />} disabled={disabled} />
                  </Popconfirm>,
                ]}
              >
                <List.Item.Meta
                  title={
                    <Space size={4}>
                      <Tag color="blue">{mod?.name || cfg.module}</Tag>
                      {cfg.instance_label && (
                        <span style={{ fontSize: 12, color: '#999' }}>{cfg.instance_label}</span>
                      )}
                    </Space>
                  }
                  description={
                    <Space size={4} wrap>
                      {paramStr && <span style={{ fontSize: 11, color: '#888' }}>{paramStr}</span>}
                      <Tag style={{ fontSize: 10 }}>{sectionLabel}</Tag>
                    </Space>
                  }
                />
              </List.Item>
            )
          }}
        />
      )}

      {/* 模块选择 */}
      <Space style={{ marginBottom: 8 }}>
        <Select
          key={selectKey}
          style={{ minWidth: 200 }}
          placeholder="选择评估模块..."
          loading={loading}
          onChange={(key) => openConfig(key)}
          disabled={disabled}
          options={modules.map((m) => ({ value: m.key, label: m.name }))}
        />
        <Button type="dashed" icon={<PlusOutlined />} disabled={disabled}>
          添加模块
        </Button>
      </Space>

      {/* Transform + 方向 */}
      <Space wrap>
        <div>
          <span style={{ fontSize: 13, color: '#666', marginRight: 8 }}>Transform</span>
          <Select
            style={{ width: 200 }}
            value={current.transform}
            onChange={(v) => onChange?.({ ...current, transform: v })}
            disabled={disabled}
            options={[
              { value: 'abs_ic_ir', label: 'abs(IC_IR)' },
            ]}
          />
        </div>
        <div>
          <span style={{ fontSize: 13, color: '#666', marginRight: 8 }}>优化方向</span>
          <Select
            style={{ width: 140 }}
            value={current.sign}
            onChange={(v) => onChange?.({ ...current, sign: v })}
            disabled={disabled}
            options={[
              { value: 'greater', label: '越大越好' },
              { value: 'less', label: '越小越好' },
            ]}
          />
        </div>
      </Space>

      {/* 配置弹窗 */}
      <Modal
        title={selectedModule ? `配置: ${selectedModule.name}` : '配置评估模块'}
        open={modalOpen}
        onCancel={() => {
          setModalOpen(false)
          setSelectedModule(null)
          setEditingIndex(null)
          setSelectKey((k) => k + 1)
          form.resetFields()
        }}
        onOk={handleConfirm}
        width={560}
        okText={editingIndex !== null ? '保存修改' : '加入列表'}
        cancelText="取消"
      >
        {selectedModule && (
          <div>
            {selectedModule.description && (
              <div style={{
                marginBottom: 16, padding: '8px 12px', background: '#f6f8fa',
                borderRadius: 6, fontSize: 13, color: '#666',
              }}>
                {selectedModule.description}
              </div>
            )}

            {/* 实例标签 */}
            <Form form={form} layout="vertical">
              <Form.Item name="_label" label="实例标签（可选）">
                <Input placeholder="给该模块起个名字" />
              </Form.Item>
            </Form>

            {/* 价格因子（逐模块） */}
            {selectedModule.requires_price && (
              <div style={{ marginBottom: 16 }}>
                <div style={{ marginBottom: 4, fontWeight: 500 }}>
                  选择价格因子
                  {poolItems.length === 0 && (
                    <span style={{ color: '#999', fontWeight: 400, fontSize: 12 }}>
                      （请先在全局因子池中添加因子）
                    </span>
                  )}
                </div>
                <Select
                  style={{ width: '100%' }}
                  placeholder="从全局因子池中选择（如 close）"
                  value={pickedPriceId}
                  onChange={setPickedPriceId}
                  allowClear
                  options={factorOptions}
                />
              </div>
            )}

            {/* 截面 ID */}
            {selectedModule.requires_descriptor_ids && (
              <div style={{ marginBottom: 16 }}>
                <div style={{ marginBottom: 4, fontWeight: 500 }}>截面 ID</div>
                <Radio.Group
                  value={sectionMode}
                  onChange={(e) => setSectionMode(e.target.value)}
                  optionType="button"
                  size="small"
                  style={{ marginBottom: 8 }}
                >
                  <Radio.Button value="auto">自动获取</Radio.Button>
                  <Radio.Button value="source" disabled={sectionSources.length === 0}>配置源</Radio.Button>
                  <Radio.Button value="custom">自定义</Radio.Button>
                </Radio.Group>
                {sectionMode === 'source' && (
                  <Select
                    style={{ width: '100%' }}
                    placeholder="选择截面 ID 源"
                    value={sectionSource}
                    onChange={setSectionSource}
                    options={sectionSources.map((s) => ({
                      value: s.name,
                      label: `${s.name} (${s.method})`,
                    }))}
                  />
                )}
                {sectionMode === 'custom' && (
                  <Input.TextArea
                    rows={2}
                    value={customIds}
                    onChange={(e) => setCustomIds(e.target.value)}
                    placeholder="逗号分隔，例如: 000001.SZ,000002.SZ"
                  />
                )}
              </div>
            )}

            {/* 参数配置 */}
            {selectedModule.params.length > 0 && (
              <div style={{ marginTop: 8 }}>
                <div style={{ marginBottom: 8, fontWeight: 500 }}>参数配置</div>
                <Form form={form} layout="vertical">
                  {selectedModule.params.map((param) => (
                    <Form.Item
                      key={param.name}
                      name={param.name}
                      label={param.label}
                      rules={param.required ? [{ required: true, message: `请输入${param.label}` }] : []}
                      extra={param.description}
                    >
                      {renderParamField(param)}
                    </Form.Item>
                  ))}
                </Form>
              </div>
            )}
            {selectedModule.params.length === 0 && (
              <div style={{ color: '#999', marginBottom: 16 }}>该模块无需额外参数</div>
            )}

          </div>
        )}
      </Modal>
    </div>
  )
}

export default EvalModulePicker
