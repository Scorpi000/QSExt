/**
 * 回测工作台页面
 *
 * 布局：左侧配置面板 | 右侧结果展示
 */

import { useEffect } from 'react'
import { Row, Col, Card, Button, message } from 'antd'
import { DownloadOutlined } from '@ant-design/icons'
import BacktestConfig from '../../components/BacktestConfig'
import ICAnalysisChart from '../../components/ICAnalysisChart'
import QuantileChart from '../../components/QuantileChart'
import BacktestResult from '../../components/BacktestResult'
import BacktestHistory from '../../components/BacktestHistory'
import TaskProgress from '../../components/TaskProgress'
import { useTaskProgress } from '../../hooks/useTaskProgress'
import { useBacktestStudioStore } from '../../stores/backtestStudio'
import {
  runICAnalysis,
  runQuantilePortfolio,
  runTurnover,
  submitStrategyBacktest,
  getBacktestResult,
  type ICAnalysisParams,
  type QuantilePortfolioParams,
  type TurnoverParams,
} from '../../services/backtest'

function BacktestStudio() {
  const store = useBacktestStudioStore()

  // WebSocket 监听策略回测任务进度
  const { task: wsTask } = useTaskProgress(store.strategyTaskId)

  // 当 WebSocket 通知任务完成或失败时，获取结果或更新状态
  useEffect(() => {
    if (!wsTask || !store.strategyTaskId) return
    if (wsTask.status === 'completed' && !store.strategyResult) {
      getBacktestResult(store.strategyTaskId).then((resp) => {
        if (resp.result) {
          store.setStrategyResult(resp.result)
          store.setStrategyLoading(false)
        }
      }).catch(() => {
        store.setStrategyLoading(false)
      })
    }
    if (wsTask.status === 'failed' && store.strategyLoading) {
      store.setStrategyLoading(false)
      message.error(wsTask.error || '回测任务失败')
    }
  }, [wsTask?.status, store.strategyTaskId, store.strategyResult, store.strategyLoading])

  // IC 分析
  const handleRunIC = async () => {
    store.setIcLoading(true)
    store.setAnalysisType('ic')
    try {
      const params: ICAnalysisParams = {
        conn_id: store.connId,
        table_name: store.tableName,
        factor_name: store.factorName,
      }
      const result = await runICAnalysis(params)
      store.setIcResult(result)
    } catch {
      // api interceptor handles error
    } finally {
      store.setIcLoading(false)
    }
  }

  // 分位数组合
  const handleRunQuantile = async () => {
    store.setQuantileLoading(true)
    store.setAnalysisType('quantile')
    try {
      const params: QuantilePortfolioParams = {
        conn_id: store.connId,
        table_name: store.tableName,
        factor_name: store.factorName,
      }
      const result = await runQuantilePortfolio(params)
      store.setQuantileResult(result)
    } finally {
      store.setQuantileLoading(false)
    }
  }

  // 换手率
  const handleRunTurnover = async () => {
    store.setTurnoverLoading(true)
    store.setAnalysisType('turnover')
    try {
      const params: TurnoverParams = {
        conn_id: store.connId,
        table_name: store.tableName,
        factor_name: store.factorName,
      }
      const result = await runTurnover(params)
      store.setTurnoverResult(result)
    } finally {
      store.setTurnoverLoading(false)
    }
  }

  // 策略回测（异步）
  const handleRunStrategy = async () => {
    store.setStrategyLoading(true)
    store.setAnalysisType('strategy')
    store.setStrategyResult(null)
    try {
      const params = store.strategyParams || {
        conn_id: store.connId,
        table_name: store.tableName,
        factor_name: store.factorName,
      }
      const { task_id } = await submitStrategyBacktest(params)
      store.setStrategyTaskId(task_id)
    } catch {
      store.setStrategyLoading(false)
    }
  }

  const isLoading = store.icLoading || store.quantileLoading || store.turnoverLoading || store.strategyLoading

  return (
    <div style={{ height: 'calc(100vh - 160px)', overflow: 'auto' }}>
      <Row gutter={16}>
        {/* 左侧：配置面板 */}
        <Col span={6}>
          <BacktestConfig
            onRunIC={handleRunIC}
            onRunQuantile={handleRunQuantile}
            onRunTurnover={handleRunTurnover}
            onRunStrategy={handleRunStrategy}
            loading={isLoading}
          />

          {/* 策略回测进度 */}
          {store.strategyTaskId && store.strategyLoading && (
            <Card title="任务进度" size="small" style={{ marginTop: 12 }}>
              <TaskProgress task={wsTask} width={undefined} />
            </Card>
          )}
        </Col>

        {/* 右侧：结果展示 */}
        <Col span={18}>
          <Card
            size="small"
            style={{ minHeight: 400 }}
            extra={
              (store.icResult || store.quantileResult || store.strategyResult) && (
                <Button size="small" icon={<DownloadOutlined />}>
                  导出报告
                </Button>
              )
            }
          >
            {/* 切换标签页 */}
            {store.analysisType === 'ic' && store.icResult && (
              <ICAnalysisChart result={store.icResult} />
            )}
            {store.analysisType === 'quantile' && store.quantileResult && (
              <QuantileChart result={store.quantileResult} />
            )}
            {store.analysisType === 'strategy' && store.strategyResult && (
              <BacktestResult result={store.strategyResult} />
            )}
            {store.analysisType === 'turnover' && store.turnoverResult && (
              <div>
                <h4>换手率分析: {store.turnoverResult.factor_name}</h4>
                <p>平均换手率: <strong>{(store.turnoverResult.avg_turnover * 100).toFixed(2)}%</strong></p>
              </div>
            )}

            {/* 无结果提示 */}
            {!store.icResult && !store.quantileResult && !store.strategyResult && !store.turnoverResult && (
              <div style={{ textAlign: 'center', padding: 60, color: '#999' }}>
                <p>请在左侧选择因子并运行分析</p>
                <p>支持 IC 分析、分位数组合、换手率分析和策略回测</p>
              </div>
            )}
          </Card>

          {/* 回测历史 */}
          <div style={{ marginTop: 16 }}>
            <BacktestHistory />
          </div>
        </Col>
      </Row>
    </div>
  )
}

export default BacktestStudio
