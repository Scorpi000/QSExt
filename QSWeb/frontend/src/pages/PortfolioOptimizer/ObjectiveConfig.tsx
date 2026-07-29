/**
 * ObjectiveConfig - 优化目标配置组件
 *
 * 求解器选择 + 优化目标类型选择 + 动态参数表单。
 */

import { Form, Select, InputNumber, Typography } from 'antd'
import { OBJECTIVE_TYPES } from '../../services/portfolio'
import type { SolverInfo } from '../../services/portfolio'

const { Text } = Typography

interface ObjectiveConfigProps {
  solver: string
  solvers: SolverInfo[]
  objType: string
  riskAversion: number
  expectedReturnCoef: number
  onSolverChange: (solver: string) => void
  onObjTypeChange: (objType: string) => void
  onRiskAversionChange: (v: number) => void
  onExpectedReturnCoefChange: (v: number) => void
}

function ObjectiveConfig({
  solver, solvers, objType, riskAversion, expectedReturnCoef,
  onSolverChange, onObjTypeChange, onRiskAversionChange, onExpectedReturnCoefChange,
}: ObjectiveConfigProps) {
  return (
    <>
      {/* 求解器选择 */}
      <Form.Item label="求解器" style={{ marginBottom: 8 }}>
        <Select
          value={solver}
          onChange={onSolverChange}
          options={solvers.map((s) => ({
            value: s.key,
            label: `${s.label}  —  ${s.desc}`,
          }))}
        />
      </Form.Item>

      {/* 目标选择 */}
      <Form.Item label="优化目标" style={{ marginBottom: 8 }}>
        <Select
          value={objType}
          onChange={onObjTypeChange}
          options={OBJECTIVE_TYPES.map((t) => ({
            value: t.value,
            label: `${t.label}  —  ${t.desc}`,
          }))}
        />
      </Form.Item>

      {/* 动态参数 */}
      {objType === 'mean_variance' && (
        <>
          <Form.Item label="风险厌恶系数 (λ)" tooltip="越高越保守，越高个股权重越分散">
            <InputNumber
              min={0} step={0.1} value={riskAversion}
              onChange={(v) => onRiskAversionChange(v ?? 1.0)}
              style={{ width: '100%' }}
            />
          </Form.Item>
          <Form.Item label="收益项系数 (α)" tooltip="预期收益的权重，0 表示纯风险最小化">
            <InputNumber
              min={0} step={0.1} value={expectedReturnCoef}
              onChange={(v) => onExpectedReturnCoefChange(v ?? 0.0)}
              style={{ width: '100%' }}
            />
          </Form.Item>
        </>
      )}
      {objType === 'risk_budget' && (
        <Text type="secondary">风险预算将由优化器自动计算（等风险平价）。如需自定义风险预算向量，请使用 API 直接调用。</Text>
      )}
      {objType === 'max_diversification' && (
        <Text type="secondary">最大化分散化比率，无需额外参数。</Text>
      )}
    </>
  )
}

export default ObjectiveConfig
