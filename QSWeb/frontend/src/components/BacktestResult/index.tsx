/**
 * 策略回测结果展示
 */

import { Card, Row, Col, Statistic, Table, Empty, Tag } from 'antd'
import {
  ArrowUpOutlined,
  ArrowDownOutlined,
} from '@ant-design/icons'
import PlotlyChart from '../PlotlyChart'
import type { BacktestResultData } from '../../services/backtest'

interface Props {
  result: BacktestResultData
}

function BacktestResult({ result }: Props) {
  const { summary, nav_series, trades } = result

  if (!nav_series?.length) {
    return <Empty description="暂无回测结果" />
  }

  // 净值曲线
  const navData: Plotly.Data[] = [
    {
      x: nav_series.map((d) => d.date),
      y: nav_series.map((d) => d.nav),
      type: 'scatter' as const,
      mode: 'lines' as const,
      name: '净值',
      fill: 'tozeroy' as const,
      line: { color: '#1890ff', width: 2 },
      fillcolor: 'rgba(24,144,255,0.1)',
    },
  ]

  // 统计指标
  const isPositive = summary.total_return >= 0

  const tradeColumns = [
    { title: '日期', dataIndex: 'date', key: 'date', width: 110 },
    { title: '代码', dataIndex: 'code', key: 'code', width: 90 },
    {
      title: '方向',
      dataIndex: 'action',
      key: 'action',
      width: 70,
      render: (a: string) => (
        <Tag color={a === 'buy' ? 'green' : 'red'}>{a === 'buy' ? '买入' : '卖出'}</Tag>
      ),
    },
    { title: '数量', dataIndex: 'shares', key: 'shares', width: 80, align: 'right' as const },
    { title: '价格', dataIndex: 'price', key: 'price', width: 80, align: 'right' as const },
  ]

  return (
    <div>
      {/* 关键指标 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={4}>
          <Card size="small">
            <Statistic
              title="总收益"
              value={summary.total_return}
              precision={2}
              suffix="%"
              valueStyle={{ color: isPositive ? '#3f8600' : '#cf1322' }}
              prefix={isPositive ? <ArrowUpOutlined /> : <ArrowDownOutlined />}
            />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic title="年化收益" value={summary.annual_return} precision={2} suffix="%" />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic title="年化波动" value={summary.annual_volatility} precision={2} suffix="%" />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic title="最大回撤" value={summary.max_drawdown} precision={2} suffix="%" />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic title="夏普比率" value={summary.sharpe_ratio} precision={2} />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic title="胜率" value={summary.win_rate} precision={1} suffix="%" />
          </Card>
        </Col>
      </Row>

      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={4}>
          <Card size="small">
            <Statistic title="信息比率" value={summary.info_ratio} precision={2} />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic title="交易次数" value={summary.n_trades} />
          </Card>
        </Col>
      </Row>

      {/* 净值曲线 */}
      <Card title="净值曲线" size="small" style={{ marginBottom: 16 }}>
        <PlotlyChart
          data={navData}
          layout={{ yaxis: { title: '净值' } }}
          style={{ height: 400 }}
        />
      </Card>

      {/* 交易记录 */}
      {trades.length > 0 && (
        <Card title={`交易记录 (${trades.length} 条)`} size="small">
          <Table
            columns={tradeColumns}
            dataSource={trades.slice(0, 100).map((t, i) => ({ ...t, key: i }))}
            pagination={trades.length > 100 ? { pageSize: 50 } : false}
            size="small"
            scroll={{ y: 400 }}
          />
        </Card>
      )}
    </div>
  )
}

export default BacktestResult
