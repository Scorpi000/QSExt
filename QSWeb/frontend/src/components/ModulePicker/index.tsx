/**
 * ModulePicker - 回测模块选择器
 *
 * 从全局因子池（Zustand store）中选择因子和价格因子，支持预配置的截面 ID 源。
 */

import { useState, useEffect, useCallback } from 'react'
import { Select, Button, Modal, Form, Input, InputNumber, Switch, Space, message, Radio } from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import type { ModuleInfo, ModuleRunConfig, FactorRef, PriceRef, ParamDef, SectionIdSource } from '../../services/backtest'
import { getBacktestModules } from '../../services/backtest'
import { useFactorPoolStore } from '../../stores/factorPoolStore'
import type { PoolItem } from '../../types/pool'

interface ModulePickerProps {
  onAdd: (config: ModuleRunConfig) => void
  /** 截面 ID 源列表 */
  sectionSources: SectionIdSource[]
}

/** 将 PoolItem 转换为后端 FactorRef */
function poolItemToFactorRef(item: PoolItem): FactorRef {
  if (item.source === 'registry') {
    return { source: 'registry', name: item.qsid }
  }
  return {
    source: 'db',
    name: item.label,
    conn_id: item.ref.conn_id,
    table_name: item.ref.table_name,
  }
}

