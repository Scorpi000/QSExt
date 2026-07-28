/**
 * PortfolioOptimizer - 组合优化页面
 *
 * 左侧：优化配置区（目标 + 约束 + 求解按钮）
 * 右侧：结果展示区（状态信息 + 权重分布图 + 风险分解图 + 导出）
 */

import { useState, useCallback, useEffect, useRef } from 'react'
import {
  Row, Col, Card, Form, Select, InputNumber, Input, Button, Radio,
  List, Modal, message, Empty, Spin, Statistic, Tag, Space, Typography, Divider, Popconfirm,
} from 'antd'
import {
  PlusOutlined, DeleteOutlined,
  PlayCircleOutlined, DownloadOutlined, EditOutlined,
} from '@ant-design/icons'
import Plotly from 'plotly.js-dist-min'
import {
  runOptimization, listSolvers, getDefaultOptimOptions, getWeightsCsvUrl,
  listTasks, getTask, saveTask, deleteTask,
  OBJECTIVE_TYPES, CONSTRAINT_TYPES,
} from '../../services/portfolio'
import type {
  OptimizeRequest, OptimizeResponse, ConstraintDef, SolverInfo, FactorDataRef,
  SavedTaskInfo,
} from '../../services/portfolio'
import { getRiskDatabases, getRiskTables, getTableDates } from '../../services/risk'
import type { RiskDBInfo, RiskTableInfo } from '../../services/risk'
import { getConnections } from '../../services/connection'
import type { Connection } from '../../services/connection'
import { getTables, getFactors, getFactorStats } from '../../services/factor'
import type { FactorTable, FactorInfo } from '../../services/factor'


const { Text } = Typography

// ─── 目标参数表单（动态渲染）─────────────────────────────────

function ObjectiveForm({
  objType, riskAversion, expectedReturnCoef,
  onRiskAversionChange, onExpectedReturnCoefChange,
}: {
  objType: string
  riskAversion: number
  expectedReturnCoef: number
  onRiskAversionChange: (v: number) => void
  onExpectedReturnCoefChange: (v: number) => void
}) {
  if (objType === 'mean_variance') {
    return (
      <>
        <Form.Item label="风险厌恶系数 (λ)" tooltip="越高越保守，越高个股权重越分散">
          <InputNumber
            min={0} step={0.1} value={riskAversion}
            onChange={(v) => onRiskAversionChange(v ?? 1.0)}
            style={{ width: '100%' }}
          />
        </Form.Item>
        <Form.Item label="收益项系数 (α)" tooltip="预期收益的权重，0 表示纯风险最小化">
          <InputNumber
            min={0} step={0.1} value={expectedReturnCoef}
            onChange={(v) => onExpectedReturnCoefChange(v ?? 0.0)}
            style={{ width: '100%' }}
          />
        </Form.Item>
      </>
    )
  }
  if (objType === 'risk_budget') {
    return (
      <Text type="secondary">风险预算将由优化器自动计算（等风险平价）。如需自定义风险预算向量，请使用 API 直接调用。</Text>
    )
  }
  if (objType === 'max_diversification') {
    return <Text type="secondary">最大化分散化比率，无需额外参数。</Text>
  }
  return null
}

// ─── 约束编辑器弹窗 ──────────────────────────────────────────

const CONSTRAINT_DEFAULTS: Record<string, any> = {
  budget: { up_limit: 1.0, down_limit: 1.0 },
  box: { lbs: 0.0, ubs: 0.1 },
  turnover: { up_limit: 0.5, constraint_type: '总换手限制' },
  cardinality: { max_nonzero: 50 },
}

