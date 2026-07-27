/**
 * 通用 Plotly 图表组件
 *
 * 封装 Plotly.js 用于金融分析图表（净值曲线、IC 图表等）。
 */

import { useEffect, useRef } from 'react'
import Plotly from 'plotly.js-dist-min'

interface PlotlyChartProps {
  data: Plotly.Data[]
  layout?: Partial<Plotly.Layout>
  config?: Partial<Plotly.Config>
  style?: React.CSSProperties
  className?: string
  /** 是否使用响应式宽度 */
  responsive?: boolean
}

const defaultLayout: Partial<Plotly.Layout> = {
  font: { family: 'Arial, sans-serif' },
  paper_bgcolor: 'transparent',
  plot_bgcolor: 'transparent',
  margin: { l: 60, r: 20, t: 40, b: 50 },
  hovermode: 'x unified' as Plotly.Layout['hovermode'],
  legend: { orientation: 'h' as const, y: 1.12 },
}

const defaultConfig: Partial<Plotly.Config> = {
  responsive: true,
  displayModeBar: true,
  modeBarButtonsToRemove: ['lasso2d', 'select2d', 'sendDataToCloud'],
  displaylogo: false,
}

function PlotlyChart({
  data,
  layout = {},
  config = {},
  style = { width: '100%', height: 400 },
  className,
}: PlotlyChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!containerRef.current) return

    const mergedLayout = { ...defaultLayout, ...layout }
    const mergedConfig = { ...defaultConfig, ...config }

    Plotly.newPlot(containerRef.current, data, mergedLayout, mergedConfig)

    return () => {
      if (containerRef.current) {
        Plotly.purge(containerRef.current)
      }
    }
  }, [data, layout, config])

  return <div ref={containerRef} style={style} className={className} />
}

export default PlotlyChart