function ModulePicker({ onAdd, sectionSources }: ModulePickerProps) {
  const poolItems = useFactorPoolStore((s) => s.items)
  const selectedIds = useFactorPoolStore((s) => s.selectedIds)

  const [modules, setModules] = useState<ModuleInfo[]>([])
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [selectedModule, setSelectedModule] = useState<ModuleInfo | null>(null)
  const [form] = Form.useForm()

  // 本模块选择的因子和价格因子（从全局池中选）
  const [pickedFactorIds, setPickedFactorIds] = useState<string[]>([])
  const [pickedPriceId, setPickedPriceId] = useState<string | null>(null)

  // 截面模式: 'source' | 'custom' | 'auto'
  const [sectionMode, setSectionMode] = useState<'source' | 'custom' | 'auto'>('auto')
  const [sectionSource, setSectionSource] = useState<string | null>(null)
  const [customIds, setCustomIds] = useState('')

  // ─── 加载模块列表 ─────────────────────────────────────────
  const loadModules = useCallback(async () => {
    setLoading(true)
    try { const data = await getBacktestModules(); setModules(data as unknown as ModuleInfo[]) }
    catch { /* handled */ }
    finally { setLoading(false) }
  }, [])
  useEffect(() => { loadModules() }, [loadModules])

  // ─── 打开配置对话框 ──────────────────────────────────────
  const handleModuleSelect = (moduleKey: string) => {
    const mod = modules.find((m) => m.key === moduleKey)
    if (!mod) return
    setSelectedModule(mod)
    setPickedFactorIds([])
    setPickedPriceId(null)
    setSectionMode('auto')
    setSectionSource(null)
    setCustomIds('')
    const defaults: Record<string, any> = {}
    mod.params.forEach((p) => { if (p.default !== undefined && p.default !== null) defaults[p.name] = p.default })
    form.resetFields()
    form.setFieldsValue(defaults)
    setModalOpen(true)
  }

  // ─── 确认添加 ─────────────────────────────────────────────
  const handleConfirm = () => {
    if (!selectedModule) return
    form.validateFields().then((values) => {
      if (pickedFactorIds.length === 0) { message.warning('请从全局因子池中选择至少一个因子'); return }

      const paramNames = new Set(selectedModule.params.map((p) => p.name))
      const params: Record<string, any> = {}
      for (const [key, val] of Object.entries(values)) {
        if (paramNames.has(key)) params[key] = val
      }

      // 价格因子：从全局因子池中查找
      const priceItem = pickedPriceId
        ? poolItems.find((item) => item.id === pickedPriceId)
        : null
      let priceRef: PriceRef | null = null
      if (selectedModule.requires_price && priceItem) {
        priceRef = {
          conn_id: priceItem.ref.conn_id || '',
          table_name: priceItem.ref.table_name || '',
          factor_name: priceItem.label,
        }
      } else if (selectedModule.requires_price) {
        message.warning('该模块需要价格因子'); return
      }

      // 截面 ID
      let descriptorSource: string | null = null
      let descriptorIds: string[] | null = null
      if (sectionMode === 'source' && sectionSource) {
        descriptorSource = sectionSource
      } else if (sectionMode === 'custom' && customIds.trim()) {
        descriptorIds = customIds.split(',').map((s) => s.trim()).filter(Boolean)
        if (descriptorIds.length === 0) descriptorIds = null
      }
      // 'auto': both null → backend auto-detects

      const pickedItems = poolItems.filter((item) => pickedFactorIds.includes(item.id))

      const config: ModuleRunConfig = {
        module_key: selectedModule.key,
        instance_label: values._label || '',
        factor_refs: pickedItems.map(poolItemToFactorRef),
        params,
        price_ref: priceRef,
        descriptor_source: descriptorSource,
        descriptor_ids: descriptorIds,
      }
      onAdd(config)
      setModalOpen(false)
      setSelectedModule(null)
      form.resetFields()
    })
  }

  // ─── 渲染参数表单 ─────────────────────────────────────────
  const renderParamField = (param: ParamDef) => {
    switch (param.type) {
      case 'int': return <InputNumber style={{ width: '100%' }} placeholder={param.description || param.label} />
      case 'float': return <InputNumber style={{ width: '100%' }} step={0.01} placeholder={param.description || param.label} />
      case 'str': return <Input placeholder={param.description || param.label} />
      case 'bool': return <Switch />
      case 'select': return <Select placeholder={param.description || param.label}
          options={param.options?.map((o) => ({ value: o, label: o })) || []} />
      default: return <Input placeholder={param.description || param.label} />
    }
  }

  // ─── 渲染 ─────────────────────────────────────────────────
  const factorOptions = poolItems.map((item) => ({
    value: item.id,
    label: `${item.label} [${item.source === 'registry' ? '注册中心' : '因子库'}]`,
  }))

  return (
    <>
      <Space>
        <Select style={{ minWidth: 200 }} placeholder="选择回测模块..." loading={loading}
          value={undefined} onChange={handleModuleSelect}
          options={modules.map((m) => ({ value: m.key, label: `${m.name} (${m.category})` }))} />
        <Button type="dashed" icon={<PlusOutlined />}>添加模块</Button>
      </Space>

      <Modal title={selectedModule ? `配置: ${selectedModule.name}` : '配置回测模块'}
        open={modalOpen} onCancel={() => { setModalOpen(false); setSelectedModule(null); form.resetFields() }}
        onOk={handleConfirm} width={640} okText="加入待运行列表" cancelText="取消">
        {selectedModule && (
          <div>
            {selectedModule.description && (
              <div style={{ marginBottom: 16, padding: '8px 12px', background: '#f6f8fa', borderRadius: 6, fontSize: 13, color: '#666' }}>
                {selectedModule.description}
              </div>
            )}
            <Form form={form} layout="vertical">
              <Form.Item name="_label" label="实例标签（可选）">
                <Input placeholder="给该模块起个名字" />
              </Form.Item>
            </Form>

            {/* 从全局因子池中选择 */}
            <div style={{ marginBottom: 16 }}>
              <div style={{ marginBottom: 4, fontWeight: 500 }}>
                选择因子
                {poolItems.length === 0 && <span style={{ color: '#999', fontWeight: 400, fontSize: 12 }}>（请先在左侧全局因子池中添加因子）</span>}
              </div>
              <Select mode="multiple" style={{ width: '100%' }} placeholder="从全局因子池中选择"
                value={pickedFactorIds} onChange={setPickedFactorIds}
                options={factorOptions} />
            </div>

            {/* 从全局因子池中选择价格因子 */}
            {selectedModule.requires_price && (
              <div style={{ marginBottom: 16 }}>
                <div style={{ marginBottom: 4, fontWeight: 500 }}>
                  选择价格因子
                  {poolItems.length === 0 && <span style={{ color: '#999', fontWeight: 400, fontSize: 12 }}>（请先在左侧全局因子池中添加因子）</span>}
                </div>
                <Select style={{ width: '100%' }} placeholder="从全局因子池中选择"
                  value={pickedPriceId} onChange={setPickedPriceId} allowClear
                  options={factorOptions} />
              </div>
            )}

            {/* 截面 ID */}
            {selectedModule.requires_descriptor_ids && (
              <div style={{ marginBottom: 16 }}>
                <div style={{ marginBottom: 4, fontWeight: 500 }}>截面 ID</div>
                <Radio.Group value={sectionMode} onChange={(e) => setSectionMode(e.target.value)}
                  optionType="button" size="small" style={{ marginBottom: 8 }}>
                  <Radio.Button value="auto">自动获取</Radio.Button>
                  <Radio.Button value="source" disabled={sectionSources.length === 0}>配置源</Radio.Button>
                  <Radio.Button value="custom">自定义</Radio.Button>
                </Radio.Group>
                {sectionMode === 'source' && (
                  <Select style={{ width: '100%' }} placeholder="选择截面 ID 源"
                    value={sectionSource} onChange={setSectionSource}
                    options={sectionSources.map((s) => ({ value: s.name, label: `${s.name} (${s.method})` }))} />
                )}
                {sectionMode === 'custom' && (
                  <Input.TextArea rows={2} value={customIds} onChange={(e) => setCustomIds(e.target.value)}
                    placeholder="逗号分隔，例如: 000001.SZ,000002.SZ" />
                )}
              </div>
            )}

            {/* 参数配置 */}
            {selectedModule.params.length > 0 && (
              <div style={{ marginTop: 8 }}>
                <div style={{ marginBottom: 8, fontWeight: 500 }}>参数配置</div>
                <Form form={form} layout="vertical">
                  {selectedModule.params.map((param) => (
                    <Form.Item key={param.name} name={param.name} label={param.label}
                      rules={param.required ? [{ required: true, message: `请输入${param.label}` }] : []}
                      extra={param.description}>
                      {renderParamField(param)}
                    </Form.Item>
                  ))}
                </Form>
              </div>
            )}
          </div>
        )}
      </Modal>
    </>
  )
}

export default ModulePicker