function ConstraintForm({
  cType, values, onChange,
}: {
  cType: string
  values: Record<string, any>
  onChange: (vals: Record<string, any>) => void
}) {
  if (cType === 'budget') {
    return (
      <>
        <Form.Item label="权重下限">
          <InputNumber min={0} max={1} step={0.1} value={values.down_limit}
            onChange={(v) => onChange({ ...values, down_limit: v ?? 1.0 })} style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item label="权重上限">
          <InputNumber min={0} max={1} step={0.1} value={values.up_limit}
            onChange={(v) => onChange({ ...values, up_limit: v ?? 1.0 })} style={{ width: '100%' }} />
        </Form.Item>
      </>
    )
  }
  if (cType === 'box') {
    return (
      <>
        <Form.Item label="个股权重下限">
          <InputNumber min={0} max={1} step={0.01} value={values.lbs}
            onChange={(v) => onChange({ ...values, lbs: v ?? 0.0 })} style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item label="个股权重上限">
          <InputNumber min={0} max={1} step={0.01} value={values.ubs}
            onChange={(v) => onChange({ ...values, ubs: v ?? 0.1 })} style={{ width: '100%' }} />
        </Form.Item>
      </>
    )
  }
  if (cType === 'turnover') {
    return (
      <>
        <Form.Item label="换手率上限">
          <InputNumber min={0} max={1} step={0.05} value={values.up_limit}
            onChange={(v) => onChange({ ...values, up_limit: v ?? 0.5 })} style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item label="约束类型">
          <Select value={values.constraint_type}
            onChange={(v) => onChange({ ...values, constraint_type: v })}
            options={[
              { value: '总换手限制', label: '总换手限制' },
              { value: '总买入限制', label: '总买入限制' },
              { value: '总卖出限制', label: '总卖出限制' },
            ]}
          />
        </Form.Item>
      </>
    )
  }
  if (cType === 'cardinality') {
    return (
      <Form.Item label="最大持仓数">
        <InputNumber min={1} max={500} step={1} value={values.max_nonzero}
          onChange={(v) => onChange({ ...values, max_nonzero: v ?? 50 })} style={{ width: '100%' }} />
      </Form.Item>
    )
  }
  return null
}

// ─── 权重分布图 (Plotly) ────────────────────────────────────

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
      type: 'bar',
      x: nonZero.map((d) => d.id),
      y: nonZero.map((d) => d.weight),
      marker: { color: colors },
      text: nonZero.map((d) => (d.weight * 100).toFixed(2) + '%'),
      textposition: 'outside',
      hovertemplate: '%{x}: %{y:.4f}<extra></extra>',
    }

    Plotly.newPlot(
      containerRef.current,
      [trace],
      {
        title: '最优权重分布 (Top 30)',
        height: 400,
        margin: { l: 60, r: 20, t: 40, b: 80 },
        xaxis: { tickangle: 45, tickfont: { size: 10 } },
        yaxis: { title: '权重', tickformat: '.2%' },
        paper_bgcolor: 'transparent',
        plot_bgcolor: 'transparent',
      },
      { responsive: true, displayModeBar: false, displaylogo: false }
    )

    return () => {
      if (containerRef.current) Plotly.purge(containerRef.current)
    }
  }, [result])

  return <div ref={containerRef} style={{ width: '100%' }} />
}

// ─── 风险分解图 (Plotly) ────────────────────────────────────

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
    if (othersPct > 0.01) {
      labels.push('其他')
      values.push(othersPct)
    }

    const trace: Plotly.Data = {
      type: 'pie',
      labels,
      values,
      hole: 0.4,
      textinfo: 'label+percent',
      textposition: 'outside',
      hovertemplate: '%{label}: %{value:.1f}%<extra></extra>',
    }

    Plotly.newPlot(
      containerRef.current,
      [trace],
      {
        title: `风险分解（组合波动率: ${(decomp.portfolio_volatility * 100).toFixed(2)}%）`,
        height: 400,
        margin: { l: 20, r: 20, t: 50, b: 20 },
        paper_bgcolor: 'transparent',
        plot_bgcolor: 'transparent',
      },
      { responsive: true, displayModeBar: false, displaylogo: false }
    )

    return () => {
      if (containerRef.current) Plotly.purge(containerRef.current)
    }
  }, [result])

  return <div ref={containerRef} style={{ width: '100%' }} />
}

// ─── 状态 Tag ────────────────────────────────────────────────

const STATUS_MAP: Record<string, { color: string; label: string }> = {
  optimal: { color: 'green', label: '最优解' },
  infeasible: { color: 'red', label: '无可行解' },
  unbounded: { color: 'orange', label: '无界' },
  error: { color: 'red', label: '求解错误' },
}

// ─── 单因子选择器（连接 → 表 → 因子 三级联动）────────────────

