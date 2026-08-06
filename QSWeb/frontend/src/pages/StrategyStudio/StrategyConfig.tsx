/**
 * 策略配置面板 —— OperatorConfig 表单 + 因子依赖 + 日期范围
 */
import React from 'react'
import {
  Form,
  Input,
  InputNumber,
  Select,
  DatePicker,
  Button,
  Switch,
  Divider,
  Typography,
} from 'antd'
import { PlayCircleOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import type { OperatorConfig, FactorRef } from '../../services/strategy'

const { Text } = Typography
const { RangePicker } = DatePicker

interface StrategyConfigProps {
  operatorConfig: OperatorConfig
  factorRefs: FactorRef[]
  modelArgs: Record<string, any>
  startDate: string
  endDate: string
  onOperatorConfigChange: (config: OperatorConfig) => void
  onFactorRefsChange: (refs: FactorRef[]) => void
  onModelArgsChange: (args: Record<string, any>) => void
  onStartDateChange: (date: string) => void
  onEndDateChange: (date: string) => void
  onRunBacktest: () => void
}

const StrategyConfig: React.FC<StrategyConfigProps> = ({
  operatorConfig,
  onOperatorConfigChange,
  startDate,
  endDate,
  onStartDateChange,
  onEndDateChange,
  onRunBacktest,
}) => {
  return (
    <div style={{ marginTop: 16 }}>
      <Divider orientation="left" style={{ fontSize: 13, margin: '12px 0' }}>
        策略配置
      </Divider>

      <Form layout="vertical" size="small">
        {/* 信号类型 */}
        <Form.Item label="信号类型">
          <Select
            value={operatorConfig.SignalType}
            onChange={(val) =>
              onOperatorConfigChange({ ...operatorConfig, SignalType: val })
            }
            options={[
              { value: '目标权重', label: '目标权重' },
              { value: '目标持仓', label: '目标持仓' },
              { value: '交易信号', label: '交易信号' },
            ]}
          />
        </Form.Item>

        {/* 初始资金 */}
        <Form.Item label="初始资金">
          <InputNumber
            style={{ width: '100%' }}
            value={operatorConfig.InitCash}
            onChange={(val) =>
              onOperatorConfigChange({
                ...operatorConfig,
                InitCash: val ?? 1e6,
              })
            }
            step={100000}
            formatter={(value) =>
              `${value}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
            }
          />
        </Form.Item>

        {/* 是否允许卖空 */}
        <Form.Item label="允许卖空">
          <Switch
            checked={operatorConfig.ShortAllowed}
            onChange={(val) =>
              onOperatorConfigChange({
                ...operatorConfig,
                ShortAllowed: val,
              })
            }
          />
        </Form.Item>

        {/* 日期范围 */}
        <Form.Item label="回测日期范围">
          <RangePicker
            style={{ width: '100%' }}
            value={
              startDate && endDate
                ? [dayjs(startDate), dayjs(endDate)]
                : undefined
            }
            onChange={(dates) => {
              if (dates && dates[0] && dates[1]) {
                onStartDateChange(dates[0].format('YYYY-MM-DD'))
                onEndDateChange(dates[1].format('YYYY-MM-DD'))
              }
            }}
          />
        </Form.Item>

        {/* 运行按钮 */}
        <Form.Item>
          <Button
            type="primary"
            icon={<PlayCircleOutlined />}
            block
            onClick={onRunBacktest}
          >
            运行回测
          </Button>
        </Form.Item>
      </Form>
    </div>
  )
}

export default StrategyConfig
