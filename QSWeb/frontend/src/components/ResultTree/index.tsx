/**
 * ResultTree - 结果树组件
 *
 * 使用 Ant Tree 渲染回测结果节点，按 type 区分图标。
 */

import { Tree } from 'antd'
import type { DataNode } from 'antd/es/tree'
import {
  FolderOutlined,
  LineChartOutlined,
  TableOutlined,
  NumberOutlined,
} from '@ant-design/icons'
import type { ResultNode } from '../../services/backtest'

interface ResultTreeProps {
  /** 结果树根节点 */
  data: ResultNode | null
  /** 选中节点回调 */
  onSelect?: (node: ResultNode) => void
}

/** 将 ResultNode 递归转换为 Ant Design Tree DataNode */
function toTreeData(node: ResultNode): DataNode {
  const icon = getIcon(node.type)
  const children = node.children?.map(toTreeData)

  return {
    key: node.key,
    title: node.label,
    icon,
    children: children && children.length > 0 ? children : undefined,
    isLeaf: node.type !== 'branch',
    // 存储原始 ResultNode 信息用于选中回调
    _raw: node,
  } as DataNode & { _raw: ResultNode }
}

function getIcon(type: string): React.ReactNode {
  switch (type) {
    case 'branch':
      return <FolderOutlined style={{ color: '#1677ff' }} />
    case 'series':
      return <LineChartOutlined style={{ color: '#52c41a' }} />
    case 'dataframe':
      return <TableOutlined style={{ color: '#fa8c16' }} />
    case 'scalar':
      return <NumberOutlined style={{ color: '#722ed1' }} />
    default:
      return <FolderOutlined />
  }
}

function ResultTree({ data, onSelect }: ResultTreeProps) {
  if (!data) {
    return (
      <div style={{ textAlign: 'center', padding: 32, color: '#ccc' }}>
        暂无结果数据
      </div>
    )
  }

  const treeData = [toTreeData(data)]

  const handleSelect = (_keys: React.Key[], info: any) => {
    const raw = (info.node as any)?._raw as ResultNode | undefined
    if (raw && raw.type !== 'branch' && onSelect) {
      onSelect(raw)
    }
  }

  return (
    <Tree
      showIcon
      defaultExpandAll
      treeData={treeData}
      onSelect={handleSelect}
      style={{ fontSize: 13 }}
    />
  )
}

export default ResultTree