function SingleFactorPicker({
  value, onChange, placeholder,
}: {
  value: FactorDataRef | null
  onChange: (ref: FactorDataRef | null) => void
  placeholder?: string
}) {
  const [connections, setConnections] = useState<Connection[]>([])
  const [tables, setTables] = useState<FactorTable[]>([])
  const [factors, setFactors] = useState<FactorInfo[]>([])
  const [connId, setConnId] = useState<string | null>(value?.conn_id || null)
  const [tableName, setTableName] = useState<string | null>(value?.table_name || null)
  const [factorName, setFactorName] = useState<string | null>(value?.factor_name || null)
  const [dt, setDt] = useState<string | null>(value?.dt || null)
  const [firstDt, setFirstDt] = useState<string | null>(null)
  const [lastDt, setLastDt] = useState<string | null>(null)

  useEffect(() => { getConnections().then((d) => setConnections(d as unknown as Connection[])).catch(() => {}) }, [])

  useEffect(() => {
    if (!connId) { setTables([]); return }
    getTables(connId).then((d) => setTables(d as unknown as FactorTable[])).catch(() => {})
  }, [connId])

  useEffect(() => {
    if (!connId || !tableName) { setFactors([]); return }
    getFactors(connId, tableName).then((d) => setFactors(d as unknown as FactorInfo[])).catch(() => {})
  }, [connId, tableName])

  // 选因子后加载日期范围
  useEffect(() => {
    if (!connId || !tableName || !factorName) { setFirstDt(null); setLastDt(null); setDt(null); return }
    getFactorStats(connId, tableName, factorName).then((s) => {
      const stats = s as unknown as { first_dt: string | null; last_dt: string | null }
      setFirstDt(stats.first_dt || null)
      setLastDt(stats.last_dt || null)
      // 默认使用最新时点
      if (!dt && stats.last_dt) {
        setDt(stats.last_dt)
      }
    }).catch(() => {})
  }, [connId, tableName, factorName])

  const emit = (c: string | null, t: string | null, f: string | null, d: string | null) => {
    if (c && t && f) {
      onChange({ conn_id: c, table_name: t, factor_name: f, dt: d || undefined })
    } else {
      onChange(null)
    }
  }

  const handleFactorChange = (f: string | null) => {
    setFactorName(f)
    setDt(null)  // 切换因子时重置日期
    if (f) {
      emit(connId, tableName, f, null)
    } else {
      emit(connId, tableName, null, null)
    }
  }

  return (
    <Space direction="vertical" style={{ width: '100%' }} size={4}>
      <Select
        style={{ width: '100%' }} size="small"
        placeholder="选择因子库连接"
        value={connId}
        allowClear
        onChange={(v) => { setConnId(v); setTableName(null); setFactorName(null); emit(v, null, null, null) }}
        options={connections.map((c) => ({ value: c.id, label: `${c.name} (${c.db_type})` }))}
      />
      {connId && (
        <Select
          style={{ width: '100%' }} size="small"
          placeholder="选择因子表"
          value={tableName}
          allowClear
          onChange={(v) => { setTableName(v); setFactorName(null); emit(connId, v, null, null) }}
          options={tables.map((t) => ({ value: t.name, label: `${t.name} (${t.factor_count ?? '?'} 因子)` }))}
        />
      )}
      {tableName && (
        <Select
          style={{ width: '100%' }} size="small"
          placeholder={placeholder || '搜索并选择因子'}
          showSearch
          value={factorName}
          allowClear
          onChange={handleFactorChange}
          filterOption={(input, option) => (option?.label as string)?.toLowerCase().includes(input.toLowerCase())}
          options={factors.map((f) => ({ value: f.name, label: f.name }))}
        />
      )}
      {factorName && firstDt && lastDt && (
        <Input
          style={{ width: '100%' }} size="small"
          placeholder={`日期范围: ${firstDt?.slice(0, 10)} ~ ${lastDt?.slice(0, 10)}，默认最新`}
          value={dt || ''}
          allowClear
          onChange={(e) => { const v = e.target.value || null; setDt(v); emit(connId, tableName, factorName, v) }}
        />
      )}
    </Space>
  )
}

// ─── 主页面 ──────────────────────────────────────────────────

