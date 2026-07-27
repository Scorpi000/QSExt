/**
 * 通用进度条组件
 *
 * 用于展示异步任务的进度和状态。
 */

import { Progress, Tag, Space, Typography } from 'antd'
import {
  LoadingOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons'
import type { TaskProgress as TaskProgressType } from '../../hooks/useTaskProgress'

const { Text } = Typography

interface TaskProgressProps {
  task: TaskProgressType | null
  /** 进度条宽度，默认 300 */
  width?: number
  /** 是否显示任务名称 */
  showName?: boolean
}

const statusConfig: Record<string, { color: string; icon: React.ReactNode; label: string }> = {
  pending: { color: 'default', icon: <ClockCircleOutlined />, label: '等待中' },
  running: { color: 'processing', icon: <LoadingOutlined />, label: '运行中' },
  completed: { color: 'success', icon: <CheckCircleOutlined />, label: '已完成' },
  failed: { color: 'error', icon: <CloseCircleOutlined />, label: '失败' },
}

function TaskProgress({ task, width = 300, showName = true }: TaskProgressProps) {
  if (!task) {
    return (
      <div style={{ width, padding: '16px 0' }}>
        <Text type="secondary">等待提交任务...</Text>
      </div>
    )
  }

  const config = statusConfig[task.status] || statusConfig.pending

  return (
    <div style={{ width }}>
      {showName && (
        <div style={{ marginBottom: 4 }}>
          <Text strong>{task.name}</Text>
        </div>
      )}
      <div style={{ marginBottom: 4 }}>
        <Space>
          <Tag color={config.color} icon={config.icon}>
            {config.label}
          </Tag>
          {task.status === 'running' && (
            <Text type="secondary">{task.progress_message}</Text>
          )}
        </Space>
      </div>
      <Progress
        percent={Math.round(task.progress)}
        status={
          task.status === 'failed'
            ? 'exception'
            : task.status === 'completed'
              ? 'success'
              : task.status === 'running'
                ? 'active'
                : 'normal'
        }
        strokeColor={
          task.status === 'failed' ? '#ff4d4f' : undefined
        }
      />
      {task.error && (
        <div style={{ marginTop: 8 }}>
          <Text type="danger">{task.error}</Text>
        </div>
      )}
    </div>
  )
}

export default TaskProgress
