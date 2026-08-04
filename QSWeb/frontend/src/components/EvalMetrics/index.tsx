/**
 * EvalMetrics — 因子评测指标对比表格
 *
 * 表格展示所有因子的评测指标，每列可排序，
 * 指标值用颜色渐变（绿=好、红=差），运行中每 5s 轮询更新。
 */

import { useState, useEffect, useRef, useCallback } from 'react'
import { Table, Tag, Empty } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { getEvalMetrics, type EvalFactorMetrics, type EvalMetricsResponse } from '../../services/mining'

interface EvalMetricsProps {
  taskId: string
  runId: string
  isRunning: boolean
}

// 指标列定义
const METRIC_COLUMNS: { key: string; title: string; goodDirection: 'higher' | 'lower' }[] = [
  { key: 'ic_mean', title: 'IC Mean', goodDirection: 'higher' },
  { key: 'ic_ir', title: 'IC IR', goodDirection: 'higher' },
  { key: 'rank_ic', title: 'Rank IC', goodDirection: 'higher' },
  { key: 'sharpe', title: 'Sharpe', goodDirection: 'higher' },
  { key: 'max_drawdown', title: '最大回撤', goodDirection: 'lower' },
]

// 颜色渐变：值域 → 颜色
function metricColor(value: number | null | undefined, direction: 'higher' | 'lower'): string {
  if (value == null || isNaN(value)) return '#d9d9d9'

  if (direction === 'higher') {
    // > 0: 绿色系；负值: 红色系
    if (value > 0.05) return '#237804'
    if (value > 0.02) return '#52c41a'
    if (value > 0) return '#b7eb8f'
    if (value > -0.02) return '#ffccc7'
    return '#cf1322'
  } else {
    // max_drawdown: 越低越好（负值的高于正值）
    if (value > -0.05) return '#cf1322'
    if (value > -0.10) return '#ffccc7'
    if (value > -0.15) return '#b7eb8f'
    if (value > -0.25) return '#52c41a'
    return '#237804'
  }
}

interface FactorRow {
  key: string
  name: string
  status: string
  [metric: string]: any
}

function EvalMetrics({ taskId, runId, isRunning }: EvalMetricsProps) {
  const [factors, setFactors] = useState<FactorRow[]>([])
  const [updatedAt, setUpdatedAt] = useState<string | null>(null)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchMetrics = useCallback(async () => {
    try {
      const data = (await getEvalMetrics(taskId, runId)) as unknown as EvalMetricsResponse
      const rows: FactorRow[] = (data.factors || []).map((f, i) => ({
        key: f.name,
        name: f.name,
        status: f.status,
        ic_mean: f.metrics?.ic_mean ?? null,
        ic_ir: f.metrics?.ic_ir ?? null,
        rank_ic: f.metrics?.rank_ic ?? null,
        sharpe: f.metrics?.sharpe ?? null,
        max_drawdown: f.metrics?.max_drawdown ?? null,
      }))
      setFactors(rows)
      setUpdatedAt(data.updated_at)
    } catch {
      // 静默
    }
  }, [taskId, runId])

  useEffect(() => {
    fetchMetrics()
  }, [taskId, runId])

  // 轮询：运行中每 5s
  useEffect(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
    if (isRunning) {
      timerRef.current = setInterval(fetchMetrics, 5000)
    }
    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current)
        timerRef.current = null
      }
    }
  }, [isRunning, fetchMetrics])

  const columns: ColumnsType<FactorRow> = [
    {
      title: '排名',
      key: 'rank',
      width: 60,
      render: (_: any, __: FactorRow, idx: number) => idx + 1,
      sorter: (a, b) => {
        const aScore = (a.ic_ir ?? 0) + (a.ic_mean ?? 0) * 10
        const bScore = (b.ic_ir ?? 0) + (b.ic_mean ?? 0) * 10
        return bScore - aScore
      },
      defaultSortOrder: 'ascend',
    },
    { title: '因子名称', dataIndex: 'name', key: 'name', width: 160 },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 90,
      render: (v: string) => {
        const color = v === 'validated' ? 'success' : v === 'failed' ? 'error' : 'default'
        const label = v === 'validated' ? '已验证' : v === 'failed' ? '失败' : v
        return <Tag color={color}>{label}</Tag>
      },
    },
    ...METRIC_COLUMNS.map((col) => ({
      title: col.title,
      dataIndex: col.key,
      key: col.key,
      width: 90,
      sorter: (a: FactorRow, b: FactorRow) => (a[col.key] ?? -Infinity) - (b[col.key] ?? -Infinity),
      render: (v: number | null) => (
        <span style={{ color: metricColor(v, col.goodDirection), fontWeight: 500 }}>
          {v != null ? v.toFixed(4) : '-'}
        </span>
      ),
    })),
  ]

  return (
    <div>
      {updatedAt && (
        <div style={{ marginBottom: 8, fontSize: 12, color: '#999' }}>
          更新时间: {new Date(updatedAt).toLocaleString()}
        </div>
      )}
      <Table
        columns={columns}
        dataSource={factors}
        size="small"
        pagination={false}
        scroll={{ x: 700 }}
        locale={{ emptyText: <Empty description="暂无评测数据" image={Empty.PRESENTED_IMAGE_SIMPLE} /> }}
      />
    </div>
  )
}

export default EvalMetrics
