/**
 * 全局因子池类型定义
 */

/** 因子引用（发现阶段使用） */
export interface FactorRef {
  /** 池内唯一 ID = `${source}:${qsid}` */
  id: string
  /** 因子 QSID */
  qsid: string
  /** 来源 */
  source: 'db' | 'registry'
  /** 显示名 */
  label: string
  /** 解析所需信息 */
  ref: {
    conn_id?: string
    table_name?: string
    factor_name?: string
  }
}

/** 池中因子项 */
export interface PoolItem extends FactorRef {
  /** 懒加载统计信息 */
  stats?: FactorStats | null
}

/** 因子统计信息 */
export interface FactorStats {
  id_count: number
  dt_count: number
  first_id: string | null
  last_id: string | null
  first_dt: string | null
  last_dt: string | null
}
