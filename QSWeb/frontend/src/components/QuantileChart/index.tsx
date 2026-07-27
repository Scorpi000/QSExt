/**
 * 分位数组合结果展示
 */

import { Card, Empty, Table } from 'antd'
import PlotlyChart from '../PlotlyChart'
import type { QuantilePortfolioResult } from '../../services/backtest'

interface Props {
  result: QuantilePortfolioResult
}

const COLORS = ['#ff4d4f', '#fa8c16', '#fadb14', '#52c41a', '#1890ff', '#722ed1']

function QuantileChart({ result }: Props) {
  if (!result.nav_series?.length) {
    return <Empty description="暂无分位数组合数据" />
  }

  // 净值曲线
  const navData: Plotly.Data[] = result.nav_series.map((g, i) => ({
    x: g.data.map((d) => d.date),
    y: g.data.map((d) => d.nav),
    type: 'scatter' as const,
    mode: 'lines' as const,
    name: g.label,
    line: { color: COLORS[i % COLORS.length], width: 2 },
  }))

  // 多空净值
  let lsData: Plotly.Data[] = []
  if (result.long_short_nav?.length) {
    lsData = [
      {
        x: result.long_short_nav.map((d) => d.date),
        y: result.long_short_nav.map((d) => d.nav),
        type: 'scatter' as const,
        mode: 'lines' as const,
        name: '多空组合',
        fill: 'tozeroy' as const,
        line: { color: '#722ed1', width: 2 },
      },
    ]
  }

  const summaryColumns = [
    { title: '分组', dataIndex: 'group', key: 'group' },
    { title: '总收益 (%)', dataIndex: 'total_return', key: 'total_return' },
    { title: '年化收益 (%)', dataIndex: 'annual_return', key: 'annual_return' },
  ]

  const summaryData = Object.entries(result.summary).map(([group, vals]) => ({
    group: group.replace('Q', '分位数 '),
    total_return: vals.total_return,
    annual_return: vals.annual_return,
  }))

  return (
    <div>
      <Card title="分位数组合净值曲线" size="small" style={{ marginBottom: 16 }}>
        <PlotlyChart
          data={navData}
          layout={{
            yaxis: { title: '净值' },
            legend: { y: 1.12 },
          }}
          style={{ height: 400 }}
        />
      </Card>

      {lsData.length > 0 && (
        <Card title="多空净值曲线" size="small" style={{ marginBottom: 16 }}>
          <PlotlyChart
            data={lsData}
            layout={{ yaxis: { title: '多空净值' } }}
            style={{ height: 350 }}
          />
        </Card>
      )}

      <Card title="分组统计" size="small">
        <Table columns={summaryColumns} dataSource={summaryData} pagination={false} size="small" rowKey="group" />
      </Card>
    </div>
  )
}

export default QuantileChart
