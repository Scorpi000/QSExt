/**
 * 策略工作台页面 —— 策略开发、调试和回测的一站式工作台
 *
 * 布局：左右分栏
 *   左侧：策略列表 + 配置面板
 *   右侧：Tab 切换（策略代码 | 回测结果）
 */
import React, { useState, useCallback } from 'react'
import { Layout, Tabs } from 'antd'
import { CodeOutlined, BarChartOutlined } from '@ant-design/icons'
import StrategyList from './StrategyList'
import StrategyEditor from './StrategyEditor'
import StrategyConfig from './StrategyConfig'
import StrategyResult from './StrategyResult'
import type { StrategySearchResult, OperatorConfig, FactorRef } from '../../services/strategy'

const { Sider, Content } = Layout

const StrategyStudio: React.FC = () => {
  // 当前选中的策略
  const [selectedStrategy, setSelectedStrategy] = useState<StrategySearchResult | null>(null)
  // 编辑器代码
  const [code, setCode] = useState<string>('')
  // OperatorConfig
  const [operatorConfig, setOperatorConfig] = useState<OperatorConfig>({
    SignalType: '目标权重',
    InitCash: 1e6,
    ShortAllowed: false,
  })
  // 因子依赖
  const [factorRefs, setFactorRefs] = useState<FactorRef[]>([])
  // 模型参数
  const [modelArgs, setModelArgs] = useState<Record<string, any>>({})
  // 回测 taskId
  const [taskId, setTaskId] = useState<string | null>(null)
  // 右侧 Tab
  const [activeTab, setActiveTab] = useState<string>('code')
  // 日期范围
  const [startDate, setStartDate] = useState<string>('2024-01-01')
  const [endDate, setEndDate] = useState<string>('2025-12-31')
  // 编辑模式（新建 or 编辑已有）
  const [isNew, setIsNew] = useState<boolean>(false)

  // 选择策略
  const handleSelectStrategy = useCallback(async (strategy: StrategySearchResult | null) => {
    if (!strategy) {
      // 新建策略
      setSelectedStrategy(null)
      try {
        const { getStrategyTemplate } = await import('../../services/strategy')
        const res = await getStrategyTemplate()
        setCode(res.code)
      } catch {
        setCode('# 无法加载策略模板')
      }
      setIsNew(true)
      return
    }

    setIsNew(false)
    setSelectedStrategy(strategy)

    // 加载策略代码
    try {
      const { getStrategyCode } = await import('../../services/strategy')
      const result = await getStrategyCode(strategy.QSID)
      setCode(result.code)
    } catch {
      setCode(`# 无法加载策略代码: ${strategy.QSID}`)
    }
  }, [])

  // 运行回测
  const handleRunBacktest = useCallback(async () => {
    const { submitStrategyBacktest } = await import('../../services/strategy')
    const result = await submitStrategyBacktest({
      code,
      factor_refs: factorRefs,
      model_args: modelArgs,
      operator_config: operatorConfig,
      start_date: startDate,
      end_date: endDate,
      dt_mode: 'natural',
    })
    setTaskId(result.task_id)
    setActiveTab('code')  // 运行中保持在代码 Tab
  }, [code, factorRefs, modelArgs, operatorConfig, startDate, endDate])

  // 回测结果就绪时切换到结果 Tab
  const handleResultReady = useCallback(() => {
    setActiveTab('result')
  }, [])

  // 左侧面板
  const leftPanel = (
    <div style={{ padding: '12px', height: '100%', overflow: 'auto' }}>
      <StrategyList
        selectedQSID={selectedStrategy?.QSID ?? null}
        onSelect={handleSelectStrategy}
      />
      {selectedStrategy && !isNew && (
        <StrategyConfig
          operatorConfig={operatorConfig}
          factorRefs={factorRefs}
          modelArgs={modelArgs}
          startDate={startDate}
          endDate={endDate}
          onOperatorConfigChange={setOperatorConfig}
          onFactorRefsChange={setFactorRefs}
          onModelArgsChange={setModelArgs}
          onStartDateChange={setStartDate}
          onEndDateChange={setEndDate}
          onRunBacktest={handleRunBacktest}
        />
      )}
    </div>
  )

  // Tab 内容容器高度（Sider + Header 约 160px）
  const tabContentStyle: React.CSSProperties = {
    height: 'calc(100vh - 200px)',
    minHeight: 300,
    overflow: 'hidden',
  }

  // 右侧 Tab 项
  const tabItems = [
    {
      key: 'code',
      label: (
        <span><CodeOutlined />策略代码</span>
      ),
      children: (
        <div style={tabContentStyle}>
          <StrategyEditor
            code={code}
            onChange={setCode}
            isNew={isNew}
            selectedStrategy={selectedStrategy}
          />
        </div>
      ),
    },
  ]

  if (taskId) {
    tabItems.push({
      key: 'result',
      label: (
        <span><BarChartOutlined />回测结果</span>
      ),
      children: (
        <div style={{ ...tabContentStyle, overflow: 'auto' }}>
          <StrategyResult taskId={taskId} onResultReady={handleResultReady} />
        </div>
      ),
    })
  }

  return (
    <Layout style={{ height: '100%' }}>
      <Sider
        width={360}
        style={{
          background: '#fff',
          borderRight: '1px solid #f0f0f0',
          overflow: 'auto',
        }}
      >
        {leftPanel}
      </Sider>
      <Content style={{ background: '#fff', padding: '0 12px' }}>
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={tabItems}
          tabBarStyle={{ marginBottom: 8 }}
        />
      </Content>
    </Layout>
  )
}

export default StrategyStudio
