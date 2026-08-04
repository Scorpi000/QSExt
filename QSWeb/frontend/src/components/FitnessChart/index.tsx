/**
 * FitnessChart - 适应度进化曲线（Plotly）
 */

import { useEffect, useRef } from 'react'
import Plotly from 'plotly.js-dist-min'

interface FitnessChartProps {
  data: {
    gen_best: number[]
    gen_avg: number[]
  }
}

function FitnessChart({ data }: FitnessChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mountedRef = useRef(false)

  useEffect(() => {
    if (!containerRef.current) return
    const { gen_best, gen_avg } = data
    if (!gen_best || gen_best.length === 0) return

    const generations = gen_best.map((_, i) => i + 1)

    const traces: Plotly.Data[] = [
      {
        x: generations,
        y: gen_best,
        type: 'scatter',
        mode: 'lines+markers',
        name: '最佳适应度',
        line: { color: '#1677ff', width: 2 },
        marker: { size: 4 },
      },
      {
        x: generations,
        y: gen_avg,
        type: 'scatter',
        mode: 'lines',
        name: '平均适应度',
        line: { color: '#91caff', width: 1.5, dash: 'dot' },
      },
    ]

    const layout: Partial<Plotly.Layout> = {
      autosize: true,
      height: 300,
      margin: { l: 60, r: 20, t: 10, b: 40 },
      xaxis: { title: '代数', dtick: Math.max(1, Math.floor(gen_best.length / 10)) },
      yaxis: { title: '适应度', tickformat: '.4f' },
      paper_bgcolor: '#fafafa',
      plot_bgcolor: '#fafafa',
      showlegend: true,
      legend: { x: 0.02, y: 0.98, xanchor: 'left', yanchor: 'top', bgcolor: '#ffffffaa' },
    }

    if (mountedRef.current) {
      // 增量更新，避免闪烁
      Plotly.react(containerRef.current, traces, layout, {
        responsive: true,
        displayModeBar: false,
      })
    } else {
      Plotly.newPlot(containerRef.current, traces, layout, {
        responsive: true,
        displayModeBar: false,
      })
      mountedRef.current = true
    }

    return () => {
      if (containerRef.current) {
        Plotly.purge(containerRef.current)
        mountedRef.current = false
      }
    }
  }, [data])

  return <div ref={containerRef} style={{ width: '100%', minHeight: 300 }} />
}

export default FitnessChart
