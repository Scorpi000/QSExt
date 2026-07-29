/**
 * ReportPreview - 报告预览弹窗
 *
 * 多 Tab 展示报告内容（HTML iframe / Markdown 纯文本）。
 */

import { Modal, Tabs, Spin, Empty } from 'antd'
import type { ReportInfo } from '../../services/report'

interface ReportPreviewProps {
  visible: boolean
  report: ReportInfo | null
  content: Record<string, string> | null
  loading: boolean
  onClose: () => void
}

function ReportPreview({ visible, report, content, loading, onClose }: ReportPreviewProps) {
  return (
    <Modal
      title={report ? `预览: ${report.name}` : '预览报告'}
      open={visible}
      onCancel={onClose}
      width="90%"
      style={{ top: 20 }}
      footer={null}
      destroyOnClose
    >
      {loading ? (
        <div style={{ textAlign: 'center', padding: 48 }}><Spin size="large" /></div>
      ) : content ? (
        <Tabs
          items={Object.entries(content).map(([name, text]) => ({
            key: name,
            label: name,
            children: (
              <div style={{
                border: '1px solid #f0f0f0', borderRadius: 8, padding: 16,
                maxHeight: '70vh', overflow: 'auto',
              }}>
                {report?.formats.includes('html') && !name.endsWith('.md') ? (
                  <iframe srcDoc={text} style={{ width: '100%', height: '65vh', border: 'none' }} title={name} />
                ) : (
                  <pre style={{ whiteSpace: 'pre-wrap', fontFamily: 'monospace', fontSize: 13 }}>{text}</pre>
                )}
              </div>
            ),
          }))}
        />
      ) : (
        <Empty description="无报告内容" />
      )}
    </Modal>
  )
}

export default ReportPreview
