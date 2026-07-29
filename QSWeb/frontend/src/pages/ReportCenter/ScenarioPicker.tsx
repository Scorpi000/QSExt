/**
 * ScenarioPicker - 报告场景选择和生成表单
 *
 * 场景选择 → 参数配置 → 因子池选择 → 提交生成。
 */

import { Form, Select, Input, DatePicker, Checkbox, Space, Collapse } from 'antd'
import dayjs from 'dayjs'
import type { ReportScenario, FactorRef } from '../../services/report'
import { useFactorPoolStore } from '../../stores/factorPoolStore'

const { RangePicker } = DatePicker

// ─── 从全局因子池选择单个因子 ─────────────────────────────

interface PoolRefPickerProps {
  value?: FactorRef
  onChange?: (ref: FactorRef | undefined) => void
  label?: string
  allowClear?: boolean
}

function PoolRefPicker({ value, onChange, label, allowClear }: PoolRefPickerProps) {
  const poolItems = useFactorPoolStore((s) => s.items)

  const selectedId = value
    ? poolItems.find((item) =>
        item.ref.conn_id === value.conn_id &&
        item.ref.table_name === value.table_name &&
        (item.label === value.factor_name || item.qsid === value.factor_name)
      )?.id || null
    : null

  const handleSelect = (id: string | null) => {
    if (!id) { onChange?.(undefined); return }
    const item = poolItems.find((p) => p.id === id)
    if (!item) return
    onChange?.({ conn_id: item.ref.conn_id || '', table_name: item.ref.table_name || '', factor_name: item.label })
  }

  return (
    <Space wrap>
      {label && <span style={{ fontSize: 13, color: '#666', minWidth: 80 }}>{label}</span>}
      <Select
        placeholder="从因子池选择" style={{ width: 300 }} value={selectedId || undefined}
        onChange={handleSelect} allowClear={allowClear}
        showSearch
        filterOption={(input, option) => (option?.label as string)?.toLowerCase().includes(input.toLowerCase())}
        options={poolItems
          .map((item) => ({
            value: item.id,
            label: `${item.label} [${item.source === 'registry' ? '注册中心' : item.ref.table_name || '因子库'}]`,
          }))}
      />
    </Space>
  )
}

// ─── ScenarioPicker ────────────────────────────────────────

interface ScenarioPickerProps {
  scenarios: ReportScenario[]
  scenario: string
  reportName: string
  priceRef: FactorRef | undefined
  maskRef: FactorRef | undefined
  catDataRef: FactorRef | undefined
  weightRef: FactorRef | undefined
  dateRange: [string, string] | null
  outputFormats: string[]
  modules: Record<string, boolean>
  onScenarioChange: (scenario: string) => void
  onReportNameChange: (name: string) => void
  onPriceRefChange: (ref: FactorRef | undefined) => void
  onMaskRefChange: (ref: FactorRef | undefined) => void
  onCatDataRefChange: (ref: FactorRef | undefined) => void
  onWeightRefChange: (ref: FactorRef | undefined) => void
  onDateRangeChange: (range: [string, string] | null) => void
  onOutputFormatsChange: (formats: string[]) => void
  onModulesChange: (modules: Record<string, boolean>) => void
}

function ScenarioPicker({
  scenarios, scenario, reportName,
  priceRef, maskRef, catDataRef, weightRef,
  dateRange, outputFormats, modules,
  onScenarioChange, onReportNameChange,
  onPriceRefChange, onMaskRefChange, onCatDataRefChange, onWeightRefChange,
  onDateRangeChange, onOutputFormatsChange, onModulesChange,
}: ScenarioPickerProps) {
  const currentScenario = scenarios.find((s) => s.key === scenario)

  return (
    <Form layout="vertical">
      <Form.Item label="报告场景">
        <Select value={scenario} onChange={onScenarioChange} style={{ width: 240 }}
          options={scenarios.map((s) => ({ value: s.key, label: s.name }))} />
        {currentScenario && (
          <div style={{ color: '#999', fontSize: 12, marginTop: 4 }}>{currentScenario.description}</div>
        )}
      </Form.Item>

      <Form.Item label="报告名称">
        <Input placeholder="可选，留空使用默认名称" value={reportName}
          onChange={(e) => onReportNameChange(e.target.value)} style={{ width: 320 }} />
      </Form.Item>

      <Form.Item label="被测因子（必选）" required>
        <span style={{ color: '#999', fontSize: 12 }}>
          请在右侧因子池面板中勾选需要纳入报告的因子
        </span>
      </Form.Item>

      <Form.Item label="价格因子（可选，用于计算收益率）">
        <PoolRefPicker value={priceRef} onChange={onPriceRefChange} allowClear />
      </Form.Item>

      <Collapse ghost size="small" items={[{
        key: 'optional',
        label: '其他可选因子 (Mask / 行业 / 权重)',
        children: (
          <>
            <Form.Item label="Mask 因子">
              <PoolRefPicker value={maskRef} onChange={onMaskRefChange} allowClear />
            </Form.Item>
            <Form.Item label="行业/分类因子">
              <PoolRefPicker value={catDataRef} onChange={onCatDataRefChange} allowClear />
            </Form.Item>
            <Form.Item label="权重因子">
              <PoolRefPicker value={weightRef} onChange={onWeightRefChange} allowClear />
            </Form.Item>
          </>
        ),
      }]} />

      <Form.Item label="日期范围" required>
        <RangePicker
          value={dateRange ? [dayjs(dateRange[0]), dayjs(dateRange[1])] : null}
          onChange={(dates) => {
            if (dates && dates[0] && dates[1]) {
              onDateRangeChange([dates[0].format('YYYY-MM-DD'), dates[1].format('YYYY-MM-DD')])
            } else {
              onDateRangeChange(null)
            }
          }} />
      </Form.Item>

      <Form.Item label="输出格式">
        <Checkbox.Group value={outputFormats}
          onChange={(vals) => onOutputFormatsChange(vals as string[])}
          options={[{ label: 'HTML', value: 'html' }, { label: 'Markdown', value: 'markdown' }]} />
      </Form.Item>

      {currentScenario && currentScenario.module_options.length > 0 && (
        <Form.Item label="分析模块">
          <Space wrap>
            {currentScenario.module_options.map((mod) => (
              <Checkbox key={mod} checked={modules[mod] !== false}
                onChange={(e) => onModulesChange({ ...modules, [mod]: e.target.checked })}>
                {{ ic: 'IC 分析', ic_decay: 'IC 衰减', quantile_portfolio: '分位数组合', factor_turnover: '因子换手率' }[mod] || mod}
              </Checkbox>
            ))}
          </Space>
        </Form.Item>
      )}
    </Form>
  )
}

export default ScenarioPicker
