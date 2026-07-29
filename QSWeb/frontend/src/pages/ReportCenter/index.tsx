/**
 * ReportCenter - 报告中心页面
 *
 * 布局编排：ScenarioPicker（生成表单）+ ReportList（报告列表）+ ReportPreview（预览弹窗）。
 * 从全局因子池读取已选因子用于报告生成。
 */

import { useState, useEffect, useCallback, useMemo } from 'react'
import { Card, Space, Select, Input, Button, message, Progress } from 'antd'
import { PlusOutlined, FileTextOutlined, ReloadOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import {
  listScenarios, generateReport, listReports, getReportContent,
  deleteReport, registerReport, getTask, getReportConfig, updateReportConfig,
  type ReportScenario, type ReportInfo, type ReportGenerateRequest,
  type FactorRef, type TaskStatus,
} from '../../services/report'
import { useFactorPoolStore } from '../../stores/factorPoolStore'
import ScenarioPicker from './ScenarioPicker'
import ReportList from './ReportList'
import ReportPreview from './ReportPreview'

export default function ReportCenter() {
  // ── 全局因子池 ───────────────────────────────────────────
  const poolItems = useFactorPoolStore((s) => s.items)
  const selectedIds = useFactorPoolStore((s) => s.selectedIds)

  // ── 生成表单 ─────────────────────────────────────────────
  const [scenarios, setScenarios] = useState<ReportScenario[]>([])
  const [scenario, setScenario] = useState('single_factor')
  const [reportName, setReportName] = useState('')
  const [priceRef, setPriceRef] = useState<FactorRef | undefined>()
  const [maskRef, setMaskRef] = useState<FactorRef | undefined>()
  const [catDataRef, setCatDataRef] = useState<FactorRef | undefined>()
  const [weightRef, setWeightRef] = useState<FactorRef | undefined>()
  const defaultDateRange = useMemo<[string, string]>(() => {
    const end = dayjs(); const start = dayjs().subtract(3, 'year')
    return [start.format('YYYY-MM-DD'), end.format('YYYY-MM-DD')]
  }, [])
  const [dateRange, setDateRange] = useState<[string, string] | null>(defaultDateRange)
  const [outputFormats, setOutputFormats] = useState<string[]>(['html'])
  const [modules, setModules] = useState<Record<string, boolean>>({
    ic: true, ic_decay: true, quantile_portfolio: true, factor_turnover: true,
  })

  // ── 任务状态 ─────────────────────────────────────────────
  const [taskId, setTaskId] = useState<string | null>(null)
  const [taskStatus, setTaskStatus] = useState<TaskStatus | null>(null)
  const [generating, setGenerating] = useState(false)

  // ── 报告列表 ─────────────────────────────────────────────
  const [reports, setReports] = useState<ReportInfo[]>([])
  const [loadingReports, setLoadingReports] = useState(false)
  const [filterScenario, setFilterScenario] = useState<string | undefined>()
  const [filterFactor, setFilterFactor] = useState('')

  // ── 预览 ─────────────────────────────────────────────────
  const [previewReport, setPreviewReport] = useState<ReportInfo | null>(null)
  const [previewContent, setPreviewContent] = useState<Record<string, string> | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewVisible, setPreviewVisible] = useState(false)

  // ── 注册 ─────────────────────────────────────────────────
  const [registering, setRegistering] = useState<string | null>(null)

  // ── 配置 ─────────────────────────────────────────────────
  const [outputDir, setOutputDir] = useState('')
  const [editingDir, setEditingDir] = useState(false)
  const [editDirValue, setEditDirValue] = useState('')
  const [savingDir, setSavingDir] = useState(false)

  // ── 初始化 ───────────────────────────────────────────────
  useEffect(() => {
    listScenarios().then((d) => setScenarios(d as unknown as ReportScenario[])).catch(() => {})
    loadReports()
    getReportConfig().then((d) => {
      setOutputDir((d as unknown as { output_dir: string }).output_dir)
    }).catch(() => {})
  }, [])

  // ── 轮询任务状态 ─────────────────────────────────────────
  useEffect(() => {
    if (!taskId || taskStatus?.status === 'completed' || taskStatus?.status === 'failed') return
    const timer = setInterval(async () => {
      try {
        const t = (await getTask(taskId)) as unknown as TaskStatus
        setTaskStatus(t)
        if (t.status === 'completed' || t.status === 'failed') {
          setGenerating(false)
          if (t.status === 'completed') { message.success('报告生成完成！'); loadReports() }
          else { message.error(t.error || '报告生成失败') }
        }
      } catch { /* ignore */ }
    }, 2000)
    return () => clearInterval(timer)
  }, [taskId, taskStatus?.status])

  const loadReports = useCallback(async () => {
    setLoadingReports(true)
    try {
      setReports((await listReports({
        scenario: filterScenario,
        factor_name: filterFactor || undefined,
      })) as unknown as ReportInfo[])
    } catch { /* ignore */ }
    finally { setLoadingReports(false) }
  }, [filterScenario, filterFactor])

  useEffect(() => { loadReports() }, [loadReports])

  // ── 生成报告 ─────────────────────────────────────────────
  const getSelectedFactorRefs = useCallback((): FactorRef[] => {
    return poolItems
      .filter((item) => selectedIds.has(item.id))
      .map((item) => ({
        conn_id: item.ref.conn_id || '',
        table_name: item.ref.table_name || '',
        factor_name: item.label,
      }))
  }, [poolItems, selectedIds])

  const handleGenerate = async () => {
    const selectedRefs = getSelectedFactorRefs()
    if (selectedRefs.length === 0) { message.error('请从全局因子池中选择至少一个被测因子'); return }
    if (!dateRange) { message.error('请选择日期范围'); return }
    if (outputFormats.length === 0) { message.error('请至少选择一个输出格式'); return }

    const req: ReportGenerateRequest = {
      scenario, name: reportName || `${scenario} 报告`,
      factor_refs: selectedRefs,
      price_ref: priceRef || null, mask_ref: maskRef || null,
      cat_data_ref: catDataRef || null, weight_ref: weightRef || null,
      start_date: dateRange[0], end_date: dateRange[1],
      output_formats: outputFormats, modules: modules as any,
    }

    setGenerating(true)
    try {
      setTaskId(((await generateReport(req)) as unknown as { task_id: string }).task_id)
      setTaskStatus(null)
    } catch (e: any) { message.error(e?.response?.data?.detail || '提交失败'); setGenerating(false) }
  }

  // ── 预览/下载/注册/删除 ──────────────────────────────────
  const handlePreview = async (report: ReportInfo) => {
    setPreviewReport(report); setPreviewVisible(true); setPreviewContent(null); setPreviewLoading(true)
    try {
      const fmt = report.formats.includes('html') ? 'html' : report.formats[0]
      setPreviewContent((await getReportContent(report.id, fmt)) as unknown as Record<string, string>)
    } catch { message.error('加载报告内容失败') }
    finally { setPreviewLoading(false) }
  }

  const handleDownload = (report: ReportInfo) => {
    const fmt = report.formats.includes('html') ? 'html' : report.formats[0]
    getReportContent(report.id, fmt).then((res) => {
      const ext = fmt === 'markdown' ? 'md' : 'html'
      Object.entries(res as unknown as Record<string, string>).forEach(([name, content]) => {
        const blob = new Blob([content], { type: 'text/plain' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url; a.download = `${name}.${ext}`; a.click()
        URL.revokeObjectURL(url)
      })
    }).catch(() => message.error('下载失败'))
  }

  const handleDelete = async (id: string) => {
    try { await deleteReport(id); message.success('删除成功'); loadReports() }
    catch { message.error('删除失败') }
  }

  const handleRegister = async (report: ReportInfo) => {
    setRegistering(report.id)
    try { await registerReport(report.id, {}); message.success('注册成功'); loadReports() }
    catch { message.error('注册失败') }
    finally { setRegistering(null) }
  }

  const handleSaveDir = async () => {
    setSavingDir(true)
    try { await updateReportConfig(editDirValue); setOutputDir(editDirValue); setEditingDir(false); message.success('保存成功') }
    catch { message.error('保存失败') }
    finally { setSavingDir(false) }
  }

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto' }}>
      {/* 存储配置 */}
      <div style={{ marginBottom: 16, padding: '8px 16px', background: '#fafafa', borderRadius: 8, display: 'flex', alignItems: 'center', gap: 12 }}>
        <span style={{ color: '#666', fontSize: 13 }}>报告存储目录:</span>
        {editingDir ? (
          <Space>
            <Input style={{ width: 400 }} value={editDirValue} onChange={(e) => setEditDirValue(e.target.value)} placeholder="输入目录路径" />
            <Button size="small" type="primary" loading={savingDir} onClick={handleSaveDir}>保存</Button>
            <Button size="small" onClick={() => setEditingDir(false)}>取消</Button>
          </Space>
        ) : (
          <Space>
            <code style={{ fontSize: 12, background: '#fff', padding: '2px 8px', borderRadius: 4 }}>{outputDir}</code>
            <Button size="small" type="link" onClick={() => { setEditDirValue(outputDir); setEditingDir(true) }}>修改</Button>
          </Space>
        )}
      </div>

      {/* 报告生成 */}
      <Card title={<span><FileTextOutlined /> 生成新报告</span>} style={{ marginBottom: 24 }}>
        <ScenarioPicker
          scenarios={scenarios} scenario={scenario} reportName={reportName}
          priceRef={priceRef} maskRef={maskRef} catDataRef={catDataRef} weightRef={weightRef}
          dateRange={dateRange} outputFormats={outputFormats} modules={modules}
          onScenarioChange={setScenario} onReportNameChange={setReportName}
          onPriceRefChange={setPriceRef} onMaskRefChange={setMaskRef}
          onCatDataRefChange={setCatDataRef} onWeightRefChange={setWeightRef}
          onDateRangeChange={setDateRange} onOutputFormatsChange={setOutputFormats}
          onModulesChange={setModules}
        />
        <div style={{ marginTop: 16 }}>
          <Space>
            <Button type="primary" icon={<PlusOutlined />} onClick={handleGenerate} loading={generating}>
              生成报告
            </Button>
            {taskId && taskStatus && (
              <div style={{ minWidth: 300 }}>
                <Progress percent={Math.round(taskStatus.progress)}
                  status={taskStatus.status === 'failed' ? 'exception' : taskStatus.status === 'completed' ? 'success' : 'active'}
                  format={() => `${Math.round(taskStatus.progress)}%`} />
                <span style={{ fontSize: 12, color: '#666' }}>{taskStatus.progress_message}</span>
              </div>
            )}
          </Space>
        </div>
      </Card>

      {/* 报告列表 */}
      <Card
        title={<span><FileTextOutlined /> 已生成报告 ({reports.length})</span>}
        extra={
          <Space>
            <Select placeholder="场景筛选" allowClear style={{ width: 150 }}
              value={filterScenario} onChange={setFilterScenario}
              options={scenarios.map((s) => ({ value: s.key, label: s.name }))} />
            <Input placeholder="因子名筛选" allowClear style={{ width: 150 }}
              value={filterFactor} onChange={(e) => setFilterFactor(e.target.value)} />
            <Button icon={<ReloadOutlined />} onClick={loadReports}>刷新</Button>
          </Space>
        }>
        <ReportList
          reports={reports} loading={loadingReports} scenarios={scenarios}
          filterScenario={filterScenario} filterFactor={filterFactor} registering={registering}
          onFilterScenarioChange={setFilterScenario} onFilterFactorChange={setFilterFactor}
          onRefresh={loadReports}
          onPreview={handlePreview} onDownload={handleDownload}
          onRegister={handleRegister} onDelete={handleDelete}
        />
      </Card>

      {/* 预览弹窗 */}
      <ReportPreview
        visible={previewVisible} report={previewReport}
        content={previewContent} loading={previewLoading}
        onClose={() => { setPreviewVisible(false); setPreviewContent(null) }}
      />
    </div>
  )
}
