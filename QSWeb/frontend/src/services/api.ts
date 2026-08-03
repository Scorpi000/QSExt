import axios from 'axios'
import { message } from 'antd'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// 响应拦截器：解包 data + 统一错误处理
api.interceptors.response.use(
  (response) => response.data,
  (error) => {
    if (error.code === 'ECONNABORTED' || error.message?.includes('timeout')) {
      message.error('请求超时，请检查网络连接后重试')
      return Promise.reject(error)
    }

    if (!error.response) {
      message.error('网络连接失败，请检查网络状态')
      return Promise.reject(error)
    }

    const { status, data } = error.response

    // 后端统一错误格式: { code, message, detail }
    const msg = data?.message || data?.detail || error.message || '请求失败'

    switch (status) {
      case 401:
        message.error('未授权，请重新登录')
        break
      case 403:
        message.error('无权限访问该资源')
        break
      case 404:
        message.error(`资源不存在：${msg}`)
        break
      case 422:
        // 验证错误：展示第一条
        if (data?.detail && Array.isArray(data.detail) && data.detail.length > 0) {
          const first = data.detail[0]
          const loc = first.loc?.join('.') || ''
          message.error(`参数错误 [${loc}]: ${first.msg}`)
        } else {
          message.error(msg)
        }
        break
      case 500:
        message.error(msg)
        break
      case 503:
        // 后端未就绪，不弹错误提示（组件层会静默重试）
        break
      default:
        message.error(msg)
    }

    return Promise.reject(error)
  }
)

export default api
