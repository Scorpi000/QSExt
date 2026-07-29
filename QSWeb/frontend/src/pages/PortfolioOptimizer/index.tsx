/**
 * PortfolioOptimizer - 组合优化页面
 *
 * 布局编排：ObjectiveConfig + ConstraintsEditor（左列配置）+ ResultView（右列结果）。
 * 预期收益/Mask/基准权重从全局因子池选择。
 */

import { useState, useCallback, useEffect } from 'react'
import {
  Row, Col, Card, Form, Select, Input, Button, Radio, Space, message, Divider, Popconfirm,
} from 'antd'
import { PlayCircleOutlined, DownloadOutlined, DeleteOutlined } from '@ant-design/icons'
import type {
  OptimizeRequest, OptimizeResponse, ConstraintDef, SolverInfo, FactorDataRef, SavedTaskInfo,
} from '../../services/portfolio'
import {
  runOptimization, listSolvers, getDefaultOptimOptions,
  listTasks, getTask, saveTask, deleteTask, getWeightsCsvUrl,
} from '../../services/portfolio'
import { getRiskDatabases, getRiskTables, getTableDates } from '../../services/risk'
import type { RiskDBInfo, RiskTableInfo } from '../../services/risk'
import { useFactorPoolStore } from '../../stores/factorPoolStore'
import ObjectiveConfig from './ObjectiveConfig'
import ConstraintsEditor from './ConstraintsEditor'
import ResultView from './ResultView'

// ─── 从全局因子池选择单个因子 ─────────────────────────────

