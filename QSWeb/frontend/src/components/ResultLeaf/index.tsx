/**
 * ResultLeaf - 结果叶子节点渲染
 *
 * 根据 ResultNode 的 type 渲染：
 * - series → Plotly 折线图
 * - dataframe → Ant Table
 * - scalar → Statistic 数值
 */

import { useMemo, useEffect, useRef } from 'react'
import { Table, Statistic, Card, Empty } from 'antd'
import Plotly from 'plotly.js-dist-min'
import type { ResultNode } from '../../services/backtest'

interface ResultLeafProps {
  /** 选中的叶子节点（type 非 branch） */
  node: ResultNode | null
}

/** Series 折线图 + 数据表 */
function SeriesView({ data }: { data: any }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const { index = [], values = [] } = data || {}

  useEffect(() => {
    if (!containerRef.current || !index.length) return

    const trace = {
      x: index,
      y: values,
      type: 'scatter' as const,
      mode: 'lines+markers' as const,
      marker: { size: 4 },
    }

    Plotly.newPlot(
      containerRef.current,
      [trace],
      {
        autosize: true,
        margin: { l: 50, r: 20, t: 10, b: 50 },
        xaxis: { title: '时间' },
        yaxis: { title: '值' },
      },
      { responsive: true, displaylogo: false }
    )

    return () => {
      if (containerRef.current) {
        Plotly.purge(containerRef.current)
      }
    }
  }, [index, values])

  if (!index.length) return <Empty description="无数据" />

  const tableData = useMemo(() => {
    return index.map((idx: string, i: number) => {
      const val = values[i]
      const displayVal = typeof val === 'number' ? Number(val.toFixed(6)) : val
      return { _key: i, index: idx, value: displayVal }
    })
  }, [index, values])

  const tableColumns = [
    { title: '#', dataIndex: 'index', key: 'index', width: 130, ellipsis: true },
    { title: '值', dataIndex: 'value', key: 'value', ellipsis: true },
  ]

  return (
    <div>
      <div ref={containerRef} style={{ width: '100%', height: 400 }} />
      <Table
        size="small"
        columns={tableColumns}
        dataSource={tableData}
        rowKey="_key"
        scroll={{ y: 300 }}
        pagination={{ pageSize: 50, size: 'small', showSizeChanger: false }}
        style={{ marginTop: 12 }}
      />
    </div>
  )
}

/** DataFrame 表格 */
function DataFrameView({ data }: { data: any }) {
  const { columns = [], index: idx = [], data: rows = [] } = data || {}

  const tableData = useMemo(() => {
    return rows.map((row: any[], i: number) => {
      const record: Record<string, any> = { _key: i, _idx: idx[i] ?? i }
      columns.forEach((col: string, j: number) => {
        const val = row[j]
        if (typeof val === 'number') {
          record[col] = Number(val.toFixed(6))
        } else {
          record[col] = val
        }
      })
      return record
    })
  }, [columns, idx, rows])

  const tableColumns = useMemo(() => {
    const indexCol = {
      title: '#',
      dataIndex: '_idx',
      key: '_idx',
      width: 130,
      ellipsis: true,
      fixed: 'left' as const,
    }
    const dataCols = columns.map((col: string) => ({
      title: col,
      dataIndex: col,
      key: col,
      ellipsis: true,
      width: 150,
    }))
    return [indexCol, ...dataCols]
  }, [columns])

  if (!columns.length) return <Empty description="无数据" />

  return (
    <Table
      size="small"
      columns={tableColumns}
      dataSource={tableData}
      rowKey="_key"
      scroll={{ x: 'max-content', y: 400 }}
      pagination={{ pageSize: 50, size: 'small', showSizeChanger: false }}
    />
  )
}

/** Scalar 统计值 */
function ScalarView({ data, label }: { data: any; label: string }) {
  let displayValue: React.ReactNode = '-'

  if (typeof data === 'number') {
    displayValue = Number.isInteger(data) ? data : data.toFixed(4)
  } else if (typeof data === 'string') {
    displayValue = data
  } else if (data === null || data === undefined) {
    displayValue = 'N/A'
  } else {
    displayValue = String(data)
  }

  return (
    <Card size="small">
      <Statistic title={label} value={String(displayValue)} />
    </Card>
  )
}

function ResultLeaf({ node }: ResultLeafProps) {
  if (!node) {
    return (
      <div style={{ textAlign: 'center', padding: 32, color: '#ccc' }}>
        请从左侧结果树中选择一个节点查看详情
      </div>
    )
  }

  switch (node.type) {
    case 'series':
      return <SeriesView data={node.data} />
    case 'dataframe':
      return <DataFrameView data={node.data} />
    case 'scalar':
      return <ScalarView data={node.data} label={node.label} />
    default:
      return <Empty description={`暂不支持类型: ${node.type}`} />
  }
}

export default ResultLeaf
