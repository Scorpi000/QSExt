declare module 'plotly.js-dist-min' {
  import Plotly from 'plotly.js'
  export = Plotly
}

declare namespace Plotly {
  interface Data {
    x?: (string | number | null)[]
    y?: (string | number | null)[]
    type?: 'scatter' | 'bar' | 'pie' | 'heatmap' | 'contour' | 'surface' | 'mesh3d'
    mode?: 'lines' | 'markers' | 'text' | 'lines+markers' | 'lines+text' | 'markers+text' | 'lines+markers+text'
    name?: string
    fill?: 'none' | 'tozeroy' | 'tozerox' | 'tonexty' | 'tonextx' | 'toself' | 'tonext'
    marker?: {
      color?: string | string[]
      size?: number
      line?: { color?: string; width?: number }
    }
    line?: {
      color?: string
      width?: number
      dash?: 'solid' | 'dot' | 'dash' | 'longdash' | 'dashdot' | 'longdashdot'
    }
    fillcolor?: string
    orientation?: 'v' | 'h'
    text?: string[]
    hoverinfo?: string
  }

  interface Layout {
    title?: string | { text: string; font?: { size?: number } }
    font?: { family?: string; size?: number }
    paper_bgcolor?: string
    plot_bgcolor?: string
    margin?: { l?: number; r?: number; t?: number; b?: number }
    hovermode?: 'x' | 'y' | 'closest' | 'x unified' | 'y unified'
    legend?: {
      orientation?: 'h' | 'v'
      y?: number
      x?: number
    }
    xaxis?: { title?: string; type?: string }
    yaxis?: { title?: string; type?: string }
    showlegend?: boolean
    [key: string]: unknown
  }

  interface Config {
    responsive?: boolean
    displayModeBar?: boolean
    modeBarButtonsToRemove?: string[]
    displaylogo?: boolean
    [key: string]: unknown
  }

  function newPlot(
    graphDiv: HTMLElement,
    data: Data[],
    layout?: Partial<Layout>,
    config?: Partial<Config>
  ): Promise<void>

  function purge(graphDiv: HTMLElement): void
}
