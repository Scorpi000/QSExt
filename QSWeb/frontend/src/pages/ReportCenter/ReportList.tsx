/**
 * ReportList - 已生成报告列表
 *
 * 报告表格展示 + 场景/因子筛选 + 预览/下载/注册/删除操作。
 */

import { Table, Tag, Space, Button, Popconfirm, Select, Input, Empty } from 'antd'
import { EyeOutlined, DownloadOutlined, LinkOutlined, DeleteOutlined, ReloadOutlined } from '@ant-design/icons'
import type { ReportScenario, ReportInfo } from '../../services/report'

interface ReportListProps {
  reports: ReportInfo[]
  loading: boolean
  scenarios: ReportScenario[]
  filterScenario: string | undefined
  filterFactor: string
  registering: string | null
  onFilterScenarioChange: (scenario: string | undefined) => void
  onFilterFactorChange: (factor: string) => void
  onRefresh: () => void
  onPreview: (report: ReportInfo) => void
  onDownload: (report: ReportInfo) => void
  onRegister: (report: ReportInfo) => void
  onDelete: (id: string) => void
}

function ReportList({
  reports, loading, scenarios,
  filterScenario, filterFactor, registering,
  onFilterScenarioChange, onFilterFactorChange, onRefresh,
  onPreview, onDownload, onRegister, onDelete,
}: ReportListProps) {
  return (
    <Table
      dataSource={reports}
      rowKey="id"
      loading={loading}
      pagination={{ pageSize: 10 }}
      scroll={{ x: 'max-content' }}
      locale={{ emptyText: <Empty description="暂无报告，请先生成" /> }}
      columns={[
        { title: '名称', dataIndex: 'name', key: 'name', width: 160, ellipsis: true },
        {
          title: '场景', dataIndex: 'scenario', key: 'scenario', width: 100,
          render: (s: string) => <Tag>{scenarios.find((sc) => sc.key === s)?.name || s}</Tag>,
        },
        {
          title: '因子', dataIndex: 'factor_names', key: 'factors', width: 160,
          render: (names: string[]) => (
            <Space size={4} wrap>{names.map((n) => <Tag key={n} color="blue">{n}</Tag>)}</Space>
          ),
        },
        {
          title: '格式', dataIndex: 'formats', key: 'formats', width: 100,
          render: (fmts: string[]) => <Space>{fmts.map((f) => <Tag key={f}>{f.toUpperCase()}</Tag>)}</Space>,
        },
        {
          title: '状态', key: 'registered', width: 80,
          render: (_: any, r: ReportInfo) => (r.registered ? <Tag color="green">已注册</Tag> : <Tag>未注册</Tag>),
        },
        {
          title: '日期范围', key: 'date', width: 200,
          render: (_: any, r: ReportInfo) => (
            <span style={{ fontSize: 12 }}>{r.start_date} ~ {r.end_date}</span>
          ),
        },
        {
          title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 170,
          render: (t: string) => t?.slice(0, 19).replace('T', ' '),
        },
        {
          title: '操作', key: 'actions', width: 240,
          render: (_: any, r: ReportInfo) => (
            <Space size="small">
              <Button size="small" type="link" icon={<EyeOutlined />} onClick={() => onPreview(r)}>预览</Button>
              <Button size="small" type="link" icon={<DownloadOutlined />} onClick={() => onDownload(r)}>下载</Button>
              <Button size="small" type="link" icon={<LinkOutlined />} loading={registering === r.id}
                disabled={r.registered} onClick={() => onRegister(r)}>注册</Button>
              <Popconfirm title="确认删除此报告？" onConfirm={() => onDelete(r.id)}>
                <Button size="small" type="link" danger icon={<DeleteOutlined />}>删除</Button>
              </Popconfirm>
            </Space>
          ),
        },
      ]}
    />
  )
}

export default ReportList
