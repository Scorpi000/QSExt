/**
 * ResultView - 优化结果展示组件
 *
 * 状态卡片 + 权重分布图 (Plotly) + 风险分解图 (Plotly) + 导出按钮。
 */

import { useRef, useEffect } from 'react'
import { Row, Col, Card, Statistic, Typography, Empty, Spin, Button } from 'antd'
import Plotly from 'plotly.js-dist-min'
import type { OptimizeResponse } from '../../services/portfolio'

const { Text } = Typography

const STATUS_MAP: Record<string, { color: string; label: string }> = {
  optimal: { color: 'green', label: '最优解' },
  infeasible: { color: 'red', label: '无可行解' },
  unbounded: { color: 'orange', label: '无界' },
  error: { color: 'red', label: '求解错误' },
}

function WeightChart({ result }: { result: OptimizeResponse }) {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!containerRef.current || !result.weights.length) return
    const nonZero = result.asset_ids
      .map((id, i) => ({ id, weight: result.weights[i] }))
      .filter((d) => Math.abs(d.weight) > 1e-6)
      .sort((a, b) => Math.abs(b.weight) - Math.abs(a.weight))
      .slice(0, 30)
    const colors = nonZero.map((d) => (d.weight >= 0 ? '#52c41a' : '#ff4d4f'))
    const trace: Plotly.Data = {
      type: 'bar', x: nonZero.map((d) => d.id), y: nonZero.map((d) => d.weight),
      marker: { color: colors },
      text: nonZero.map((d) => (d.weight * 100).toFixed(2) + '%'), textposition: 'outside',
      hovertemplate: '%{x}: %{y:.4f}<extra></extra>',
    }
    Plotly.newPlot(containerRef.current, [trace], {
      title: '最优权重分布 (Top 30)', height: 400,
      margin: { l: 60, r: 20, t: 40, b: 80 },
      xaxis: { tickangle: 45, tickfont: { size: 10 } },
      yaxis: { title: '权重', tickformat: '.2%' },
      paper_bgcolor: 'transparent', plot_bgcolor: 'transparent',
    }, { responsive: true, displayModeBar: false, displaylogo: false })
    return () => { if (containerRef.current) Plotly.purge(containerRef.current) }
  }, [result])

  return <div ref={containerRef} style={{ width: '100%' }} />
}

function RiskDecompChart({ result }: { result: OptimizeResponse }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const decomp = result.risk_decomposition

  useEffect(() => {
    if (!containerRef.current || !decomp?.risk_contributions.length) return
    const top10 = decomp.risk_contributions.slice(0, 10)
    const others = decomp.risk_contributions.slice(10)
    const othersPct = others.reduce((s, c) => s + c.pct, 0)
    const labels = top10.map((c) => c.asset)
    const values = top10.map((c) => c.pct)
    if (othersPct > 0.01) { labels.push('其他'); values.push(othersPct) }
    const trace: Plotly.Data = {
      type: 'pie', labels, values, hole: 0.4,
      textinfo: 'label+percent', textposition: 'outside',
      hovertemplate: '%{label}: %{value:.1f}%<extra></extra>',
    }
    Plotly.newPlot(containerRef.current, [trace], {
      title: `风险分解（组合波动率: ${(decomp.portfolio_volatility * 100).toFixed(2)}%）`,
      height: 400, margin: { l: 20, r: 20, t: 50, b: 20 },
      paper_bgcolor: 'transparent', plot_bgcolor: 'transparent',
    }, { responsive: true, displayModeBar: false, displaylogo: false })
    return () => { if (containerRef.current) Plotly.purge(containerRef.current) }
  }, [result])

  return <div ref={containerRef} style={{ width: '100%' }} />
}

interface ResultViewProps {
  result: OptimizeResponse | null
  solving: boolean
}

function ResultView({ result, solving }: ResultViewProps) {
  const statusInfo = result ? STATUS_MAP[result.status] || STATUS_MAP.error : null

  if (!result && !solving) {
    return (
      <Empty
        description="配置协方差矩阵（风险库或手动输入）和约束条件后，点击「求解」开始优化"
        style={{ marginTop: 60 }}
      />
    )
  }

  if (solving) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 300 }}>
        <Spin size="large" tip="正在求解优化问题..." />
      </div>
    )
  }

  if (!result) return null

  return (
    <>
      {/* 状态卡片 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card size="small">
            <Statistic title="状态" value={statusInfo?.label || result.status}
              valueStyle={{ color: statusInfo?.color === 'green' ? '#52c41a' : '#ff4d4f' }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small"><Statistic title="求解器" value={result.solver_name || '-'} /></Card>
        </Col>
        <Col span={6}>
          <Card size="small"><Statistic title="耗时" value={`${result.solve_time?.toFixed(3) || '?'}s`} /></Card>
        </Col>
        <Col span={6}>
          <Card size="small"><Statistic title="持仓数" value={result.weights.filter((w) => Math.abs(w) > 1e-6).length} /></Card>
        </Col>
      </Row>

      {result.message && (
        <Text type="secondary" style={{ display: 'block', marginBottom: 16 }}>求解信息: {result.message}</Text>
      )}

      {result.status === 'optimal' && result.weights.length > 0 && (
        <Row gutter={16}>
          <Col span={12}><WeightChart result={result} /></Col>
          <Col span={12}>
            {result.risk_decomposition ? <RiskDecompChart result={result} /> : <Empty description="无风险分解数据" />}
          </Col>
        </Row>
      )}

      {result.status !== 'optimal' && (
        <Empty description={`无最优解: ${result.message || '请检查约束条件是否过于严格'}`} style={{ marginTop: 40 }} />
      )}
    </>
  )
}

export default ResultView
