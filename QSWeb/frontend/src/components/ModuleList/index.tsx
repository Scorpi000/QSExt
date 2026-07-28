/**
 * ModuleList - 待运行模块列表
 *
 * 展示已配置的回测模块，支持编辑和删除。
 */

import { List, Tag, Button, Space, Popconfirm, Tooltip } from 'antd'
import {
  DeleteOutlined,
  EditOutlined,
  ExperimentOutlined,
  LineChartOutlined,
  PieChartOutlined,
  SafetyOutlined,
  RiseOutlined,
  BarChartOutlined,
} from '@ant-design/icons'
import type { ModuleRunConfig, ModuleInfo } from '../../services/backtest'

const categoryIcons: Record<string, React.ReactNode> = {
  SectionFactor: <ExperimentOutlined />,
  Portfolio: <PieChartOutlined />,
  Correlation: <BarChartOutlined />,
  ReturnDecomposition: <RiseOutlined />,
  Risk: <SafetyOutlined />,
  Strategy: <LineChartOutlined />,
}

const categoryColors: Record<string, string> = {
  SectionFactor: 'blue',
  Portfolio: 'green',
  Correlation: 'orange',
  ReturnDecomposition: 'purple',
  Risk: 'red',
  Strategy: 'cyan',
}

interface ModuleListProps {
  /** 待运行模块配置列表 */
  configs: ModuleRunConfig[]
  /** 模块注册表信息（用于展示名称和分类） */
  moduleInfos: ModuleInfo[]
  /** 编辑模块 */
  onEdit: (index: number) => void
  /** 删除模块 */
  onDelete: (index: number) => void
}

function ModuleList({ configs, moduleInfos, onEdit, onDelete }: ModuleListProps) {
  const getModuleInfo = (key: string): ModuleInfo | undefined =>
    moduleInfos.find((m) => m.key === key)

  if (configs.length === 0) {
    return (
      <div
        style={{
          textAlign: 'center',
          padding: '32px 16px',
          color: '#ccc',
        }}
      >
        暂无回测模块，请从上方添加
      </div>
    )
  }

  return (
    <List
      size="small"
      dataSource={configs}
      renderItem={(cfg, index) => {
        const info = getModuleInfo(cfg.module_key)
        const label = cfg.instance_label || info?.name || cfg.module_key
        const category = info?.category || ''

        return (
          <List.Item
            actions={[
              <Button
                key="edit"
                type="text"
                size="small"
                icon={<EditOutlined />}
                onClick={() => onEdit(index)}
              />,
              <Popconfirm
                key="delete"
                title="确定删除此模块？"
                onConfirm={() => onDelete(index)}
              >
                <Button
                  type="text"
                  size="small"
                  danger
                  icon={<DeleteOutlined />}
                />
              </Popconfirm>,
            ]}
          >
            <List.Item.Meta
              avatar={
                <span style={{ fontSize: 18 }}>
                  {categoryIcons[category] || <ExperimentOutlined />}
                </span>
              }
              title={
                <Space>
                  <span>{label}</span>
                  <Tag color={categoryColors[category] || 'default'} style={{ fontSize: 11 }}>
                    {info?.name || cfg.module_key}
                  </Tag>
                </Space>
              }
              description={
                <Space wrap size={[0, 2]}>
                  <Tooltip title="分配给此模块的因子">
                    <span style={{ fontSize: 12, color: '#888' }}>
                      因子: {cfg.factor_refs.map((f) => f.name).join(', ')}
                    </span>
                  </Tooltip>
                  {Object.keys(cfg.params).length > 0 && (
                    <Tooltip
                      title={Object.entries(cfg.params)
                        .map(([k, v]) => `${k}=${v}`)
                        .join(', ')}
                    >
                      <span style={{ fontSize: 12, color: '#888' }}>
                        | 参数: {Object.keys(cfg.params).length} 项
                      </span>
                    </Tooltip>
                  )}
                </Space>
              }
            />
          </List.Item>
        )
      }}
    />
  )
}

export default ModuleList