function PortfolioOptimizer() {
  // ── 配置状态 ─────────────────────────────────────────────
  const [solver, setSolver] = useState('cvxpy')
  const [solvers, setSolvers] = useState<SolverInfo[]>([])
  const [objType, setObjType] = useState<string>('mean_variance')
  const [riskAversion, setRiskAversion] = useState(1.0)
  const [expectedReturnCoef, setExpectedReturnCoef] = useState(0.0)
  const [constraints, setConstraints] = useState<ConstraintDef[]>([])
  const [taskName, setTaskName] = useState('未命名优化')

  // ── 求解状态 ─────────────────────────────────────────────
  const [solving, setSolving] = useState(false)
  const [result, setResult] = useState<OptimizeResponse | null>(null)

  // ── 协方差来源模式 ───────────────────────────────────────
  const [covMode, setCovMode] = useState<'risk_db' | 'json'>('json')

  // ── 风险库选择器状态 ─────────────────────────────────────
  const [riskDbs, setRiskDbs] = useState<RiskDBInfo[]>([])
  const [riskDbId, setRiskDbId] = useState<string | null>(null)
  const [riskTables, setRiskTables] = useState<RiskTableInfo[]>([])
  const [riskTable, setRiskTable] = useState<string | null>(null)
  const [riskDates, setRiskDates] = useState<string[]>([])
  const [riskDt, setRiskDt] = useState<string | null>(null)

  // ── 手动协方差矩阵 ───────────────────────────────────────
  const [covInput, setCovInput] = useState('')
  const [assetIdsInput, setAssetIdsInput] = useState('')

  // ── 因子引用 ─────────────────────────────────────────────
  const [expectedReturnRef, setExpectedReturnRef] = useState<FactorDataRef | null>(null)
  const [maskRef, setMaskRef] = useState<FactorDataRef | null>(null)
  const [benchmarkRef, setBenchmarkRef] = useState<FactorDataRef | null>(null)

  // ── 加载求解器列表 ───────────────────────────────────────
  useEffect(() => {
    listSolvers().then((data) => {
      const list = data as unknown as SolverInfo[]
      setSolvers(list)
      if (list.length > 0 && !solver) setSolver(list[0].key)
    }).catch(() => {
      setSolvers([{ key: 'cvxpy', label: 'CVXPY', desc: '基于 CVXPY 的凸优化求解器' }])
    })
  }, [])

  // ── 加载风险库列表 ───────────────────────────────────────
  useEffect(() => {
    getRiskDatabases().then((d) => setRiskDbs(d as unknown as RiskDBInfo[])).catch(() => {})
  }, [])

  // ── 选风险库 → 加载表列表 ─────────────────────────────────
  useEffect(() => {
    if (!riskDbId) { setRiskTables([]); setRiskTable(null); return }
    getRiskTables(riskDbId).then((d) => setRiskTables(d as unknown as RiskTableInfo[])).catch(() => {})
  }, [riskDbId])

  // ── 选风险表 → 加载时点列表 ──────────────────────────────
  useEffect(() => {
    if (!riskDbId || !riskTable) { setRiskDates([]); setRiskDt(null); return }
    getTableDates(riskDbId, riskTable).then((d) => {
      const dates = d as unknown as string[]
      setRiskDates(dates)
      if (dates.length > 0) setRiskDt(dates[dates.length - 1])
    }).catch(() => {})
  }, [riskDbId, riskTable])

  // ── 求解器切换时加载对应默认优化选项 ────────────────────
  useEffect(() => {
    if (!solver) return
    getDefaultOptimOptions(solver).then((data) => {
      const opts = data as unknown as Record<string, any>
      setOptimOptionsStr(JSON.stringify(opts, null, 2))
    }).catch(() => {
      setOptimOptionsStr('{\n  "verbose": false\n}')
    })
  }, [solver])

  // ── 约束弹窗 ─────────────────────────────────────────────
  const [modalOpen, setModalOpen] = useState(false)
  const [editingIndex, setEditingIndex] = useState<number | null>(null)
  const [constraintType, setConstraintType] = useState<ConstraintDef['type']>('budget')
  const [constraintValues, setConstraintValues] = useState<Record<string, any>>({})

  // ── 优化选项 ─────────────────────────────────────────────
  const [optimOptionsStr, setOptimOptionsStr] = useState('{}')

  // ── 任务保存/加载 ─────────────────────────────────────────
  const [savedTasks, setSavedTasks] = useState<SavedTaskInfo[]>([])
  const [saving, setSaving] = useState(false)

  const loadSavedTasks = useCallback(async () => {
    try {
      const data = await listTasks() as unknown as SavedTaskInfo[]
      setSavedTasks(data)
    } catch { /* ignore */ }
  }, [])

  useEffect(() => { loadSavedTasks() }, [loadSavedTasks])

  /** 构建当前配置的请求体 */
  const buildRequest = useCallback((): OptimizeRequest => {
    let optimOptions: Record<string, any> = {}
    try { optimOptions = JSON.parse(optimOptionsStr) } catch { optimOptions = {} }

    const covMode_ = covMode === 'risk_db' && riskDbId && riskTable && riskDt ? 'risk_db' : 'json'
    return {
      name: taskName,
      solver,
      objective: {
        type: objType as OptimizeRequest['objective']['type'],
        risk_aversion: riskAversion,
        expected_return_coef: expectedReturnCoef,
      },
      constraints,
      optim_options: optimOptions,
      risk_db_id: covMode_ === 'risk_db' ? riskDbId : null,
      risk_table_name: covMode_ === 'risk_db' ? riskTable : null,
      risk_dt: covMode_ === 'risk_db' ? riskDt : null,
      cov_matrix: covMode_ !== 'risk_db' && covInput.trim() ? JSON.parse(covInput) : null,
      asset_ids: covMode_ !== 'risk_db' && assetIdsInput.trim()
        ? assetIdsInput.split(',').map((s) => s.trim()).filter(Boolean) : null,
      expected_return_ref: expectedReturnRef,
      mask_ref: maskRef,
      benchmark_ref: benchmarkRef,
    }
  }, [taskName, solver, objType, riskAversion, expectedReturnCoef, constraints,
      optimOptionsStr, covMode, riskDbId, riskTable, riskDt, covInput, assetIdsInput,
      expectedReturnRef, maskRef, benchmarkRef])

  /** 保存当前配置 */
  const handleSave = useCallback(async () => {
    if (!taskName.trim()) { message.warning('请先输入任务名称'); return }
    setSaving(true)
    try {
      const req = buildRequest()
      await saveTask(taskName, req)
      message.success(`已保存: ${taskName}`)
      loadSavedTasks()
    } catch (e: any) {
      message.error(`保存失败: ${e?.response?.data?.detail || e?.message || ''}`)
    } finally { setSaving(false) }
  }, [taskName, buildRequest, loadSavedTasks])

  /** 加载已保存配置 */
  const handleLoad = useCallback(async (taskId: string) => {
    try {
      const data = await getTask(taskId) as unknown as { name: string; config: OptimizeRequest }
      const cfg = data.config
      setTaskName(cfg.name || '')
      setSolver(cfg.solver || 'cvxpy')
      setObjType(cfg.objective?.type || 'mean_variance')
      setRiskAversion(cfg.objective?.risk_aversion ?? 1.0)
      setExpectedReturnCoef(cfg.objective?.expected_return_coef ?? 0.0)
      setConstraints(cfg.constraints || [])
      setOptimOptionsStr(JSON.stringify(cfg.optim_options || {}, null, 2))
      setCovMode(cfg.risk_db_id ? 'risk_db' : 'json')
      setRiskDbId(cfg.risk_db_id || null)
      setRiskTable(cfg.risk_table_name || null)
      setRiskDt(cfg.risk_dt || null)
      setCovInput(cfg.cov_matrix ? JSON.stringify(cfg.cov_matrix) : '')
      setAssetIdsInput(cfg.asset_ids?.join(', ') || '')
      setExpectedReturnRef(cfg.expected_return_ref || null)
      setMaskRef(cfg.mask_ref || null)
      setBenchmarkRef(cfg.benchmark_ref || null)
      message.success(`已加载: ${cfg.name || taskId}`)
    } catch (e: any) {
      message.error(`加载失败: ${e?.response?.data?.detail || e?.message || ''}`)
    }
  }, [])

  /** 删除已保存配置 */
  const handleDeleteTask = useCallback(async (taskId: string) => {
    try {
      await deleteTask(taskId)
      message.success('已删除')
      loadSavedTasks()
    } catch (e: any) {
      message.error(`删除失败: ${e?.response?.data?.detail || e?.message || ''}`)
    }
  }, [loadSavedTasks])

  // ── 提交求解 ─────────────────────────────────────────────
  const handleSolve = useCallback(async () => {
    setSolving(true)
    setResult(null)
    try {
      const req = buildRequest()

      const res = await runOptimization(req) as unknown as OptimizeResponse
      setResult(res)
      if (res.status === 'optimal') {
        message.success(`求解成功！耗时 ${res.solve_time?.toFixed(2) ?? '?'}s`)
      } else {
        message.warning(`求解状态: ${res.status} — ${res.message}`)
      }
    } catch (e: any) {
      const detail = e?.response?.data?.detail || e?.response?.data?.message || e?.message || '未知错误'
      message.error(`求解失败: ${detail}`)
    } finally {
      setSolving(false)
    }
  }, [buildRequest])

  // ── 约束编辑 ─────────────────────────────────────────────
  const handleAddConstraint = () => {
    setEditingIndex(null)
    setConstraintType('budget')
    setConstraintValues({ ...CONSTRAINT_DEFAULTS.budget })
    setModalOpen(true)
  }

  const handleEditConstraint = (index: number) => {
    const c = constraints[index]
    setEditingIndex(index)
    setConstraintType(c.type)
    const defaults = CONSTRAINT_DEFAULTS[c.type] || {}
    setConstraintValues({ ...defaults, ...c })
    setModalOpen(true)
  }

  const handleDeleteConstraint = (index: number) => {
    setConstraints((prev) => prev.filter((_, i) => i !== index))
  }

  const handleModalOk = () => {
    const newConstraint: ConstraintDef = {
      type: constraintType,
      ...constraintValues,
    }
    if (editingIndex !== null) {
      setConstraints((prev) => prev.map((c, i) => (i === editingIndex ? newConstraint : c)))
    } else {
      setConstraints((prev) => [...prev, newConstraint])
    }
    setModalOpen(false)
  }

  // ── 导出权重 ─────────────────────────────────────────────
  const handleExport = () => {
    if (!result) return
    const url = getWeightsCsvUrl(result.solution_id)
    window.open(url, '_blank')
  }

  const statusInfo = result ? STATUS_MAP[result.status] || STATUS_MAP.error : null

  return (
    <>
      <Row gutter={16} style={{ height: '100%' }}>
        {/* 左侧：配置区 */}
        <Col span={8}>
          <Card
            size="small"
            title="优化配置"
            style={{ height: '100%', overflow: 'auto' }}
            extra={
              <Button
                type="primary"
                icon={<PlayCircleOutlined />}
                loading={solving}
                onClick={handleSolve}
                disabled={covMode === 'json' ? !covInput.trim() : !(riskDbId && riskTable && riskDt)}
              >
                求解
              </Button>
            }
          >
            {/* 任务名称 */}
            <Form.Item label="任务名称" style={{ marginBottom: 4 }}>
              <Input
                value={taskName}
                onChange={(e) => setTaskName(e.target.value)}
                placeholder="输入任务名称"
              />
            </Form.Item>

            {/* 保存 / 加载工具栏 */}
            <Row gutter={8} style={{ marginBottom: 12 }}>
              <Col flex="auto">
                <Select
                  style={{ width: '100%' }}
                  size="small"
                  value={undefined}
                  placeholder={savedTasks.length === 0 ? '暂无已保存的任务' : '📂 加载已保存的配置...'}
                  onChange={handleLoad}
                  options={savedTasks.map((t) => ({
                    value: t.id,
                    label: (
                      <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                        <span>{t.name}</span>
                        <Popconfirm
                          title="确定删除？"
                          onConfirm={() => handleDeleteTask(t.id)}
                        >
                          <Button
                            type="link" size="small" danger
                            icon={<DeleteOutlined />}
                            onClick={(e) => e.stopPropagation()}
                          />
                        </Popconfirm>
                      </Space>
                    ),
                  }))}
                  dropdownStyle={{ minWidth: 320 }}
                  popupMatchSelectWidth={true}
                />
              </Col>
              <Col>
                <Button
                  size="small"
                  icon={<DownloadOutlined style={{ rotate: '180deg' }} />}
                  loading={saving}
                  onClick={handleSave}
                >
                  保存
                </Button>
              </Col>
            </Row>

            <Divider style={{ margin: '8px 0' }} />

            {/* 求解器选择 */}
            <Form.Item label="求解器" style={{ marginBottom: 8 }}>
              <Select
                value={solver}
                onChange={setSolver}
                options={solvers.map((s) => ({
                  value: s.key,
                  label: `${s.label}  —  ${s.desc}`,
                }))}
              />
            </Form.Item>

            {/* 目标选择 */}
            <Form.Item label="优化目标" style={{ marginBottom: 8 }}>
              <Select
                value={objType}
                onChange={(v) => setObjType(v)}
                options={OBJECTIVE_TYPES.map((t) => ({
                  value: t.value,
                  label: `${t.label}  —  ${t.desc}`,
                }))}
              />
            </Form.Item>

            <ObjectiveForm
              objType={objType}
              riskAversion={riskAversion}
              expectedReturnCoef={expectedReturnCoef}
              onRiskAversionChange={setRiskAversion}
              onExpectedReturnCoefChange={setExpectedReturnCoef}
            />

            <Divider style={{ margin: '8px 0' }} />

            {/* 协方差矩阵 — 风险库 / 手动 JSON */}
            <Form.Item label="协方差来源" style={{ marginBottom: 4 }}>
              <Radio.Group
                value={covMode}
                onChange={(e) => setCovMode(e.target.value)}
                size="small"
                optionType="button"
              >
                <Radio.Button value="risk_db">风险库</Radio.Button>
                <Radio.Button value="json">手动输入</Radio.Button>
              </Radio.Group>
            </Form.Item>

            {covMode === 'risk_db' ? (
              <Space direction="vertical" style={{ width: '100%' }} size={4}>
                <Select
                  style={{ width: '100%' }} size="small"
                  placeholder="选择风险库"
                  value={riskDbId}
                  onChange={(v) => { setRiskDbId(v); setRiskTable(null); setRiskDt(null) }}
                  options={riskDbs.map((d) => ({ value: d.id, label: `${d.name} (${d.db_type})` }))}
                />
                {riskDbId && (
                  <Select
                    style={{ width: '100%' }} size="small"
                    placeholder="选择风险表"
                    value={riskTable}
                    onChange={(v) => { setRiskTable(v); setRiskDt(null) }}
                    options={riskTables.map((t) => ({ value: t.name, label: `${t.name} (${t.dt_count} 时点)` }))}
                  />
                )}
                {riskTable && (
                  <Select
                    style={{ width: '100%' }} size="small"
                    placeholder="选择时点"
                    value={riskDt}
                    onChange={setRiskDt}
                    showSearch
                    options={riskDates.map((d) => ({ value: d, label: d }))}
                  />
                )}
              </Space>
            ) : (
              <>
                <Form.Item label="协方差矩阵 (JSON)" tooltip="二维数组 JSON" style={{ marginBottom: 4 }}>
                  <Input.TextArea
                    rows={4}
                    value={covInput}
                    onChange={(e) => setCovInput(e.target.value)}
                    placeholder='[[0.04, 0.01], [0.01, 0.09]]'
                    style={{ fontFamily: 'monospace', fontSize: 12 }}
                  />
                </Form.Item>
                <Form.Item label="资产 ID (逗号分隔)" style={{ marginBottom: 4 }}>
                  <Input
                    value={assetIdsInput}
                    onChange={(e) => setAssetIdsInput(e.target.value)}
                    placeholder="000001.SZ, 600519.SH"
                  />
                </Form.Item>
              </>
            )}

            <Divider style={{ margin: '8px 0' }} />

            {/* 预期收益 — 因子选择器 */}
            <Form.Item label="预期收益" tooltip="选因子作为预期收益向量，使用最新时点截面数据" style={{ marginBottom: 4 }}>
              <SingleFactorPicker
                value={expectedReturnRef}
                onChange={setExpectedReturnRef}
                placeholder="选择预期收益因子（可选）"
              />
            </Form.Item>

            <Divider style={{ margin: '8px 0' }} />

            {/* Mask — 因子选择器 */}
            <Form.Item label="Mask（可选资产）" tooltip="选因子，其值非 NaN 且非零的资产视为可投资" style={{ marginBottom: 4 }}>
              <SingleFactorPicker
                value={maskRef}
                onChange={setMaskRef}
                placeholder="选择 Mask 因子（可选，留空=全选）"
              />
            </Form.Item>

            <Divider style={{ margin: '8px 0' }} />

            {/* 基准权重 — 因子选择器 */}
            <Form.Item label="基准权重" tooltip="选因子作为基准权重（如市值），会自动归一化" style={{ marginBottom: 4 }}>
              <SingleFactorPicker
                value={benchmarkRef}
                onChange={setBenchmarkRef}
                placeholder="选择基准权重因子（可选）"
              />
            </Form.Item>

            <Divider style={{ margin: '8px 0' }} />

            {/* 优化选项 */}
            <Form.Item
              label="优化选项 (JSON)"
              tooltip="求解器参数，如 solver/verbose/max_iters 等。默认值来自 QSWebConfig.json。修改仅本次生效。"
              style={{ marginBottom: 8 }}
            >
              <Input.TextArea
                rows={6}
                value={optimOptionsStr}
                onChange={(e) => setOptimOptionsStr(e.target.value)}
                style={{ fontFamily: 'monospace', fontSize: 12 }}
              />
            </Form.Item>

            <Divider style={{ margin: '8px 0' }} />

            {/* 约束列表 */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
              <Text strong>约束条件</Text>
              <Button size="small" type="dashed" icon={<PlusOutlined />} onClick={handleAddConstraint}>
                添加约束
              </Button>
            </div>

            {constraints.length === 0 ? (
              <Empty
                description="暂无约束，点击「添加约束」配置"
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                style={{ margin: '12px 0' }}
              />
            ) : (
              <List
                size="small"
                dataSource={constraints}
                renderItem={(c, i) => (
                  <List.Item
                    actions={[
                      <Button key="edit" size="small" type="link" icon={<EditOutlined />}
                        onClick={() => handleEditConstraint(i)} />,
                      <Popconfirm key="del" title="确定删除该约束？"
                        onConfirm={() => handleDeleteConstraint(i)}>
                        <Button size="small" type="link" danger icon={<DeleteOutlined />} />
                      </Popconfirm>,
                    ]}
                  >
                    <List.Item.Meta
                      title={
                        <Space>
                          <Tag color="blue">{CONSTRAINT_TYPES.find((t) => t.value === c.type)?.label || c.type}</Tag>
                        </Space>
                      }
                      description={
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          {JSON.stringify({ ...c, type: undefined })}
                        </Text>
                      }
                    />
                  </List.Item>
                )}
              />
            )}
          </Card>
        </Col>

        {/* 右侧：结果区 */}
        <Col span={16}>
          <Card
            size="small"
            title="优化结果"
            extra={
              result?.status === 'optimal' ? (
                <Button icon={<DownloadOutlined />} onClick={handleExport}>
                  导出权重 CSV
                </Button>
              ) : null
            }
            style={{ height: '100%', overflow: 'auto' }}
          >
            {!result && !solving && (
              <Empty
                description="配置协方差矩阵（风险库或手动输入）和约束条件后，点击「求解」开始优化"
                style={{ marginTop: 60 }}
              />
            )}

            {solving && (
              <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 300 }}>
                <Spin size="large" tip="正在求解优化问题..." />
              </div>
            )}

            {result && (
              <>
                {/* 状态卡片 */}
                <Row gutter={16} style={{ marginBottom: 16 }}>
                  <Col span={6}>
                    <Card size="small">
                      <Statistic
                        title="状态"
                        value={statusInfo?.label || result.status}
                        valueStyle={{ color: statusInfo?.color === 'green' ? '#52c41a' : '#ff4d4f' }}
                      />
                    </Card>
                  </Col>
                  <Col span={6}>
                    <Card size="small">
                      <Statistic title="求解器" value={result.solver_name || '-'} />
                    </Card>
                  </Col>
                  <Col span={6}>
                    <Card size="small">
                      <Statistic title="耗时" value={`${result.solve_time?.toFixed(3) || '?'}s`} />
                    </Card>
                  </Col>
                  <Col span={6}>
                    <Card size="small">
                      <Statistic title="持仓数" value={result.weights.filter((w) => Math.abs(w) > 1e-6).length} />
                    </Card>
                  </Col>
                </Row>

                {result.message && (
                  <Text type="secondary" style={{ display: 'block', marginBottom: 16 }}>
                    求解信息: {result.message}
                  </Text>
                )}

                {result.status === 'optimal' && result.weights.length > 0 && (
                  <Row gutter={16}>
                    <Col span={12}>
                      <WeightChart result={result} />
                    </Col>
                    <Col span={12}>
                      {result.risk_decomposition ? (
                        <RiskDecompChart result={result} />
                      ) : (
                        <Empty description="无风险分解数据" />
                      )}
                    </Col>
                  </Row>
                )}

                {result.status !== 'optimal' && (
                  <Empty
                    description={`无最优解: ${result.message || '请检查约束条件是否过于严格'}`}
                    style={{ marginTop: 40 }}
                  />
                )}
              </>
            )}
          </Card>
        </Col>
      </Row>

      {/* 约束编辑弹窗 */}
      <Modal
        title={editingIndex !== null ? '编辑约束' : '添加约束'}
        open={modalOpen}
        onOk={handleModalOk}
        onCancel={() => setModalOpen(false)}
        destroyOnClose
      >
        <Form layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item label="约束类型">
            <Select
              value={constraintType}
              onChange={(v) => {
                setConstraintType(v)
                setConstraintValues({ ...(CONSTRAINT_DEFAULTS[v] || {}) })
              }}
              options={CONSTRAINT_TYPES.map((t) => ({
                value: t.value,
                label: `${t.label}  —  ${t.desc}`,
              }))}
            />
          </Form.Item>
          <ConstraintForm
            cType={constraintType}
            values={constraintValues}
            onChange={setConstraintValues}
          />
        </Form>
      </Modal>
    </>
  )
}

export default PortfolioOptimizer
