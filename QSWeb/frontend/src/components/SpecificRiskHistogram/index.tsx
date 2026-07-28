/**
 * SpecificRiskHistogram - 特异性风险分布直方图
 *
 * 包含直方图、描述统计卡片和明细表格。
 */

import { useMemo, useEffect, useRef } from 'react'
import Plotly from 'plotly.js-dist-min'
import { Spin, Empty, Table, Card } from 'antd'
import type { FactorDecompositionData } from '../../services/risk'

interface SpecificRiskHistogramProps {
  data: FactorDecompositionData | null
  loading: boolean
}

function SpecificRiskHistogram({ data, loading }: SpecificRiskHistogramProps) {
  const containerRef = useRef<HTMLDivElement>(null)

  const values = useMemo(() => {
    if (!data?.specific_risk) return null
    return data.specific_risk.values.filter(
      (v): v is number => v != null && !isNaN(v)
    )
  }, [data])

  useEffect(() => {
    if (!containerRef.current || !values || values.length === 0) return

    Plotly.newPlot(
      containerRef.current,
      [
        {
          type: 'histogram' as const,
          x: values,
          nbinsx: Math.min(50, Math.max(10, Math.floor(values.length / 20))),
          marker: {
            color: '#91cc75',
            line: { color: '#73c04e', width: 1 },
          },
          hovertemplate: 'σ: %{x}<br>频数: %{y}<extra></extra>',
        },
      ],
      {
        title: '特异性风险分布',
        height: 400,
        margin: { l: 60, r: 20, t: 50, b: 50 },
        xaxis: { title: '特异性风险 (σ)' },
        yaxis: { title: '频数' },
        paper_bgcolor: 'transparent',
        plot_bgcolor: 'transparent',
        bargap: 0.05,
      },
      {
        responsive: true,
        displayModeBar: true,
        modeBarButtonsToRemove: ['lasso2d', 'select2d'],
        displaylogo: false,
      }
    )

    return () => {
      if (containerRef.current) {
        Plotly.purge(containerRef.current)
      }
    }
  }, [values])

  // 描述统计
  const stats = useMemo(() => {
    if (!values || values.length === 0) return null
    const sorted = [...values].sort((a, b) => a - b)
    const n = sorted.length
    const sum = values.reduce((a, b) => a + b, 0)
    const mean = sum / n
    const variance = values.reduce((s, v) => s + (v - mean) ** 2, 0) / n
    const std = Math.sqrt(variance)

    return {
      count: n,
      mean,
      std,
      min: sorted[0],
      max: sorted[n - 1],
      p25: sorted[Math.floor(n * 0.25)],
      p50: sorted[Math.floor(n * 0.5)],
      p75: sorted[Math.floor(n * 0.75)],
    }
  }, [values])

  // 明细表格
  const columns = useMemo(() => [
    {
      title: '证券 ID',
      dataIndex: 'id',
      key: 'id',
      width: 120,
    },
    {
      title: '特异性风险 (σ)',
      dataIndex: 'value',
      key: 'value',
      render: (v: number | null) => v != null ? v.toFixed(6) : '-',
    },
  ], [])

  const tableData = useMemo(() => {
    if (!data?.specific_risk) return []
    return data.specific_risk.ids.map((id, i) => ({
      key: id,
      id,
      value: data.specific_risk.values[i],
    }))
  }, [data])

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 400 }}>
        <Spin size="large" />
      </div>
    )
  }

  if (!values || values.length === 0) {
    return <Empty description="暂无特异性风险数据" />
  }

  return (
    <div>
      <div ref={containerRef} style={{ width: '100%' }} />
      {stats && (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(4, 1fr)',
            gap: 12,
            marginTop: 16,
          }}
        >
          {[
            { label: '样本数', value: stats.count },
            { label: '均值', value: stats.mean.toFixed(6) },
            { label: '标准差', value: stats.std.toFixed(6) },
            { label: '最小值', value: stats.min.toFixed(6) },
            { label: '最大值', value: stats.max.toFixed(6) },
            { label: 'P25', value: stats.p25.toFixed(6) },
            { label: '中位数', value: stats.p50.toFixed(6) },
            { label: 'P75', value: stats.p75.toFixed(6) },
          ].map((s) => (
            <div
              key={s.label}
              style={{
                padding: '8px 12px',
                background: '#fafafa',
                border: '1px solid #f0f0f0',
                borderRadius: 6,
                textAlign: 'center',
              }}
            >
              <div style={{ fontSize: 12, color: '#999' }}>{s.label}</div>
              <div style={{ fontSize: 16, fontWeight: 600 }}>{s.value}</div>
            </div>
          ))}
        </div>
      )}
      <Card size="small" title="特异性风险明细" style={{ marginTop: 16 }}>
        <Table
          columns={columns}
          dataSource={tableData}
          size="small"
          virtual
          scroll={{ y: 400 }}
          pagination={{
            pageSize: 50,
            showSizeChanger: true,
            showTotal: (total) => `共 ${total} 只证券`,
          }}
        />
      </Card>
    </div>
  )
}

export default SpecificRiskHistogram