function PoolFactorPicker({
  value, onChange, placeholder,
}: {
  value: FactorDataRef | null
  onChange: (ref: FactorDataRef | null) => void
  placeholder?: string
}) {
  const poolItems = useFactorPoolStore((s) => s.items)

  const selectedId = value
    ? poolItems.find((item) =>
        item.ref.conn_id === value.conn_id &&
        item.ref.table_name === value.table_name &&
        (item.label === value.factor_name || item.qsid === value.factor_name)
      )?.id || null
    : null

  const handleSelect = (id: string | null) => {
    if (!id) { onChange(null); return }
    const item = poolItems.find((p) => p.id === id)
    if (!item) return
    onChange({
      conn_id: item.ref.conn_id || '',
      table_name: item.ref.table_name || '',
      factor_name: item.label,
    })
  }

  return (
    <Select
      style={{ width: '100%' }} size="small"
      placeholder={placeholder || '从全局因子池中选择'}
      value={selectedId}
      allowClear
      onChange={handleSelect}
      showSearch
      filterOption={(input, option) => (option?.label as string)?.toLowerCase().includes(input.toLowerCase())}
      options={poolItems
        .map((item) => ({
          value: item.id,
          label: `${item.label} [${item.source === 'registry' ? '注册中心' : item.ref.table_name || '因子库'}]`,
        }))}
    />
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

  // ── 协方差来源 ───────────────────────────────────────────
  const [covMode, setCovMode] = useState<'risk_db' | 'json'>('json')
  const [riskDbs, setRiskDbs] = useState<RiskDBInfo[]>([])
  const [riskDbId, setRiskDbId] = useState<string | null>(null)
  const [riskTables, setRiskTables] = useState<RiskTableInfo[]>([])
  const [riskTable, setRiskTable] = useState<string | null>(null)
  const [riskDates, setRiskDates] = useState<string[]>([])
  const [riskDt, setRiskDt] = useState<string | null>(null)
  const [covInput, setCovInput] = useState('')
  const [assetIdsInput, setAssetIdsInput] = useState('')

  // ── 因子引用 ─────────────────────────────────────────────
  const [expectedReturnRef, setExpectedReturnRef] = useState<FactorDataRef | null>(null)
  const [maskRef, setMaskRef] = useState<FactorDataRef | null>(null)
  const [benchmarkRef, setBenchmarkRef] = useState<FactorDataRef | null>(null)

  // ── 优化选项 ─────────────────────────────────────────────
  const [optimOptionsStr, setOptimOptionsStr] = useState('{}')

  // ── 任务保存/加载 ────────────────────────────────────────
  const [savedTasks, setSavedTasks] = useState<SavedTaskInfo[]>([])
  const [saving, setSaving] = useState(false)

  // ── 加载 ─────────────────────────────────────────────────
  useEffect(() => {
    listSolvers().then((data) => {
      const list = data as unknown as SolverInfo[]
      setSolvers(list)
      if (list.length > 0 && !solver) setSolver(list[0].key)
    }).catch(() => {
      setSolvers([{ key: 'cvxpy', label: 'CVXPY', desc: '基于 CVXPY 的凸优化求解器' }])
    })
  }, [])
  useEffect(() => { getRiskDatabases().then((d) => setRiskDbs(d as unknown as RiskDBInfo[])).catch(() => {}) }, [])
  useEffect(() => {
    if (!riskDbId) { setRiskTables([]); setRiskTable(null); return }
    getRiskTables(riskDbId).then((d) => setRiskTables(d as unknown as RiskTableInfo[])).catch(() => {})
  }, [riskDbId])
  useEffect(() => {
    if (!riskDbId || !riskTable) { setRiskDates([]); setRiskDt(null); return }
    getTableDates(riskDbId, riskTable).then((d) => {
      const dates = d as unknown as string[]
      setRiskDates(dates)
      if (dates.length > 0) setRiskDt(dates[dates.length - 1])
    }).catch(() => {})
  }, [riskDbId, riskTable])
  useEffect(() => {
    if (!solver) return
    getDefaultOptimOptions(solver).then((data) => {
      setOptimOptionsStr(JSON.stringify(data as unknown as Record<string, any> || {}, null, 2))
    }).catch(() => { setOptimOptionsStr('{\n  "verbose": false\n}') })
  }, [solver])

  const loadSavedTasks = useCallback(async () => {
    try { setSavedTasks((await listTasks()) as unknown as SavedTaskInfo[]) } catch { /* ignore */ }
  }, [])
  useEffect(() => { loadSavedTasks() }, [loadSavedTasks])

  // ── 请求构建 ─────────────────────────────────────────────
  const buildRequest = useCallback((): OptimizeRequest => {
    let optimOptions: Record<string, any> = {}
    try { optimOptions = JSON.parse(optimOptionsStr) } catch { optimOptions = {} }
    const covMode_ = covMode === 'risk_db' && riskDbId && riskTable && riskDt ? 'risk_db' : 'json'
    return {
      name: taskName, solver,
      objective: { type: objType as OptimizeRequest['objective']['type'], risk_aversion: riskAversion, expected_return_coef: expectedReturnCoef },
      constraints,
      optim_options: optimOptions,
      risk_db_id: covMode_ === 'risk_db' ? riskDbId : null,
      risk_table_name: covMode_ === 'risk_db' ? riskTable : null,
      risk_dt: covMode_ === 'risk_db' ? riskDt : null,
      cov_matrix: covMode_ !== 'risk_db' && covInput.trim() ? JSON.parse(covInput) : null,
      asset_ids: covMode_ !== 'risk_db' && assetIdsInput.trim() ? assetIdsInput.split(',').map((s) => s.trim()).filter(Boolean) : null,
      expected_return_ref: expectedReturnRef, mask_ref: maskRef, benchmark_ref: benchmarkRef,
    }
  }, [taskName, solver, objType, riskAversion, expectedReturnCoef, constraints, optimOptionsStr, covMode, riskDbId, riskTable, riskDt, covInput, assetIdsInput, expectedReturnRef, maskRef, benchmarkRef])

  // ── 保存/加载 ────────────────────────────────────────────
  const handleSave = useCallback(async () => {
    if (!taskName.trim()) { message.warning('请先输入任务名称'); return }
    setSaving(true)
    try { await saveTask(taskName, buildRequest()); message.success(`已保存: ${taskName}`); loadSavedTasks() }
    catch (e: any) { message.error(`保存失败: ${e?.response?.data?.detail || e?.message || ''}`) }
    finally { setSaving(false) }
  }, [taskName, buildRequest, loadSavedTasks])

  const handleLoad = useCallback(async (taskId: string) => {
    try {
      const data = await getTask(taskId) as unknown as { name: string; config: OptimizeRequest }
      const cfg = data.config
      setTaskName(cfg.name || ''); setSolver(cfg.solver || 'cvxpy')
      setObjType(cfg.objective?.type || 'mean_variance')
      setRiskAversion(cfg.objective?.risk_aversion ?? 1.0)
      setExpectedReturnCoef(cfg.objective?.expected_return_coef ?? 0.0)
      setConstraints(cfg.constraints || [])
      setOptimOptionsStr(JSON.stringify(cfg.optim_options || {}, null, 2))
      setCovMode(cfg.risk_db_id ? 'risk_db' : 'json')
      setRiskDbId(cfg.risk_db_id || null); setRiskTable(cfg.risk_table_name || null); setRiskDt(cfg.risk_dt || null)
      setCovInput(cfg.cov_matrix ? JSON.stringify(cfg.cov_matrix) : '')
      setAssetIdsInput(cfg.asset_ids?.join(', ') || '')
      setExpectedReturnRef(cfg.expected_return_ref || null)
      setMaskRef(cfg.mask_ref || null)
      setBenchmarkRef(cfg.benchmark_ref || null)
      message.success(`已加载: ${cfg.name || taskId}`)
    } catch (e: any) { message.error(`加载失败: ${e?.response?.data?.detail || e?.message || ''}`) }
  }, [])

  const handleDeleteTask = useCallback(async (taskId: string) => {
    try { await deleteTask(taskId); message.success('已删除'); loadSavedTasks() }
    catch (e: any) { message.error(`删除失败: ${e?.response?.data?.detail || e?.message || ''}`) }
  }, [loadSavedTasks])

  // ── 求解 ─────────────────────────────────────────────────
  const handleSolve = useCallback(async () => {
    setSolving(true); setResult(null)
    try {
      const res = await runOptimization(buildRequest()) as unknown as OptimizeResponse
      setResult(res)
      if (res.status === 'optimal') message.success(`求解成功！耗时 ${res.solve_time?.toFixed(2) ?? '?'}s`)
      else message.warning(`求解状态: ${res.status} — ${res.message}`)
    } catch (e: any) {
      message.error(`求解失败: ${e?.response?.data?.detail || e?.response?.data?.message || e?.message || '未知错误'}`)
    } finally { setSolving(false) }
  }, [buildRequest])

  return (
    <>
      <Row gutter={16} style={{ height: '100%' }}>
        {/* 左侧：配置区 */}
        <Col span={8}>
          <Card size="small" title="优化配置" style={{ height: '100%', overflow: 'auto' }}
            extra={
              <Button type="primary" icon={<PlayCircleOutlined />} loading={solving} onClick={handleSolve}
                disabled={covMode === 'json' ? !covInput.trim() : !(riskDbId && riskTable && riskDt)}>
                求解
              </Button>
            }>
            {/* 任务名称 + 保存/加载 */}
            <Form.Item label="任务名称" style={{ marginBottom: 4 }}>
              <Input value={taskName} onChange={(e) => setTaskName(e.target.value)} placeholder="输入任务名称" />
            </Form.Item>
            <Row gutter={8} style={{ marginBottom: 12 }}>
              <Col flex="auto">
                <Select style={{ width: '100%' }} size="small" value={undefined}
                  placeholder={savedTasks.length === 0 ? '暂无已保存的任务' : '📂 加载已保存的配置...'}
                  onChange={handleLoad}
                  options={savedTasks.map((t) => ({
                    value: t.id,
                    label: (
                      <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                        <span>{t.name}</span>
                        <Popconfirm title="确定删除？" onConfirm={() => handleDeleteTask(t.id)}>
                          <Button type="link" size="small" danger icon={<DeleteOutlined />} onClick={(e) => e.stopPropagation()} />
                        </Popconfirm>
                      </Space>
                    ),
                  }))}
                  popupMatchSelectWidth={true} />
              </Col>
              <Col>
                <Button size="small" icon={<DownloadOutlined style={{ rotate: '180deg' }} />} loading={saving} onClick={handleSave}>保存</Button>
              </Col>
            </Row>
            <Divider style={{ margin: '8px 0' }} />

            {/* 目标配置 */}
            <ObjectiveConfig
              solver={solver} solvers={solvers} objType={objType}
              riskAversion={riskAversion} expectedReturnCoef={expectedReturnCoef}
              onSolverChange={setSolver} onObjTypeChange={setObjType}
              onRiskAversionChange={setRiskAversion} onExpectedReturnCoefChange={setExpectedReturnCoef} />

            <Divider style={{ margin: '8px 0' }} />

            {/* 协方差矩阵 */}
            <Form.Item label="协方差来源" style={{ marginBottom: 4 }}>
              <Radio.Group value={covMode} onChange={(e) => setCovMode(e.target.value)} size="small" optionType="button">
                <Radio.Button value="risk_db">风险库</Radio.Button>
                <Radio.Button value="json">手动输入</Radio.Button>
              </Radio.Group>
            </Form.Item>
            {covMode === 'risk_db' ? (
              <Space direction="vertical" style={{ width: '100%' }} size={4}>
                <Select style={{ width: '100%' }} size="small" placeholder="选择风险库" value={riskDbId}
                  onChange={(v) => { setRiskDbId(v); setRiskTable(null); setRiskDt(null) }}
                  options={riskDbs.map((d) => ({ value: d.id, label: `${d.name} (${d.db_type})` }))} />
                {riskDbId && (
                  <Select style={{ width: '100%' }} size="small" placeholder="选择风险表" value={riskTable}
                    onChange={(v) => { setRiskTable(v); setRiskDt(null) }}
                    options={riskTables.map((t) => ({ value: t.name, label: `${t.name} (${t.dt_count} 时点)` }))} />
                )}
                {riskTable && (
                  <Select style={{ width: '100%' }} size="small" placeholder="选择时点" value={riskDt}
                    onChange={setRiskDt} showSearch
                    options={riskDates.map((d) => ({ value: d, label: d }))} />
                )}
              </Space>
            ) : (
              <>
                <Form.Item label="协方差矩阵 (JSON)" style={{ marginBottom: 4 }}>
                  <Input.TextArea rows={4} value={covInput} onChange={(e) => setCovInput(e.target.value)}
                    placeholder='[[0.04, 0.01], [0.01, 0.09]]'
                    style={{ fontFamily: 'monospace', fontSize: 12 }} />
                </Form.Item>
                <Form.Item label="资产 ID (逗号分隔)" style={{ marginBottom: 4 }}>
                  <Input value={assetIdsInput} onChange={(e) => setAssetIdsInput(e.target.value)} placeholder="000001.SZ, 600519.SH" />
                </Form.Item>
              </>
            )}

            <Divider style={{ margin: '8px 0' }} />

            {/* 预期收益 */}
            <Form.Item label="预期收益" tooltip="从全局因子池选因子作为预期收益向量" style={{ marginBottom: 4 }}>
              <PoolFactorPicker value={expectedReturnRef} onChange={setExpectedReturnRef} placeholder="选择预期收益因子（可选）" />
            </Form.Item>
            <Divider style={{ margin: '8px 0' }} />

            {/* Mask */}
            <Form.Item label="Mask（可选资产）" tooltip="从全局因子池选因子，非 NaN/非零=可投资" style={{ marginBottom: 4 }}>
              <PoolFactorPicker value={maskRef} onChange={setMaskRef} placeholder="选择 Mask 因子（可选，留空=全选）" />
            </Form.Item>
            <Divider style={{ margin: '8px 0' }} />

            {/* 基准权重 */}
            <Form.Item label="基准权重" tooltip="从全局因子池选因子作为基准权重" style={{ marginBottom: 4 }}>
              <PoolFactorPicker value={benchmarkRef} onChange={setBenchmarkRef} placeholder="选择基准权重因子（可选）" />
            </Form.Item>
            <Divider style={{ margin: '8px 0' }} />

            {/* 优化选项 */}
            <Form.Item label="优化选项 (JSON)" tooltip="求解器参数" style={{ marginBottom: 8 }}>
              <Input.TextArea rows={6} value={optimOptionsStr} onChange={(e) => setOptimOptionsStr(e.target.value)}
                style={{ fontFamily: 'monospace', fontSize: 12 }} />
            </Form.Item>

            <Divider style={{ margin: '8px 0' }} />

            <Divider style={{ margin: '8px 0' }} />

            {/* 约束条件 */}
            <ConstraintsEditor constraints={constraints} onConstraintsChange={setConstraints} />
          </Card>
        </Col>

        {/* 右侧：结果区 */}
        <Col span={16}>
          <Card size="small" title="优化结果"
            extra={result?.status === 'optimal' ? <Button icon={<DownloadOutlined />} onClick={() => {
              if (result) window.open(getWeightsCsvUrl(result.solution_id), '_blank')
            }}>导出权重 CSV</Button> : null}
            style={{ height: '100%', overflow: 'auto' }}>
            <ResultView result={result} solving={solving} />
          </Card>
        </Col>
      </Row>

    </>
  )
}

export default PortfolioOptimizer
