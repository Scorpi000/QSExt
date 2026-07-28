/**
 * BacktestStudio - 回测工作台页面
 *
 * 左侧：配置区（全局因子池 + 全局价格因子池 + 日期/时点 + 模块选择 + 运行按钮）
 * 右侧：结果区（结果树 + 叶子节点详情）
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import {
  Row, Col, Card, Button, DatePicker, Radio, Space, Tooltip, message,
} from 'antd'
import { PlayCircleOutlined, ReloadOutlined, InfoCircleOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import type { ModuleInfo, ModuleRunConfig, ResultNode, BacktestRunRequest, FactorRef, SectionIdSource } from '../../services/backtest'
import { getBacktestModules, getBacktestConfig, getSectionIdSources, submitBacktestRun, getBacktestResult } from '../../services/backtest'
import { useTaskProgress } from '../../hooks/useTaskProgress'
import TaskProgress from '../../components/TaskProgress'
import ModulePicker from '../../components/ModulePicker'
import ModuleList from '../../components/ModuleList'
import ResultTree from '../../components/ResultTree'
import ResultLeaf from '../../components/ResultLeaf'
import FactorSelector from '../../components/FactorSelector'

const { RangePicker } = DatePicker

function BacktestStudio() {
  // ─── 全局因子池 ───────────────────────────────────────────
  const [globalFactors, setGlobalFactors] = useState<FactorRef[]>([])

  // ─── 全局配置 ─────────────────────────────────────────────
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs, dayjs.Dayjs] | null>(
    [dayjs().subtract(3, 'year'), dayjs()]
  )
  const [tradingDayAvailable, setTradingDayAvailable] = useState(false)
  const [dtMode, setDtMode] = useState<'natural' | 'trading'>('natural')
  const [sectionSources, setSectionSources] = useState<SectionIdSource[]>([])

  // ─── 模块列表 ─────────────────────────────────────────────
  const [modules, setModules] = useState<ModuleInfo[]>([])
  const [moduleConfigs, setModuleConfigs] = useState<ModuleRunConfig[]>([])

  // ─── 运行状态 ─────────────────────────────────────────────
  const [taskId, setTaskId] = useState<string | null>(null)
  const { task } = useTaskProgress(taskId)
  const [resultTree, setResultTree] = useState<ResultNode | null>(null)
  const [selectedLeaf, setSelectedLeaf] = useState<ResultNode | null>(null)
  const [isRunning, setIsRunning] = useState(false)

  // ─── 加载 ─────────────────────────────────────────────────
  const loadModules = useCallback(async () => {
    try {
      const data = await getBacktestModules()
      setModules(data as unknown as ModuleInfo[])
    } catch { /* handled */ }
  }, [])

  useEffect(() => {
    loadModules()
    getBacktestConfig().then((data) => {
      const cfg = data as unknown as { trading_day_available: boolean; section_id_sources: string[] }
      setTradingDayAvailable(cfg.trading_day_available)
      setDtMode(cfg.trading_day_available ? 'trading' : 'natural')
    }).catch(() => {})
    getSectionIdSources().then((data) => {
      setSectionSources(data as unknown as SectionIdSource[])
    }).catch(() => {})
  }, [loadModules])

  // ─── 模块管理 ─────────────────────────────────────────────
  const handleAddModule = (config: ModuleRunConfig) => {
    setModuleConfigs([...moduleConfigs, config])
    message.success(`已添加模块: ${config.instance_label || config.module_key}`)
  }

  const handleEditModule = (index: number) => {
    const cfg = moduleConfigs[index]
    const newConfigs = [...moduleConfigs]
    newConfigs.splice(index, 1)
    setModuleConfigs(newConfigs)
    message.info(`已移除 "${cfg.instance_label || cfg.module_key}"，请重新添加并配置`)
  }

  const handleDeleteModule = (index: number) => {
    const newConfigs = [...moduleConfigs]
    newConfigs.splice(index, 1)
    setModuleConfigs(newConfigs)
  }

  // ─── 运行回测 ─────────────────────────────────────────────
  const handleRun = async () => {
    if (moduleConfigs.length === 0) { message.warning('请至少添加一个回测模块'); return }
    if (!dateRange) { message.warning('请选择日期范围'); return }

    setResultTree(null)
    setSelectedLeaf(null)
    setIsRunning(true)

    const request: BacktestRunRequest = {
      module_configs: moduleConfigs,
      start_date: dateRange[0].format('YYYY-MM-DD'),
      end_date: dateRange[1].format('YYYY-MM-DD'),
      dt_mode: dtMode,
    }

    try {
      const resp = await submitBacktestRun(request)
      const data = resp as unknown as { task_id: string }
      setTaskId(data.task_id)
    } catch { setIsRunning(false) }
  }

  // ─── 轮询结果 ─────────────────────────────────────────────
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (!taskId) return

    pollTimerRef.current = setInterval(async () => {
      try {
        const result = await getBacktestResult(taskId)
        const data = result as unknown as Record<string, any>
        if (data && data.type) {
          setResultTree(data as unknown as ResultNode)
          setIsRunning(false)
          if (pollTimerRef.current) { clearInterval(pollTimerRef.current); pollTimerRef.current = null }
        }
      } catch { /* 继续轮询 */ }
    }, 2000)

    return () => {
      if (pollTimerRef.current) { clearInterval(pollTimerRef.current); pollTimerRef.current = null }
    }
  }, [taskId])

  // ─── WebSocket 失败处理 ───────────────────────────────────
  useEffect(() => {
    if (task && task.status === 'failed') {
      message.error(`回测失败: ${task.error || '未知错误'}`)
      setIsRunning(false)
    }
    if (task && task.status === 'completed') {
      setIsRunning(false)
    }
  }, [task])

  // ─── 渲染 ─────────────────────────────────────────────────
  return (
    <Row gutter={16} style={{ height: 'calc(100vh - 160px)' }}>
      <Col span={10} style={{ height: '100%', overflow: 'auto' }}>

        {/* 全局因子池 */}
        <Card title="全局因子池" size="small" style={{ marginBottom: 12 }}>
          <FactorSelector selected={globalFactors} onChange={setGlobalFactors} />
        </Card>

        {/* 全局配置 */}
        <Card title="全局配置" size="small" style={{ marginBottom: 12 }}>
          <div style={{ marginBottom: 12 }}>
            <div style={{ marginBottom: 4, fontSize: 12, color: '#666' }}>日期范围</div>
            <RangePicker style={{ width: '100%' }} value={dateRange}
              onChange={(dates) => setDateRange(dates as [dayjs.Dayjs, dayjs.Dayjs])} />
          </div>
          <div>
            <div style={{ marginBottom: 4, fontSize: 12, color: '#666' }}>
              时点模式
              {!tradingDayAvailable && (
                <Tooltip title="交易日源未配置，请在 QSWebConfig.json 的 backtest.trading_day_source 中配置">
                  <InfoCircleOutlined style={{ marginLeft: 6, color: '#faad14' }} />
                </Tooltip>
              )}
            </div>
            <Radio.Group value={dtMode} onChange={(e) => setDtMode(e.target.value)}
              optionType="button" size="small">
              <Radio.Button value="natural">自然日</Radio.Button>
              <Radio.Button value="trading" disabled={!tradingDayAvailable}>交易日</Radio.Button>
            </Radio.Group>
            {!tradingDayAvailable && (
              <div style={{ marginTop: 4, fontSize: 11, color: '#999' }}>
                配置文件中未设置交易日源，仅支持自然日模式
              </div>
            )}
          </div>
        </Card>

        {/* 模块 */}
        <Card title="回测模块" size="small" style={{ marginBottom: 12 }}
          extra={<Button size="small" icon={<ReloadOutlined />} onClick={loadModules} />}>
          <div style={{ marginBottom: 12 }}>
            <ModulePicker
              onAdd={handleAddModule}
              globalFactors={globalFactors}
              sectionSources={sectionSources}
            />
          </div>
          <ModuleList configs={moduleConfigs} moduleInfos={modules}
            onEdit={handleEditModule} onDelete={handleDeleteModule} />
        </Card>

        {/* 运行 */}
        <Card size="small">
          <Space direction="vertical" style={{ width: '100%' }}>
            <Button type="primary" size="large" icon={<PlayCircleOutlined />}
              onClick={handleRun} disabled={isRunning} block>
              {isRunning ? '运行中...' : '全部运行'}
            </Button>
            <TaskProgress task={task} width={undefined} showName />
          </Space>
        </Card>
      </Col>

      {/* 结果区 */}
      <Col span={14} style={{ height: '100%' }}>
        <Row gutter={8} style={{ height: '100%' }}>
          <Col span={8} style={{ height: '100%' }}>
            <Card title="结果树" size="small" style={{ height: '100%' }}
              bodyStyle={{ padding: 8, height: 'calc(100% - 46px)', overflow: 'auto' }}>
              {resultTree
                ? <ResultTree data={resultTree} onSelect={setSelectedLeaf} />
                : <div style={{ textAlign: 'center', padding: 32, color: '#ccc', fontSize: 13 }}>运行回测后在此查看结果</div>}
            </Card>
          </Col>
          <Col span={16} style={{ height: '100%' }}>
            <Card title={selectedLeaf ? selectedLeaf.label : '结果详情'} size="small" style={{ height: '100%' }}
              bodyStyle={{ padding: 12, height: 'calc(100% - 46px)', overflow: 'auto' }}>
              <ResultLeaf node={selectedLeaf} />
            </Card>
          </Col>
        </Row>
      </Col>
    </Row>
  )
}

export default BacktestStudio
