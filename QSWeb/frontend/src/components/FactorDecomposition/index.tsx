/**
 * FactorDecomposition - 因子风险分解组件
 *
 * 展示因子协方差矩阵（热力图）+ 因子相关系数矩阵（热力图）+ 因子风险贡献（柱状图）
 */

import { useMemo, useEffect, useRef } from 'react'
import Plotly from 'plotly.js-dist-min'
import { Spin, Empty, Tabs } from 'antd'
import RiskHeatmap from '../RiskHeatmap'
import type { FactorDecompositionData, MatrixData } from '../../services/risk'

interface FactorDecompositionProps {
  data: FactorDecompositionData | null
  loading: boolean
}

/** 从协方差矩阵计算相关系数矩阵 */
function calcCorrelation(factorCov: MatrixData): MatrixData {
  const n = factorCov.ids.length
  // 提取对角线（方差）
  const diag = Array(n).fill(0)
  for (const [row, col, val] of factorCov.data) {
    if (row === col) diag[row] = val
  }
  // std = sqrt(方差)
  const std = diag.map((v) => (v > 0 ? Math.sqrt(v) : NaN))
  // corr[i][j] = cov[i][j] / (std[i] * std[j])
  const corrData: [number, number, number][] = []
  for (const [row, col, val] of factorCov.data) {
    const denom = std[row] * std[col]
    if (!isNaN(denom) && denom !== 0) {
      corrData.push([row, col, val / denom])
    }
  }
  return { dt: factorCov.dt, ids: factorCov.ids, data: corrData }
}

function FactorBarChart({ data }: { data: FactorDecompositionData | null }) {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!containerRef.current || !data?.factor_cov) return

    const n = data.factors.length
    const diag: number[] = Array(n).fill(0)
    for (const [row, col, val] of data.factor_cov.data) {
      if (row === col) diag[row] = val
    }

    Plotly.newPlot(
      containerRef.current,
      [
        {
          type: 'bar' as const,
          x: data.factors,
          y: diag,
          marker: { color: '#5470c6' },
          hovertemplate: '因子: %{x}<br>风险贡献: %{y:.6f}<extra></extra>',
        },
      ],
      {
        title: '因子风险贡献（协方差对角线）',
        height: 400,
        margin: { l: 80, r: 20, t: 50, b: 100 },
        xaxis: { tickfont: { size: 9 }, tickangle: 45 },
        yaxis: { title: '方差' },
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
  }, [data])

  return <div ref={containerRef} style={{ width: '100%' }} />
}

function FactorDecomposition({ data, loading }: FactorDecompositionProps) {
  const factorCovData = useMemo(() => {
    if (!data?.factor_cov) return null
    return data.factor_cov
  }, [data])

  const factorCorrData = useMemo(() => {
    if (!factorCovData) return null
    return calcCorrelation(factorCovData)
  }, [factorCovData])

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 400 }}>
        <Spin size="large" />
      </div>
    )
  }

  if (!data) {
    return <Empty description="暂无数据" />
  }

  const tabItems = [
    {
      key: 'factor-cov',
      label: '因子协方差矩阵',
      children: (
        <RiskHeatmap
          data={factorCovData}
          loading={false}
          title="因子协方差矩阵"
          colorscale="Viridis"
        />
      ),
    },
    {
      key: 'factor-corr',
      label: '因子相关系数矩阵',
      children: (
        <RiskHeatmap
          data={factorCorrData}
          loading={false}
          title="因子相关系数矩阵"
          colorscale="RdBu"
        />
      ),
    },
    {
      key: 'factor-bar',
      label: '因子风险贡献',
      children: <FactorBarChart data={data} />,
    },
  ]

  return <Tabs items={tabItems} />
}

export default FactorDecomposition
