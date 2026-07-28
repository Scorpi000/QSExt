/**
 * RiskHeatmap - 协方差/相关系数矩阵热力图
 *
 * 使用 Plotly heatmap 渲染，支持协方差矩阵和相关系数矩阵切换。
 */

import { useMemo, useEffect, useRef } from 'react'
import Plotly from 'plotly.js-dist-min'
import { Spin, Empty } from 'antd'
import type { MatrixData } from '../../services/risk'

interface RiskHeatmapProps {
  data: MatrixData | null
  loading: boolean
  title: string
  colorscale?: 'RdBu' | 'Viridis'
}

function RiskHeatmap({ data, loading, title, colorscale = 'RdBu' }: RiskHeatmapProps) {
  const containerRef = useRef<HTMLDivElement>(null)

  const plotData = useMemo(() => {
    if (!data || data.ids.length === 0) return null

    const n = data.ids.length
    // 构建稠密矩阵
    const z: number[][] = Array.from({ length: n }, () => Array(n).fill(NaN))
    for (const [row, col, val] of data.data) {
      z[row][col] = val
    }

    return [
      {
        type: 'heatmap' as const,
        z,
        x: data.ids,
        y: data.ids,
        colorscale,
        showscale: true,
        hovertemplate: 'Row: %{y}<br>Col: %{x}<br>值: %{z:.6f}<extra></extra>',
      },
    ]
  }, [data, colorscale])

  useEffect(() => {
    if (!containerRef.current || !plotData) return

    Plotly.newPlot(
      containerRef.current,
      plotData,
      {
        title,
        height: Math.max(500, (data?.ids.length || 0) * 22 + 100),
        margin: { l: 100, r: 50, t: 50, b: 100 },
        xaxis: { tickfont: { size: 8 }, tickangle: 45 },
        yaxis: { tickfont: { size: 8 }, autorange: 'reversed' as const },
        paper_bgcolor: 'transparent',
        plot_bgcolor: 'transparent',
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
  }, [plotData, title, data?.ids.length])

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 400 }}>
        <Spin size="large" />
      </div>
    )
  }

  if (!data || data.ids.length === 0) {
    return <Empty description="暂无数据" />
  }

  return <div ref={containerRef} style={{ width: '100%' }} />
}

export default RiskHeatmap
