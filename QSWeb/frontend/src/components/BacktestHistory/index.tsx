/**
 * 回测历史列表 + 对比功能
 */

import { useEffect, useState } from 'react'
import { Card, Table, Button, Space, Empty, Modal } from 'antd'
import { ColumnHeightOutlined, SaveOutlined, HistoryOutlined } from '@ant-design/icons'
import PlotlyChart from '../PlotlyChart'
import {
  getBacktestHistory,
  registerBacktest,
  type BacktestHistoryItem,
} from '../../services/backtest'
import { useBacktestStudioStore } from '../../stores/backtestStudio'

function BacktestHistory() {
  const [history, setHistory] = useState<BacktestHistoryItem[]>([])
  const [loading, setLoading] = useState(false)
  const [compareModalOpen, setCompareModalOpen] = useState(false)
  const { compareIds, toggleCompareId, clearCompare } = useBacktestStudioStore()

  // 加载历史
  const loadHistory = () => {
    setLoading(true)
    getBacktestHistory(undefined, 30)
      .then((res) => setHistory(res.items))
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    loadHistory()
  }, [])

  // 注册回测
  const handleRegister = async (item: BacktestHistoryItem) => {
    try {
      await registerBacktest(item.task_id, item.name)
      loadHistory()
    } catch {
      // 错误由 api interceptor 处理
    }
  }

  const columns = [
    { title: '名称', dataIndex: 'name', key: 'name', ellipsis: true },
    {
      title: '因子', dataIndex: 'factor_name', key: 'factor_name', width: 120, ellipsis: true,
    },
    {
      title: '总收益', key: 'total_return', width: 80, align: 'right' as const,
      render: (_: unknown, r: BacktestHistoryItem) => {
        const ret = r.summary?.total_return
        if (ret == null) return '-'
        return <span style={{ color: ret >= 0 ? '#3f8600' : '#cf1322' }}>{ret}%</span>
      },
    },
    {
      title: '夏普', key: 'sharpe', width: 60, align: 'right' as const,
      render: (_: unknown, r: BacktestHistoryItem) => r.summary?.sharpe_ratio?.toFixed(2) || '-',
    },
    {
      title: '最大回撤', key: 'max_dd', width: 80, align: 'right' as const,
      render: (_: unknown, r: BacktestHistoryItem) => {
        const dd = r.summary?.max_drawdown
        return dd != null ? `${dd}%` : '-'
      },
    },
    {
      title: '时间', dataIndex: 'created_at', key: 'created_at', width: 160,
      render: (v: string) => v?.replace('T', ' ').substring(0, 19) || '-',
    },
    {
      title: '操作', key: 'actions', width: 120,
      render: (_: unknown, r: BacktestHistoryItem) => (
        <Space size="small">
          <Button size="small" icon={<SaveOutlined />} onClick={() => handleRegister(r)}>
            注册
          </Button>
        </Space>
      ),
    },
  ]

  // 对比用的净值数据
  const compareData: Plotly.Data[] = history
    .filter((h) => compareIds.includes(h.task_id))
    .map((h) => {
      return {
        x: [],
        y: [],
        type: 'scatter' as const,
        mode: 'lines' as const,
        name: h.name,
      }
    })

  return (
    <>
      <Card
        title={<Space><HistoryOutlined />回测历史</Space>}
        size="small"
        extra={
          <Space>
            <Button size="small" onClick={() => setCompareModalOpen(true)} disabled={compareIds.length < 2}>
              <ColumnHeightOutlined /> 对比 ({compareIds.length})
            </Button>
            <Button size="small" onClick={loadHistory}>刷新</Button>
          </Space>
        }
      >
        <Table
          columns={columns}
          dataSource={history}
          loading={loading}
          size="small"
          pagination={{ pageSize: 10 }}
          rowKey="task_id"
          rowSelection={{
            type: 'checkbox',
            selectedRowKeys: compareIds,
            onChange: (keys) => {
              clearCompare()
              keys.forEach((k) => toggleCompareId(k as string))
            },
          }}
          locale={{ emptyText: <Empty description="暂无回测历史" /> }}
        />
      </Card>

      {/* 对比弹窗 */}
      <Modal
        title="回测对比"
        open={compareModalOpen}
        onCancel={() => setCompareModalOpen(false)}
        width={800}
        footer={null}
      >
        {compareData.length >= 2 ? (
          <PlotlyChart
            data={compareData}
            style={{ height: 450 }}
            layout={{ yaxis: { title: '净值' } }}
          />
        ) : (
          <Empty description="请选择至少 2 个回测进行对比" />
        )}

        {/* 对比表格 */}
        {compareIds.length >= 2 && (
          <Table
            style={{ marginTop: 16 }}
            dataSource={history.filter((h) => compareIds.includes(h.task_id))}
            columns={[
              { title: '名称', dataIndex: 'name', key: 'name' },
              {
                title: '总收益', key: 'ret', render: (_: unknown, r: BacktestHistoryItem) =>
                  r.summary ? `${r.summary.total_return}%` : '-',
              },
              {
                title: '夏普', key: 'sr', render: (_: unknown, r: BacktestHistoryItem) =>
                  r.summary?.sharpe_ratio?.toFixed(2) || '-',
              },
              {
                title: '最大回撤', key: 'mdd', render: (_: unknown, r: BacktestHistoryItem) =>
                  r.summary ? `${r.summary.max_drawdown}%` : '-',
              },
            ]}
            size="small"
            pagination={false}
            rowKey="task_id"
          />
        )}
      </Modal>
    </>
  )
}

export default BacktestHistory
