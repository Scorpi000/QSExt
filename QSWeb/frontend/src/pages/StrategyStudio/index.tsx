/**
 * 策略工作台页面 —— 策略开发、调试和回测的一站式工作台
 *
 * 布局：左右分栏
 *   左侧：策略列表 + 配置面板
 *   右侧：代码编辑器 + 回测结果
 */
import React, { useState, useCallback } from 'react'
import { Layout, Row, Col, Tabs } from 'antd'
import { CodeOutlined, SettingOutlined, BarChartOutlined } from '@ant-design/icons'
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
      setCode(DEFAULT_TEMPLATE)
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
  }, [code, factorRefs, modelArgs, operatorConfig, startDate, endDate])

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

  // 右侧面板
  const rightPanel = (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <div style={{ flex: 1, minHeight: 0 }}>
        <StrategyEditor
          code={code}
          onChange={setCode}
          isNew={isNew}
          selectedStrategy={selectedStrategy}
        />
      </div>
      {taskId && (
        <div style={{ height: '40%', minHeight: 300, borderTop: '1px solid #f0f0f0' }}>
          <StrategyResult taskId={taskId} />
        </div>
      )}
    </div>
  )

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
      <Content style={{ background: '#fff' }}>
        {rightPanel}
      </Content>
    </Layout>
  )
}

// 默认策略模板
const DEFAULT_TEMPLATE = `# -*- coding: utf-8 -*-
"""新策略"""

from QuantStudio.BackTest.Strategy.Strategy import MakeStrategy
from QSExt.StrategyDef.StrategyDefContent import StrategyDefInput

__STRATEGY_META__ = {
    "TargetTable": "my_strategy_signals",
    "IDType": "A股",
    "Description": "",
    "OperatorConfig": {
        "SignalType": "目标权重",
        "InitCash": 1e6,
        "ShortAllowed": False,
    },
    "FactorDeps": {},
    "StrategyDeps": {},
    "DBDeps": {},
    "ModelArgs": {},
    "Author": "",
    "Tags": [],
    "MaxLookBack": 365,
    "DefScriptPath": __file__,
}

class MyStrategy(MakeStrategy):
    def genSignal(self, f, idt, x, last_price, cash, position_num, args):
        # 在此编写你的交易信号逻辑
        # x: 依赖因子数据列表
        # 返回: pd.Series，index 为证券 ID，值为信号
        return None

def defStrategy(sdi: StrategyDefInput):
    op = MyStrategy(
        signal_type=sdi.ModelArgs.get("signal_type", "目标权重"),
        init_cash=sdi.ModelArgs.get("init_cash", 1e6),
        short_allowed=sdi.ModelArgs.get("short_allowed", False),
    )
    # 从 sdi.Factors 取依赖因子，传给 op()
    return op(last_price=sdi.Factors.get("close"))
`

export default StrategyStudio
