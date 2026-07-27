/**
 * 回测配置表单
 *
 * 统一的回测配置表单：因子选择、分析类型、参数配置。
 */

import { useEffect, useState } from 'react'
import {
  Form,
  Select,
  InputNumber,
  DatePicker,
  Button,
  Card,
  Divider,
  Radio,
  Alert,
} from 'antd'
import { PlayCircleOutlined } from '@ant-design/icons'
import { getConnections, type Connection } from '../../services/connection'
import { getTables, getFactors, type FactorTable, type FactorInfo } from '../../services/factor'
import { useBacktestStudioStore } from '../../stores/backtestStudio'
import dayjs from 'dayjs'

interface Props {
  onRunIC: () => void
  onRunQuantile: () => void
  onRunTurnover: () => void
  onRunStrategy: () => void
  loading: boolean
}

function BacktestConfig({ onRunIC, onRunQuantile, onRunTurnover, onRunStrategy, loading }: Props) {
  const [form] = Form.useForm()

  const [connections, setConnections] = useState<Array<{ id: string; name: string; db_type: string }>>([])
  const [tables, setTables] = useState<string[]>([])
  const [factors, setFactors] = useState<string[]>([])

  const store = useBacktestStudioStore()

  // 加载连接列表
  useEffect(() => {
    getConnections().then((data: unknown) => setConnections(data as Connection[])).catch(() => {})
  }, [])

  // 连接变更 → 加载表列表
  const handleConnChange = async (connId: string) => {
    store.setConnId(connId)
    setTables([])
    setFactors([])
    form.setFieldsValue({ table_name: undefined, factor_name: undefined })
    if (!connId) return
    try {
      const result: unknown = await getTables(connId)
      setTables((result as FactorTable[]).map((t) => t.name))
    } catch {
      setTables([])
    }
  }

  // 表变更 → 加载因子列表
  const handleTableChange = async (tableName: string) => {
    store.setTableName(tableName)
    setFactors([])
    form.setFieldsValue({ factor_name: undefined })
    if (!store.connId || !tableName) return
    try {
      const result: unknown = await getFactors(store.connId, tableName)
      setFactors((result as FactorInfo[]).map((f) => f.name))
    } catch {
      setFactors([])
    }
  }

  const canRun = store.connId && store.tableName && store.factorName

  return (
    <Card title="回测配置" size="small">
      {!canRun && (
        <Alert
          message="请先选择连接、因子表和因子"
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
        />
      )}

      <Form
        form={form}
        layout="horizontal"
        labelCol={{ span: 6 }}
        wrapperCol={{ span: 18 }}
        size="small"
      >
        {/* 因子选择 */}
        <Form.Item label="连接" required>
          <Select
            showSearch
            placeholder="选择因子库连接"
            optionFilterProp="label"
            onChange={handleConnChange}
            options={connections.map((c) => ({ label: c.name, value: c.id }))}
          />
        </Form.Item>

        <Form.Item label="因子表" required>
          <Select
            showSearch
            placeholder="选择因子表"
            optionFilterProp="label"
            onChange={handleTableChange}
            options={tables.map((t) => ({ label: t, value: t }))}
          />
        </Form.Item>

        <Form.Item label="因子" required>
          <Select
            showSearch
            placeholder="选择因子"
            optionFilterProp="label"
            onChange={(v) => store.setFactorName(v)}
            options={factors.map((f) => ({ label: f, value: f }))}
          />
        </Form.Item>

        <Divider style={{ margin: '12px 0' }} />

        {/* 分析类型选择 */}
        <Form.Item label="分析类型">
          <Radio.Group
            value={store.analysisType}
            onChange={(e) => store.setAnalysisType(e.target.value)}
            optionType="button"
            buttonStyle="solid"
            size="small"
            style={{ width: '100%', display: 'flex' }}
          >
            <Radio.Button value="ic" style={{ flex: 1, textAlign: 'center' }}>IC 分析</Radio.Button>
            <Radio.Button value="quantile" style={{ flex: 1, textAlign: 'center' }}>分位数组合</Radio.Button>
            <Radio.Button value="turnover" style={{ flex: 1, textAlign: 'center' }}>换手率</Radio.Button>
            <Radio.Button value="strategy" style={{ flex: 1, textAlign: 'center' }}>策略回测</Radio.Button>
          </Radio.Group>
        </Form.Item>

        {/* IC 分析参数 */}
        {store.analysisType === 'ic' && (
          <>
            <Form.Item label="IC 方法" name="corr_method" initialValue="spearman">
              <Select options={[
                { label: 'Spearman (秩相关)', value: 'spearman' },
                { label: 'Pearson (线性相关)', value: 'pearson' },
              ]} />
            </Form.Item>
          </>
        )}

        {/* 分位数组合参数 */}
        {store.analysisType === 'quantile' && (
          <>
            <Form.Item label="分组数" name="n_groups" initialValue={5}>
              <InputNumber min={2} max={20} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item label="再平衡频率" name="rebalance_freq" initialValue="monthly">
              <Select options={[
                { label: '日频', value: 'daily' },
                { label: '周频', value: 'weekly' },
                { label: '月频', value: 'monthly' },
              ]} />
            </Form.Item>
          </>
        )}

        {/* 换手率参数 */}
        {store.analysisType === 'turnover' && (
          <>
            <Form.Item label="选股比例" name="top_pct" initialValue={0.2}>
              <InputNumber min={0.01} max={0.5} step={0.05} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item label="再平衡频率" name="rebalance_freq" initialValue="monthly">
              <Select options={[
                { label: '日频', value: 'daily' },
                { label: '周频', value: 'weekly' },
                { label: '月频', value: 'monthly' },
              ]} />
            </Form.Item>
          </>
        )}

        {/* 策略回测参数 */}
        {store.analysisType === 'strategy' && (
          <>
            <Form.Item label="初始资金" name="initial_capital" initialValue={1000000}>
              <InputNumber min={10000} step={100000} style={{ width: '100%' }} formatter={(v) => `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')} />
            </Form.Item>
            <Form.Item label="佣金费率" name="commission_rate" initialValue={0.0003}>
              <InputNumber min={0} max={0.01} step={0.0001} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item label="滑点" name="slippage" initialValue={0.001}>
              <InputNumber min={0} max={0.02} step={0.001} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item label="选股数量" name="top_n" initialValue={20}>
              <InputNumber min={1} max={200} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item label="信号方向" name="signal_direction" initialValue="long">
              <Select options={[
                { label: '多头', value: 'long' },
                { label: '空头', value: 'short' },
                { label: '多空', value: 'long_short' },
              ]} />
            </Form.Item>
            <Form.Item label="再平衡频率" name="rebalance_freq" initialValue="monthly">
              <Select options={[
                { label: '日频', value: 'daily' },
                { label: '周频', value: 'weekly' },
                { label: '月频', value: 'monthly' },
              ]} />
            </Form.Item>
          </>
        )}

        {/* 日期范围 */}
        <Form.Item label="起始日期" name="start_date">
          <DatePicker
            style={{ width: '100%' }}
            placeholder="默认全部"
          />
        </Form.Item>
        <Form.Item label="截止日期" name="end_date">
          <DatePicker
            style={{ width: '100%' }}
            placeholder="默认全部"
          />
        </Form.Item>

        {/* 运行按钮 */}
        <Form.Item wrapperCol={{ offset: 6, span: 18 }}>
          <Button
            type="primary"
            icon={<PlayCircleOutlined />}
            loading={loading}
            disabled={!canRun}
            block
            onClick={() => {
              if (!canRun) return
              const values = form.getFieldsValue()
              store.setStrategyParams({
                conn_id: store.connId,
                table_name: store.tableName,
                factor_name: store.factorName,
                ...values,
                start_date: values.start_date ? (values.start_date as dayjs.Dayjs).format('YYYY-MM-DD') : null,
                end_date: values.end_date ? (values.end_date as dayjs.Dayjs).format('YYYY-MM-DD') : null,
              })
              switch (store.analysisType) {
                case 'ic': onRunIC(); break
                case 'quantile': onRunQuantile(); break
                case 'turnover': onRunTurnover(); break
                case 'strategy': onRunStrategy(); break
              }
            }}
          >
            {loading ? '运行中...' : '运行分析'}
          </Button>
        </Form.Item>
      </Form>
    </Card>
  )
}

export default BacktestConfig
