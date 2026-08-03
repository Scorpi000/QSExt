/**
 * MiningStudio - 因子挖掘管理页面 (/mining)
 *
 * 布局：左侧任务列表 + 右侧配置/结果/因子树面板。
 * 支持新建任务、接续挖掘、结果浏览、因子树可视化和因子导出。
 */

import { useState, useEffect, useCallback } from 'react'
import {
  Layout,
  Button,
  List,
  Tabs,
  Form,
  Select,
  InputNumber,
  Input,
  Table,
  Tag,
  Space,
  message,
  Empty,
  Popconfirm,
  Modal,
  DatePicker,
  Radio,
  Tooltip,
  Row,
  Col,
  Card,
} from 'antd'
import {
  PlusOutlined,
  RocketOutlined,
  ExportOutlined,
  DeleteOutlined,
  ImportOutlined,
  InfoCircleOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import ReactFlow, {
  Node,
  Edge,
  Background,
  Controls,
  MarkerType,
  useNodesState,
  useEdgesState,
} from 'reactflow'
import 'reactflow/dist/style.css'
import {
  listTasks,
  getTask,
  deleteTask,
  createTask,
  submitRun,
  continueMining,
  getRunResult,
  getFactorTree,
  exportFactor,
  importFactorsFromScript,
  listFrameworks,
  getFrameworkConfig,
  type MiningTaskSummary,
  type MiningTask,
  type FrameworkInfo,
  type GPRunConfig,
  type RunResult,
  type FactorTreeDAG,
  type HallOfFameEntry,
} from '../../services/mining'
import { getTables, getFactors, type FactorInfo } from '../../services/factor'
import { useFactorPoolStore } from '../../stores/factorPoolStore'
import EvalModulePicker, { type EvalPickerValue } from '../../components/EvalModulePicker'
import FitnessChart from '../../components/FitnessChart'
import { getBacktestConfig, getSectionIdSources, type SectionIdSource } from '../../services/backtest'

const { Sider, Content } = Layout
const { RangePicker } = DatePicker

// 因子树节点着色
const NODE_COLORS: Record<string, string> = {
  operator: '#4682b4',
  terminal: '#91caff',
}

function MiningStudio() {
  // 任务列表
  const [tasks, setTasks] = useState<MiningTaskSummary[]>([])
  const [activeTask, setActiveTask] = useState<MiningTask | null>(null)
  const [taskLoading, setTaskLoading] = useState(false)

  // 配置
  const [frameworks, setFrameworks] = useState<FrameworkInfo[]>([])
  const [frameworkConfig, setFrameworkConfig] = useState<Record<string, any> | null>(null)
  const [isContinue, setIsContinue] = useState(false)

  // 结果
  const [activeRunId, setActiveRunId] = useState<string>('001')
  const [runResult, setRunResult] = useState<RunResult | null>(null)
  const [resultLoading, setResultLoading] = useState(false)

  // 因子树
  const [selectedFactorIndex, setSelectedFactorIndex] = useState<number | null>(null)
  const [factorDAG, setFactorDAG] = useState<FactorTreeDAG | null>(null)
  const [treeNodes, setTreeNodes, onTreeNodesChange] = useNodesState([])
  const [treeEdges, setTreeEdges, onTreeEdgesChange] = useEdgesState([])

  // 全局配置（参照回测工作台）
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs, dayjs.Dayjs] | null>([
    dayjs().subtract(3, 'year'), dayjs(),
  ])
  const [tradingDayAvailable, setTradingDayAvailable] = useState(false)
  const [dtMode, setDtMode] = useState<'natural' | 'trading'>('natural')

  // 评估配置
  const [evalConfig, setEvalConfig] = useState<EvalPickerValue>({
    modules: [{ module: 'ic', instance_label: '', params: {}, section_mode: 'auto' }],
    transform: 'abs_ic_ir',
    sign: 'greater',
  })

  // 提交状态
  const [submitting, setSubmitting] = useState(false)

  const [form] = Form.useForm()

  const poolItems = useFactorPoolStore((s) => s.items)

  // 导入对话框
  const [importOpen, setImportOpen] = useState(false)
  const [importPath, setImportPath] = useState('')
  const [importing, setImporting] = useState(false)
  const [importedTerminals, setImportedTerminals] = useState<
    { conn_id: string; table_name: string; factor_name: string }[]
  >([])

  const handleImport = async () => {
    if (!importPath.trim()) return
    setImporting(true)
    try {
      const result = await importFactorsFromScript(importPath.trim()) as unknown as {
        terminal_count: number
        terminals: { conn_id: string; table_name: string; factor_name: string }[]
      }
      const terms = result.terminals || []
      setImportedTerminals(terms)

      if (terms.length) {
        // 自动填充到终端因子选择
        const current = form.getFieldValue('terminal_factors') || []
        const existingKeys = new Set(current.map((t: any) =>
          `${t.conn_id}/${t.table_name}/${t.factor_name}`
        ))
        const newTerms = terms.filter((t) =>
          !existingKeys.has(`${t.conn_id}/${t.table_name}/${t.factor_name}`)
        )
        form.setFieldsValue({ terminal_factors: [...current, ...newTerms] })
        message.success(`导入 ${terms.length} 个终端因子`)
      } else {
        message.info('脚本未产生任何终端因子')
      }
    } catch (e: any) {
      message.error('导入失败: ' + (e?.message || '未知错误'))
    } finally {
      setImporting(false)
    }
  }

  // 终端因子级联选择
  const [terminalConns, setTerminalConns] = useState<{ id: string; name: string }[]>([])
  const [terminalConnId, setTerminalConnId] = useState<string | null>(null)
  const [terminalTables, setTerminalTables] = useState<{ name: string }[]>([])
  const [terminalTable, setTerminalTable] = useState<string | null>(null)
  const [terminalFactors, setTerminalFactors] = useState<FactorInfo[]>([])

  // 加载可用的 FactorDB 连接列表（用于终端因子选择）
  useEffect(() => {
    import('../../services/connection').then(({ getConnections }) => {
      getConnections().then((data: any) => {
        const conns = (data || []).map((c: any) => ({ id: c.qsid || c.name, name: c.name }))
        setTerminalConns(conns)
      }).catch(() => {})
    })
  }, [])

  const handleConnChange = async (connId: string) => {
    setTerminalConnId(connId)
    setTerminalTable(null)
    setTerminalFactors([])
    try {
      const tables = await getTables(connId) as unknown as { name: string }[]
      setTerminalTables(tables)
    } catch { setTerminalTables([]) }
  }

  const handleTableChange = async (table: string) => {
    if (!terminalConnId) return
    setTerminalTable(table)
    try {
      const factors = await getFactors(terminalConnId, table) as unknown as FactorInfo[]
      setTerminalFactors(factors)
    } catch { setTerminalFactors([]) }
  }

  // 截面 ID 源列表
  const [sectionSources, setSectionSources] = useState<SectionIdSource[]>([])

  // 加载回测全局配置（交易日可用性 + 截面 ID 源）
  useEffect(() => {
    getBacktestConfig().then((data) => {
      const cfg = data as unknown as { trading_day_available: boolean }
      setTradingDayAvailable(cfg.trading_day_available)
      if (cfg.trading_day_available) setDtMode('trading')
    }).catch(() => {})
    getSectionIdSources().then((data) => {
      setSectionSources(data as unknown as SectionIdSource[])
    }).catch(() => {})
  }, [])

  // 加载框架列表
  useEffect(() => {
    listFrameworks().then((data) => {
      const fws = data as unknown as FrameworkInfo[]
      setFrameworks(fws)
      if (fws.length > 0) {
        handleFrameworkChange(fws[0].key)
      }
    }).catch(() => {})
  }, [])

  // 加载任务列表
  const loadTasks = useCallback(async () => {
    try {
      const data = await listTasks()
      setTasks(data as unknown as MiningTaskSummary[])
    } catch {
      // 静默
    }
  }, [])

  useEffect(() => {
    loadTasks()
  }, [loadTasks])

  // 加载 run 结果
  const loadRunResult = useCallback(async (taskId: string, runId: string) => {
    setResultLoading(true)
    try {
      const result = await getRunResult(taskId, runId) as unknown as RunResult
      setRunResult(result)
    } catch {
      setRunResult(null)
    } finally {
      setResultLoading(false)
    }
  }, [])

  // 加载框架配置（schema，不覆盖表单已有值）
  const loadFrameworkConfig = useCallback(async (key: string) => {
    try {
      const config = await getFrameworkConfig(key) as unknown as Record<string, any>
      setFrameworkConfig(config)
      if (!form.getFieldValue('operators')?.length) {
        form.setFieldsValue({
          operators: config.operators || [],
          ...config.default_params,
        })
      }
    } catch {
      // 静默
    }
  }, [form])

  // 选择任务
  const handleSelectTask = useCallback(async (taskId: string) => {
    setTaskLoading(true)
    try {
      const task = await getTask(taskId) as unknown as MiningTask
      setActiveTask(task)

      // 默认选择最新完成的 run
      const completedRuns = (task.runs || []).filter((r) => r.status === 'completed')
      if (completedRuns.length > 0) {
        setActiveRunId(completedRuns[completedRuns.length - 1].run_id)
        loadRunResult(taskId, completedRuns[completedRuns.length - 1].run_id)
      } else {
        setRunResult(null)
      }

      // 还原配置到表单
      const cfg = task.config
      if (cfg) {
        await loadFrameworkConfig(task.framework)
        // 还原终端因子的级联选择器：取第一个终端因子的 conn/table
        if (cfg.terminal_factors?.length) {
          const first = cfg.terminal_factors[0]
          if (first.conn_id) {
            setTerminalConnId(first.conn_id)
            try {
              const tables = await getTables(first.conn_id) as unknown as { name: string }[]
              setTerminalTables(tables)
              if (first.table_name) {
                setTerminalTable(first.table_name)
                try {
                  const factors = await getFactors(first.conn_id, first.table_name) as unknown as FactorInfo[]
                  setTerminalFactors(factors)
                } catch { /* 静默 */ }
              }
            } catch { /* 静默 */ }
          }
        }
        form.setFieldsValue({
          framework: task.framework,
          operators: cfg.operators || [],
          terminal_factors: cfg.terminal_factors || [],
          seed_factors: (cfg.seed_factors || []).map((sf: any) => {
            const key = `${sf.conn_id}/${sf.table_name}/${sf.factor_name}`
            const existing = poolItems.find((p: any) => p.id === key)
            if (existing) return key
            return undefined
          }).filter(Boolean),
          population_size: cfg.population_size,
          n_generations: cfg.n_generations,
          tournament_size: cfg.tournament_size,
          init_depth: cfg.init_depth ?? [2, 6],
          init_method: cfg.init_method ?? 'half and half',
          const_range: cfg.const_range ?? null,
          p_crossover: cfg.p_crossover,
          p_subtree_mutation: cfg.p_subtree_mutation,
          p_hoist_mutation: cfg.p_hoist_mutation,
          p_point_mutation: cfg.p_point_mutation,
          p_point_replace: cfg.p_point_replace,
          parsimony_coefficient: cfg.parsimony_coefficient,
        })
        if (cfg.start_date) {
          setDateRange([dayjs(cfg.start_date), dayjs(cfg.end_date)])
        }
        if (cfg.dt_mode) {
          setDtMode(cfg.dt_mode as 'natural' | 'trading')
        }
        if (cfg.eval) {
          setEvalConfig({
            modules: cfg.eval.modules || [],
            transform: cfg.eval.transform || 'abs_ic_ir',
            sign: cfg.eval.sign || 'greater',
          })
        }
      } else {
        await loadFrameworkConfig(task.framework)
      }
    } catch {
      message.error('加载任务失败')
    } finally {
      setTaskLoading(false)
    }
  }, [poolItems, form, loadRunResult, loadFrameworkConfig])

  // 加载因子树
  const handleViewFactorTree = useCallback(async (index: number) => {
    if (!activeTask) return
    setSelectedFactorIndex(index)
    try {
      const dag = await getFactorTree(activeTask.task_id, index) as unknown as FactorTreeDAG
      setFactorDAG(dag)

      const nodes: Node[] = (dag.nodes || []).map((n, i) => ({
        id: n.id,
        data: {
          label: (
            <div
              style={{
                padding: '4px 10px',
                borderRadius: 4,
                background: NODE_COLORS[n.type] || '#d9d9d9',
                color: n.type === 'operator' ? '#fff' : '#333',
                fontSize: 12,
                fontWeight: 500,
              }}
            >
              {n.name}
            </div>
          ),
        },
        position: { x: i * 60, y: 0 },
      }))

      const edges: Edge[] = (dag.edges || []).map((e, i) => ({
        id: `e-${i}`,
        source: e.source,
        target: e.target,
        type: 'smoothstep',
        style: { stroke: '#91caff', strokeWidth: 1.5 },
        markerEnd: { type: MarkerType.ArrowClosed, color: '#91caff' },
      }))

      setTreeNodes(nodes)
      setTreeEdges(edges)
    } catch {
      setFactorDAG(null)
    }
  }, [activeTask, setTreeNodes, setTreeEdges])

  // 加载框架配置（触发默认值覆盖）
  const handleFrameworkChange = useCallback(async (key: string) => {
    try {
      const config = await getFrameworkConfig(key) as unknown as Record<string, any>
      setFrameworkConfig(config)
      form.setFieldsValue({
        operators: config.operators || [],
        ...config.default_params,
      })
      setEvalConfig({
        modules: config.default_eval?.modules || [{ module: 'ic', instance_label: '', params: {}, section_mode: 'auto' }],
        transform: config.default_eval?.transform || 'abs_ic_ir',
        sign: config.default_eval?.sign || 'greater',
      })
    } catch {
      // 静默
    }
  }, [form])

  // 新建任务
  const handleNewTask = useCallback(() => {
    setActiveTask(null)
    setRunResult(null)
    setFactorDAG(null)
    setFrameworkConfig(null)
    setIsContinue(false)
    setEvalConfig({
      modules: [{ module: 'ic', instance_label: '', params: {}, section_mode: 'auto' }],
      transform: 'abs_ic_ir',
      sign: 'greater',
    })
    setDateRange([dayjs().subtract(3, 'year'), dayjs()])
    setDtMode(tradingDayAvailable ? 'trading' : 'natural')
    form.resetFields()
    // resetFields 后恢复框架配置的默认值
    if (frameworkConfig) {
      form.setFieldsValue({
        operators: frameworkConfig.operators || [],
        ...frameworkConfig.default_params,
      })
    }
  }, [form, tradingDayAvailable, frameworkConfig])

  // 接续挖掘
  const handleContinue = useCallback(() => {
    setIsContinue(true)
    // 保留之前的配置在表单中
  }, [])

  // 提交
  const handleSubmit = useCallback(async () => {
    try {
      const values = await form.validateFields()
      setSubmitting(true)

      // 构建配置
      // 解析种子因子为 TerminalFactorRef 格式
      const seedFactors = (values.seed_factors || []).map((id: string) => {
        const item = poolItems.find((p: any) => p.id === id)
        return {
          conn_id: item?.ref?.conn_id || '',
          table_name: item?.ref?.table_name || '',
          factor_name: item?.ref?.factor_name || '',
        }
      })

      const config: GPRunConfig = {
        operators: values.operators || [],
        terminal_factors: values.terminal_factors || [],
        seed_factors: seedFactors,
        population_size: values.population_size ?? 20,
        n_generations: values.n_generations ?? 20,
        tournament_size: values.tournament_size ?? 20,
        init_depth: values.init_depth ?? [2, 6],
        init_method: values.init_method ?? 'half and half',
        const_range: values.const_range ?? null,
        p_crossover: values.p_crossover ?? 0.9,
        p_subtree_mutation: values.p_subtree_mutation ?? 0.01,
        p_hoist_mutation: values.p_hoist_mutation ?? 0.01,
        p_point_mutation: values.p_point_mutation ?? 0.01,
        p_point_replace: values.p_point_replace ?? 0.05,
        parsimony_coefficient: values.parsimony_coefficient ?? 0.0,
        start_date: dateRange?.[0]?.format('YYYY-MM-DD') || null,
        end_date: dateRange?.[1]?.format('YYYY-MM-DD') || null,
        dt_mode: dtMode,
        eval: {
          modules: evalConfig.modules,
          transform: evalConfig.transform || 'abs',
          sign: evalConfig.sign || 'greater',
        },
      }

      let targetTaskId: string

      if (!activeTask) {
        // 新建任务
        const task = await createTask({
          name: values.task_name || '挖掘任务',
          framework: values.framework || 'gp',
        }) as unknown as MiningTask
        targetTaskId = task.task_id
        setActiveTask(task)
        await submitRun(task.task_id, config)
      } else if (isContinue) {
        targetTaskId = activeTask.task_id
        await continueMining(activeTask.task_id, config)
      }

      // 运行完成后刷新任务详情（状态、runs 等已更新）
      if (targetTaskId!) {
        const updated = await getTask(targetTaskId) as unknown as MiningTask
        setActiveTask(updated)
      }

      message.success('挖掘任务已提交')
      setSubmitting(false)
      setIsContinue(false)
      loadTasks()
    } catch {
      message.error('提交失败，请检查配置')
      setSubmitting(false)
    }
  }, [form, activeTask, isContinue, loadTasks, evalConfig, dateRange, dtMode, poolItems])

  // 导出
  const handleExport = useCallback(async () => {
    if (!activeTask) return
    try {
      const result = await exportFactor(activeTask.task_id)
      message.success((result as unknown as { message: string }).message)
    } catch {
      message.error('导出失败')
    }
  }, [activeTask])

  // 删除任务
  const handleDeleteTask = useCallback(async (taskId: string) => {
    try {
      await deleteTask(taskId)
      if (activeTask?.task_id === taskId) {
        handleNewTask()
      }
      message.success('已删除')
      loadTasks()
    } catch {
      message.error('删除失败')
    }
  }, [activeTask, handleNewTask, loadTasks])

  // Hall of Fame 表格列
  const hofColumns = [
    { title: '排名', dataIndex: 'rank', key: 'rank', width: 60 },
    { title: '适应度', dataIndex: 'fitness', key: 'fitness', width: 100, render: (v: number) => v.toFixed(6) },
    { title: '表达式', dataIndex: 'expression', key: 'expression', ellipsis: true },
    {
      title: '操作',
      key: 'action',
      width: 80,
      render: (_: any, _record: HallOfFameEntry, idx: number) => (
        <Button size="small" type="link" onClick={() => handleViewFactorTree(idx)}>
          查看
        </Button>
      ),
    },
  ]

  return (
    <Layout style={{ height: 'calc(100vh - 160px)', background: '#fff' }}>
      {/* 左侧：任务列表 */}
      <Sider
        width={260}
        style={{
          background: '#fafafa',
          borderRight: '1px solid #f0f0f0',
          overflow: 'hidden',
        }}
      >
        <div style={{ padding: '12px 16px', borderBottom: '1px solid #f0f0f0' }}>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            block
            onClick={handleNewTask}
          >
            新建任务
          </Button>
        </div>
        <List
          style={{ overflow: 'auto', height: 'calc(100% - 53px)' }}
          dataSource={tasks}
          renderItem={(task) => (
            <List.Item
              onClick={() => handleSelectTask(task.task_id)}
              style={{
                cursor: 'pointer',
                padding: '8px 16px',
                background: activeTask?.task_id === task.task_id ? '#e6f4ff' : undefined,
              }}
            >
              <List.Item.Meta
                title={
                  <Space size={4}>
                    <Tag
                      color={
                        task.status === 'running'
                          ? 'processing'
                          : task.status === 'completed'
                            ? 'success'
                            : task.status === 'failed'
                              ? 'error'
                              : 'default'
                      }
                      style={{ fontSize: 10, lineHeight: '16px' }}
                    >
                      {task.status === 'running'
                        ? '运行中'
                        : task.status === 'completed'
                          ? '已完成'
                          : task.status === 'failed'
                            ? '失败'
                            : '等待中'}
                    </Tag>
                    {task.name}
                  </Space>
                }
                description={
                  <Space size={4}>
                    <span style={{ fontSize: 11 }}>{task.framework}</span>
                    <span style={{ fontSize: 11, color: '#999' }}>
                      {task.current_run} runs
                    </span>
                  </Space>
                }
              />
              <Popconfirm
                title="确定删除？"
                onConfirm={(e) => {
                  e?.stopPropagation()
                  handleDeleteTask(task.task_id)
                }}
                onCancel={(e) => e?.stopPropagation()}
              >
                <Button
                  type="link"
                  danger
                  size="small"
                  icon={<DeleteOutlined />}
                  onClick={(e) => e.stopPropagation()}
                />
              </Popconfirm>
            </List.Item>
          )}
          locale={{ emptyText: <Empty description="暂无任务，点击上方新建" image={Empty.PRESENTED_IMAGE_SIMPLE} /> }}
        />
      </Sider>

      {/* 右侧：内容 */}
      <Content style={{ padding: '16px 24px', overflow: 'auto' }}>
        <Tabs
          items={[
            {
              key: 'config',
              label: '配置',
              children: (
                <Form
                  form={form}
                  layout="vertical"
                  style={{ maxWidth: 760 }}
                  initialValues={{
                    framework: 'gp',
                    init_method: 'half and half',
                    population_size: frameworkConfig?.default_params?.population_size ?? 20,
                    n_generations: frameworkConfig?.default_params?.n_generations ?? 20,
                    tournament_size: frameworkConfig?.default_params?.tournament_size ?? 20,
                    init_depth: frameworkConfig?.default_params?.init_depth ?? [2, 6],
                    const_range: frameworkConfig?.default_params?.const_range ?? [-1.0, 1.0],
                    p_crossover: frameworkConfig?.default_params?.p_crossover ?? 0.9,
                    p_subtree_mutation: frameworkConfig?.default_params?.p_subtree_mutation ?? 0.01,
                    p_hoist_mutation: frameworkConfig?.default_params?.p_hoist_mutation ?? 0.01,
                    p_point_mutation: frameworkConfig?.default_params?.p_point_mutation ?? 0.01,
                    p_point_replace: frameworkConfig?.default_params?.p_point_replace ?? 0.05,
                    parsimony_coefficient: frameworkConfig?.default_params?.parsimony_coefficient ?? 0.0,
                  }}
                >
                  <Form.Item label="任务名称" name="task_name" hidden={!!activeTask && !isContinue}>
                    <Input placeholder="给任务起个名字" />
                  </Form.Item>

                  <Form.Item label="挖掘框架" name="framework" initialValue={frameworks[0]?.key || 'gp'}>
                    <Select
                      onChange={handleFrameworkChange}
                      disabled={!!activeTask && !isContinue}
                      options={frameworks.map((f) => ({
                        value: f.key,
                        label: f.name,
                      }))}
                    />
                  </Form.Item>

                  <Form.Item label="算子" name="operators">
                    <Select
                      mode="multiple"
                      placeholder="选择算子"
                      disabled={isContinue}
                      options={
                        frameworkConfig?.operators?.map((op: string) => ({
                          value: op,
                          label: op,
                        })) || []
                      }
                    />
                  </Form.Item>

                  <Card title="终端因子" size="small" style={{ marginBottom: 12 }}>
                    <Space direction="vertical" style={{ width: '100%' }}>
                      <Select
                        style={{ width: '100%' }}
                        placeholder="选择因子库"
                        onChange={handleConnChange}
                        disabled={isContinue}
                        allowClear
                        options={terminalConns.map((c) => ({ value: c.id, label: c.name }))}
                      />
                      <Select
                        style={{ width: '100%' }}
                        placeholder="选择因子表"
                        value={terminalTable}
                        onChange={handleTableChange}
                        disabled={isContinue || !terminalConnId}
                        allowClear
                        options={terminalTables.map((t) => ({ value: t.name, label: t.name }))}
                      />
                      <Form.Item
                        name="terminal_factors"
                        noStyle
                        getValueFromEvent={(names: string[]) =>
                          names.map((name) => ({
                            conn_id: terminalConnId || '',
                            table_name: terminalTable || '',
                            factor_name: name,
                          }))
                        }
                        getValueProps={(refs: any[]) => ({
                          value: (refs || []).map((r: any) =>
                            typeof r === 'string' ? r : r?.factor_name || ''
                          ),
                        })}
                      >
                        <Select
                          mode="multiple"
                          placeholder="选择终端因子"
                          disabled={isContinue || !terminalTable}
                          dropdownMatchSelectWidth={false}
                          style={{ width: '100%' }}
                          options={terminalFactors.map((f) => ({
                            value: f.name,
                            label: f.name,
                          }))}
                          optionFilterProp="label"
                          showSearch
                        />
                      </Form.Item>
                    </Space>
                  </Card>

                  <Row gutter={12} style={{ marginBottom: 12 }}>
                    <Col span={12}>
                      <Form.Item label="种子因子（可选）" name="seed_factors" style={{ marginBottom: 0 }}>
                        <Select
                          mode="multiple"
                          placeholder="从全局因子池选择"
                          options={poolItems.map((item) => ({
                            value: item.id,
                            label: `${item.label} (${item.ref?.factor_name || ''})`,
                          }))}
                          optionFilterProp="label"
                          showSearch
                          notFoundContent={
                            <Empty description="因子池为空" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                          }
                        />
                      </Form.Item>
                    </Col>
                    <Col span={12}>
                      <Form.Item label="导入因子定义脚本" style={{ marginBottom: 0 }}>
                        <Button
                          icon={<ImportOutlined />}
                          onClick={() => setImportOpen(true)}
                          disabled={isContinue}
                        >
                          从脚本导入
                        </Button>
                      </Form.Item>
                    </Col>
                  </Row>

                  <Card title="GP 参数" size="small" style={{ marginBottom: 12 }}>
                    <Row gutter={[16, 0]}>
                      <Col span={12}>
                        <Form.Item label="种群大小" name="population_size">
                          <InputNumber min={10} max={100000} style={{ width: '100%' }} />
                        </Form.Item>
                      </Col>
                      <Col span={12}>
                        <Form.Item label="进化代数" name="n_generations">
                          <InputNumber min={1} max={1000} style={{ width: '100%' }} />
                        </Form.Item>
                      </Col>
                      <Col span={12}>
                        <Form.Item label="锦标赛大小" name="tournament_size">
                          <InputNumber min={2} style={{ width: '100%' }} />
                        </Form.Item>
                      </Col>
                      <Col span={12}>
                        <Form.Item label="初始深度范围" style={{ marginBottom: 0 }}>
                          <Space>
                            <Form.Item name={['init_depth', 0]} noStyle>
                              <InputNumber min={1} max={20} placeholder="最小" />
                            </Form.Item>
                            <span>—</span>
                            <Form.Item name={['init_depth', 1]} noStyle>
                              <InputNumber min={1} max={20} placeholder="最大" />
                            </Form.Item>
                          </Space>
                        </Form.Item>
                      </Col>
                      <Col span={12}>
                        <Form.Item label="交叉概率" name="p_crossover">
                          <InputNumber min={0} max={1} step={0.01} style={{ width: '100%' }} />
                        </Form.Item>
                      </Col>
                      <Col span={12}>
                        <Form.Item label="子树变异概率" name="p_subtree_mutation">
                          <InputNumber min={0} max={1} step={0.01} style={{ width: '100%' }} />
                        </Form.Item>
                      </Col>
                      <Col span={12}>
                        <Form.Item label="提升变异概率" name="p_hoist_mutation">
                          <InputNumber min={0} max={1} step={0.01} style={{ width: '100%' }} />
                        </Form.Item>
                      </Col>
                      <Col span={12}>
                        <Form.Item label="点变异概率" name="p_point_mutation">
                          <InputNumber min={0} max={1} step={0.01} style={{ width: '100%' }} />
                        </Form.Item>
                      </Col>
                      <Col span={12}>
                        <Form.Item label="复杂度惩罚系数" name="parsimony_coefficient">
                          <InputNumber min={0} step={0.01} style={{ width: '100%' }} />
                        </Form.Item>
                      </Col>
                    </Row>
                  </Card>

                  <Card title="评估配置" size="small" style={{ marginBottom: 12 }}>
                    <Row gutter={[16, 8]}>
                      <Col span={12}>
                        <div style={{ marginBottom: 4, fontSize: 12, color: '#666' }}>日期范围</div>
                        <RangePicker
                          style={{ width: '100%' }}
                          value={dateRange}
                          onChange={(dates) => setDateRange(dates as [dayjs.Dayjs, dayjs.Dayjs])}
                          disabled={isContinue}
                        />
                      </Col>
                      <Col span={12}>
                        <div style={{ marginBottom: 4, fontSize: 12, color: '#666' }}>
                          时点模式
                          {!tradingDayAvailable && (
                            <Tooltip title="交易日源未配置，请在 QSWebConfig.yaml 的 backtest.trading_day_source 中配置">
                              <InfoCircleOutlined style={{ marginLeft: 6, color: '#faad14' }} />
                            </Tooltip>
                          )}
                        </div>
                        <Radio.Group
                          value={dtMode}
                          onChange={(e) => setDtMode(e.target.value)}
                          optionType="button"
                          size="small"
                          disabled={isContinue}
                        >
                          <Radio.Button value="natural">自然日</Radio.Button>
                          <Radio.Button value="trading" disabled={!tradingDayAvailable}>交易日</Radio.Button>
                        </Radio.Group>
                      </Col>
                    </Row>
                    <div style={{ marginTop: 12 }}>
                      <EvalModulePicker
                        disabled={isContinue}
                        value={evalConfig}
                        onChange={setEvalConfig}
                        sectionSources={sectionSources}
                      />
                    </div>
                  </Card>

                  <Form.Item>
                    <Button
                      type="primary"
                      icon={<RocketOutlined />}
                      loading={submitting}
                      onClick={handleSubmit}
                    >
                      {activeTask ? (isContinue ? '接续挖掘' : '开始挖掘') : '创建并开始挖掘'}
                    </Button>
                    {activeTask && activeTask.runs.some((r) => r.status === 'completed') && (
                      <Button
                        style={{ marginLeft: 8 }}
                        onClick={handleContinue}
                      >
                        接续挖掘
                      </Button>
                    )}
                  </Form.Item>
                </Form>
              ),
            },
            {
              key: 'result',
              label: '结果',
              children: (
                <div>
                  {/* Run 选择器 */}
                  {activeTask && (activeTask.runs || []).length > 0 && (
                    <Space style={{ marginBottom: 16 }}>
                      <span>Run:</span>
                      {(activeTask.runs || []).map((r) => (
                        <Tag
                          key={r.run_id}
                          color={activeRunId === r.run_id ? 'blue' : 'default'}
                          style={{ cursor: 'pointer' }}
                          onClick={() => {
                            setActiveRunId(r.run_id)
                            if (r.status === 'completed') {
                              loadRunResult(activeTask.task_id, r.run_id)
                            }
                          }}
                        >
                          {r.run_id} ({r.status === 'completed' ? '完成' : r.status})
                        </Tag>
                      ))}
                    </Space>
                  )}

                  {runResult ? (
                    <>
                      {/* 运行信息 */}
                      {activeTask && (
                        <div style={{ marginBottom: 16, padding: '8px 12px', background: '#f6f8fa', borderRadius: 6, fontSize: 13 }}>
                          <Space wrap size={[16, 4]}>
                            <span>代数: <b>{runResult.gen_start} – {runResult.gen_end}</b></span>
                            {(() => {
                              const run = (activeTask.runs || []).find((r) => r.run_id === activeRunId)
                              return run ? (
                                <>
                                  <span>开始: {run.started_at ? new Date(run.started_at).toLocaleString() : '-'}</span>
                                  <span>完成: {run.completed_at ? new Date(run.completed_at).toLocaleString() : '-'}</span>
                                </>
                              ) : null
                            })()}
                          </Space>
                        </div>
                      )}

                      {/* 错误信息（失败时） */}
                      {runResult.hall_of_fame?.length === 0 && activeTask && (() => {
                        const run = (activeTask.runs || []).find((r) => r.run_id === activeRunId)
                        if (run?.status === 'failed') return null // 由下方错误显示处理
                        return null
                      })()}

                      {/* 失败 Runs 的错误信息 */}
                      {(activeTask?.runs || []).filter((r) => r.status === 'failed').length > 0 && (
                        <div style={{ marginBottom: 16, padding: '8px 12px', background: '#fff2f0', borderRadius: 6, border: '1px solid #ffccc7' }}>
                          <div style={{ fontWeight: 500, color: '#cf1322', marginBottom: 4 }}>运行失败</div>
                          {(activeTask?.runs || []).filter((r) => r.status === 'failed').map((r) => (
                            <div key={r.run_id} style={{ fontSize: 12, color: '#666', marginBottom: 4 }}>
                              <b>{r.run_id}</b>: {((r as any).error) || '未知错误'}
                            </div>
                          ))}
                        </div>
                      )}

                      {/* Hall of Fame */}
                      {runResult.hall_of_fame?.length > 0 && (
                        <>
                          <h4>Hall of Fame</h4>
                          <Table
                            columns={hofColumns}
                            dataSource={runResult.hall_of_fame || []}
                            rowKey="rank"
                            size="small"
                            pagination={false}
                            style={{ marginBottom: 16 }}
                          />

                          {/* 导出按钮 */}
                          <Space style={{ marginBottom: 16 }}>
                            <Button icon={<ExportOutlined />} onClick={handleExport}>
                              导出因子脚本
                            </Button>
                          </Space>
                        </>
                      )}

                      {/* 适应度曲线 */}
                      {runResult.fitness_history?.gen_best?.length > 0 && (
                        <>
                          <h4>适应度进化曲线</h4>
                          <FitnessChart data={runResult.fitness_history} />
                        </>
                      )}
                    </>
                  ) : (
                    <Empty description="选择已完成的任务查看结果" />
                  )}
                </div>
              ),
            },
            {
              key: 'factorTree',
              label: '因子树',
              children: (
                <div style={{ height: 500 }}>
                  {factorDAG ? (
                    <ReactFlow
                      nodes={treeNodes}
                      edges={treeEdges}
                      onNodesChange={onTreeNodesChange}
                      onEdgesChange={onTreeEdgesChange}
                      fitView
                    >
                      <Background />
                      <Controls />
                    </ReactFlow>
                  ) : (
                    <Empty description="点击 Hall of Fame 中的'查看'来查看因子树" />
                  )}
                </div>
              ),
            },
          ]}
        />
      </Content>

      {/* 导入因子定义脚本对话框 */}
      <Modal
        title="从因子定义脚本导入终端因子"
        open={importOpen}
        onOk={handleImport}
        onCancel={() => { setImportOpen(false); setImportedTerminals([]) }}
        confirmLoading={importing}
        okText="导入"
        cancelText="取消"
      >
        <div style={{ marginBottom: 12 }}>
          <Input
            placeholder="输入因子定义脚本路径，如 D:/FactorDef/Scripts/my_factor.py"
            value={importPath}
            onChange={(e) => setImportPath(e.target.value)}
            onPressEnter={handleImport}
          />
        </div>
        {importedTerminals.length > 0 && (
          <div>
            <div style={{ marginBottom: 8, fontWeight: 500 }}>
              已导入 {importedTerminals.length} 个终端因子:
            </div>
            <List
              size="small"
              dataSource={importedTerminals}
              renderItem={(item) => (
                <List.Item>
                  <Space>
                    <Tag color="blue">{item.factor_name}</Tag>
                    <span style={{ fontSize: 12, color: '#666' }}>
                      {item.conn_id}/{item.table_name}
                    </span>
                  </Space>
                </List.Item>
              )}
            />
          </div>
        )}
      </Modal>
    </Layout>
  )
}

export default MiningStudio
