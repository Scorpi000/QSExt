/**
 * IC 分析结果展示组件
 */

import { Card, Statistic, Row, Col, Empty, Table } from 'antd'
import PlotlyChart from '../PlotlyChart'
import type { ICAnalysisResult } from '../../services/backtest'

interface Props {
  result: ICAnalysisResult
}

function ICAnalysisChart({ result }: Props) {
  if (!result.ic_series?.length) {
    return <Empty description="暂无 IC 数据" />
  }

  const { summary, ic_series, ic_decay, corr_method } = result

  // IC 时间序列图
  const icLineData: Plotly.Data[] = [
    {
      x: ic_series.map((s) => s.date),
      y: ic_series.map((s) => s.ic),
      type: 'bar' as const,
      name: `${corr_method.toUpperCase()} IC`,
      marker: {
        color: ic_series.map((s) => (s.ic >= 0 ? '#52c41a' : '#ff4d4f')),
      },
    },
    {
      x: ic_series.map((s) => s.date),
      y: Array(ic_series.length).fill(summary.mean_ic),
      type: 'scatter' as const,
      mode: 'lines' as const,
      name: `均值 IC (${summary.mean_ic.toFixed(4)})`,
      line: { dash: 'dash', color: '#1890ff', width: 2 },
    },
  ]

  // IC 衰减图
  const icDecayData: Plotly.Data[] | null = ic_decay?.length
    ? [
        {
          x: ic_decay.map((d) => `Lag ${d.lag}`),
          y: ic_decay.map((d) => d.autocorr),
          type: 'scatter' as const,
          mode: 'lines+markers' as const,
          name: 'IC 自相关',
          marker: { size: 8 },
          line: { color: '#722ed1' },
        },
      ]
    : null

  const statsColumns = [
    { title: '指标', dataIndex: 'label', key: 'label' },
    { title: '值', dataIndex: 'value', key: 'value' },
  ]
  const statsData = [
    { label: '均值 IC', value: summary.mean_ic.toFixed(4) },
    { label: '标准差 IC', value: summary.std_ic.toFixed(4) },
    { label: 'ICIR', value: summary.ir.toFixed(4) },
    { label: '胜率', value: `${(summary.positive_ratio * 100).toFixed(1)}%` },
    { label: '周期数', value: summary.n_periods },
    { label: '最大 IC', value: summary.max_ic?.toFixed(4) || '-' },
    { label: '最小 IC', value: summary.min_ic?.toFixed(4) || '-' },
  ]

  return (
    <div>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card size="small"><Statistic title="均值 IC" value={summary.mean_ic.toFixed(4)} precision={4} /></Card>
        </Col>
        <Col span={6}>
          <Card size="small"><Statistic title="ICIR" value={summary.ir.toFixed(4)} precision={4} /></Card>
        </Col>
        <Col span={6}>
          <Card size="small"><Statistic title="胜率" value={`${(summary.positive_ratio * 100).toFixed(1)}%`} /></Card>
        </Col>
        <Col span={6}>
          <Card size="small"><Statistic title="周期数" value={summary.n_periods} /></Card>
        </Col>
      </Row>

      <Card title={`${corr_method.toUpperCase()} IC 时间序列`} size="small" style={{ marginBottom: 16 }}>
        <PlotlyChart data={icLineData} style={{ height: 350 }} />
      </Card>

      {icDecayData && (
        <Card title="IC 衰减曲线" size="small" style={{ marginBottom: 16 }}>
          <PlotlyChart data={icDecayData} style={{ height: 350 }} />
        </Card>
      )}

      <Card title="统计指标" size="small">
        <Table columns={statsColumns} dataSource={statsData} pagination={false} size="small" rowKey="label" />
      </Card>
    </div>
  )
}

export default ICAnalysisChart
