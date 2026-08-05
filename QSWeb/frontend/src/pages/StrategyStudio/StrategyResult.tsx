/**
 * 策略回测结果展示 —— 净值曲线、绩效统计、交易记录
 */
import React, { useState, useEffect, useCallback, useRef } from 'react'
import { Tabs, Table, Card, Spin, Statistic, Row, Col, Empty, Typography } from 'antd'
import {
  ArrowUpOutlined,
  ArrowDownOutlined,
  LineChartOutlined,
  TableOutlined,
  SwapOutlined,
} from '@ant-design/icons'
import type { ResultNode } from '../../services/strategy'
import { getStrategyBacktestResult } from '../../services/strategy'

const { Text } = Typography

interface StrategyResultProps {
  taskId: string
}

const StrategyResult: React.FC<StrategyResultProps> = ({ taskId }) => {
  const [result, setResult] = useState<ResultNode | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval>>()

  const fetchResult = useCallback(async () => {
    try {
      const data = await getStrategyBacktestResult(taskId)
      setResult(data)
      setLoading(false)
      if (pollRef.current) {
        clearInterval(pollRef.current)
        pollRef.current = undefined
      }
    } catch (err: any) {
      // 202 = 仍在运行中，继续轮询
      if (err?.response?.status === 202) {
        return
      }
      setError(err?.response?.data?.detail || '获取结果失败')
      setLoading(false)
      if (pollRef.current) {
        clearInterval(pollRef.current)
      }
    }
  }, [taskId])

  useEffect(() => {
    setLoading(true)
    setError(null)
    setResult(null)

    // 立即请求一次
    fetchResult()

    // 每 2 秒轮询
    pollRef.current = setInterval(fetchResult, 2000)

    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current)
      }
    }
  }, [taskId, fetchResult])

  if (loading) {
    return (
      <div style={{ padding: 40, textAlign: 'center' }}>
        <Spin tip="回测运行中..." />
      </div>
    )
  }

  if (error) {
    return <Empty description={error} />
  }

  if (!result) {
    return <Empty description="暂无结果" />
  }

  // 查找各类型数据
  const children = result.children || []

  // 统计数据节点
  const statsNode = children.find(
    (c) => c.label?.includes('统计') || c.key?.includes('统计')
  )
  // 序列数据节点（净值曲线）
  const seriesNode = children.find(
    (c) => c.type === 'series' || c.label?.includes('净值') || c.label?.includes('时间序列')
  )
  // 交易记录节点
  const tradeNode = children.find(
    (c) => c.label?.includes('交易') || c.key?.includes('交易')
  )
  // 持仓节点
  const positionNode = children.find(
    (c) => c.label?.includes('持仓') || c.key?.includes('持仓')
  )

  // 从统计数据中提取关键指标
  const statsData = statsNode?.data || {}
  const statItems = statsNode?.children?.map((c) => ({
    label: c.label || c.key,
    value: typeof c.data === 'number' ? c.data.toFixed(4) : String(c.data || '-'),
  })) || []

  const tabItems = [
    {
      key: 'overview',
      label: (
        <span>
          <LineChartOutlined />
          概览
        </span>
      ),
      children: (
        <div style={{ padding: 16 }}>
          {statItems.length > 0 && (
            <Row gutter={16} style={{ marginBottom: 16 }}>
              {statItems.slice(0, 6).map((item, i) => (
                <Col span={8} key={i}>
                  <Card size="small">
                    <Statistic
                      title={item.label}
                      value={item.value}
                      valueStyle={{ fontSize: 16 }}
                    />
                  </Card>
                </Col>
              ))}
            </Row>
          )}
          {seriesNode && (
            <Card size="small" title="净值曲线数据">
              <Text type="secondary">
                数据点数: {Array.isArray(seriesNode.data) ? seriesNode.data.length : 'N/A'}
              </Text>
            </Card>
          )}
        </div>
      ),
    },
    {
      key: 'trades',
      label: (
        <span>
          <SwapOutlined />
          交易记录
        </span>
      ),
      children: (
        <div style={{ padding: 16 }}>
          {tradeNode ? (
            <Table
              dataSource={
                Array.isArray(tradeNode.data)
                  ? tradeNode.data.map((row: any, i: number) => ({ ...row, _key: i }))
                  : []
              }
              columns={
                tradeNode.data &&
                Array.isArray(tradeNode.data) &&
                tradeNode.data.length > 0
                  ? Object.keys(tradeNode.data[0] || {}).map((k) => ({
                      title: k,
                      dataIndex: k,
                      key: k,
                    }))
                  : []
              }
              size="small"
              pagination={{ pageSize: 20 }}
            />
          ) : (
            <Empty description="无交易记录" />
          )}
        </div>
      ),
    },
    {
      key: 'positions',
      label: (
        <span>
          <TableOutlined />
          持仓历史
        </span>
      ),
      children: (
        <div style={{ padding: 16 }}>
          {positionNode ? (
            <Text type="secondary">
              持仓数据已加载（{JSON.stringify(positionNode.data)?.length || 0} 字符）
            </Text>
          ) : (
            <Empty description="无持仓数据" />
          )}
        </div>
      ),
    },
  ]

  return <Tabs items={tabItems} size="small" style={{ padding: '0 12px' }} />
}

export default StrategyResult
