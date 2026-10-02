<template>
  <section class="page" data-module="feeder">
    <header class="page-head">
      <div>
        <h2>馈线巡检管理</h2>
        <p class="page-desc">维护馈线，围绕馈线编号、所属站点、馈线长度、接头数量做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记馈线</button>
        <button class="btn" type="button" @click="exportRows">导出馈线巡检清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>馈线编号</span>
        <input v-model="keyword" placeholder="按馈线编号检索" />
      </label>
      <label class="filter-item">
        <span>馈线状态</span>
        <select v-model="statusFilter">
          <option value="">全部状态</option>
          <option v-for="option in statuses" :key="option" :value="option">{{ option }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">
            <button v-if="column === '馈线编号'" class="link" type="button" @click="openDetail(row)">
              {{ row[column] ?? '—' }}
            </button>
            <template v-else-if="column === '馈线状态'">
              {{ rowStatus(row) ?? '—' }}
            </template>
            <template v-else>{{ row[column] ?? '—' }}</template>
          </td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              :disabled="!actionAllowed(action, rowStatus(row))"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
            <button class="link" type="button" @click="openEdit(row)">修改</button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无符合条件的馈线巡检数据</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条馈线巡检记录，当前页 {{ rows.length }} 条</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <div v-if="formVisible" class="modal-mask" @click.self="closeForm">
      <div class="modal">
        <h3>{{ formMode === 'create' ? '登记馈线' : '修改馈线登记内容' }}</h3>
        <form @submit.prevent="submitForm">
          <label v-for="field in formFields" :key="field" class="form-item">
            <span>{{ field }}{{ requiredFields.includes(field) ? ' *' : '' }}</span>
            <input v-model="form[field]" :placeholder="field === '馈线长度' ? '必填，缺失会被拦下' : `请填写${field}`" />
          </label>
          <p v-if="formError" class="error-text">{{ formError }}</p>
          <div class="form-actions">
            <button class="btn ghost" type="button" @click="closeForm">取消</button>
            <button class="btn primary" type="submit" :disabled="saving">{{ saving ? '保存中…' : '保存' }}</button>
          </div>
        </form>
      </div>
    </div>

    <div v-if="detailVisible && detail" class="modal-mask" @click.self="detailVisible = false">
      <div class="modal">
        <h3>馈线明细 · {{ detail['馈线编号'] ?? '' }}</h3>
        <dl class="detail-list">
          <div v-for="field in detailFields" :key="field">
            <dt>{{ field }}</dt>
            <dd>{{ detail[field] ?? '—' }}</dd>
          </div>
        </dl>
        <p v-if="detailError" class="error-text">{{ detailError }}</p>
        <div class="form-actions">
          <button class="btn" type="button" @click="openEdit(detail)">修改登记内容</button>
          <button class="btn primary" type="button" @click="detailVisible = false">关闭</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/feeder'
const columns = ["馈线编号", "所属站点", "馈线长度", "接头数量", "防水情况", "接地电阻", "巡检日期", "馈线状态"]
const actions = ["登记失效", "登记超标", "安排修复"]
const statuses = ["正常", "防水失效", "接地超标", "已修复"]
const requiredFields = ["馈线编号", "所属站点", "馈线长度"]
const formFields = ["馈线编号", "所属站点", "馈线长度", "接头数量", "防水情况", "接地电阻", "巡检日期"]
const detailFields = ["馈线编号", "所属站点", "馈线长度", "接头数量", "防水情况", "接地电阻", "巡检日期", "馈线状态"]
// 与后端 ACTION_FROM 保持同一口径：状态只沿序列前进，不显示不该走的动作
const ACTION_FROM: Record<string, string[]> = {
  登记失效: ["正常"],
  登记超标: ["正常", "防水失效"],
  安排修复: ["防水失效", "接地超标"],
}

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const keyword = ref('')
const statusFilter = ref('')
const stats = ref([
  { label: '正常馈线', value: 0 },
  { label: '失效馈线', value: 0 },
  { label: '超标馈线', value: 0 },
  { label: '已修复馈线', value: 0 },
])

const formVisible = ref(false)
const formMode = ref<'create' | 'edit'>('create')
const editingId = ref<number | null>(null)
const form = ref<Record<string, string>>({})
const formError = ref('')
const saving = ref(false)

const detailVisible = ref(false)
const detail = ref<Row | null>(null)
const detailError = ref('')

function rowStatus(row: Row): string {
  return String(row.status ?? row['馈线状态'] ?? '')
}

function actionAllowed(action: string, current: string): boolean {
  return ACTION_FROM[action]?.includes(current) ?? false
}

function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function blankForm(): Record<string, string> {
  return {
    馈线编号: '',
    所属站点: '',
    馈线长度: '',
    接头数量: '',
    防水情况: '正常',
    接地电阻: '合格',
    巡检日期: '',
  }
}

function openCreate() {
  formMode.value = 'create'
  editingId.value = null
  form.value = blankForm()
  formError.value = ''
  formVisible.value = true
}

function openEdit(row: Row) {
  formMode.value = 'edit'
  editingId.value = Number(row.id)
  form.value = { ...blankForm() }
  for (const field of formFields) {
    const value = row[field]
    if (value !== null && value !== undefined) {
      form.value[field] = String(value)
    }
  }
  detailVisible.value = false
  formError.value = ''
  formVisible.value = true
}

function closeForm() {
  formVisible.value = false
  editingId.value = null
}

async function openDetail(row: Row) {
  detailError.value = ''
  detail.value = row
  detailVisible.value = true
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    if (!response.ok) {
      throw new Error(`明细读取失败（${response.status}）`)
    }
    // 明细以服务端单条记录为准，保证与列表同源、字段一致
    detail.value = (await response.json()) as Row
  } catch (error) {
    detailError.value = error instanceof Error ? error.message : '馈线明细读取失败'
  }
}

async function submitForm() {
  const missing = requiredFields.filter((field) => !form.value[field]?.trim())
  if (missing.length) {
    // 馈线长度等必填项为空时直接拦下，并点明缺哪一项
    formError.value = `缺少必填字段：${missing.join('、')}`
    return
  }
  formError.value = ''
  saving.value = true
  try {
    const url = formMode.value === 'create' ? ENDPOINT : `${ENDPOINT}/${editingId.value}`
    const method = formMode.value === 'create' ? 'POST' : 'PUT'
    const response = await request(url, {
      method,
      body: JSON.stringify({ values: form.value }),
    })
    const payload = (await response.json().catch(() => null)) as { ok?: boolean; message?: string } | null
    // 后端业务失败仍是 200，必须看 ok，不能只看 HTTP 状态
    if (!response.ok || !payload || payload.ok === false) {
      throw new Error(payload?.message || '馈线登记内容未保存，请稍后重试')
    }
    closeForm()
    await reload()
  } catch (error) {
    formError.value = error instanceof Error ? error.message : '馈线登记内容保存失败'
  } finally {
    saving.value = false
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      // 后端从 values.action 取动作；之前直接发 { action }，动作恒为空、被静默驳回
      body: JSON.stringify({ values: { action } }),
    })
    const payload = (await response.json().catch(() => null)) as { ok?: boolean; message?: string } | null
    if (!response.ok || !payload || payload.ok === false) {
      throw new Error(payload?.message || '馈线巡检动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '馈线巡检操作失败'
  }
}

async function fetchPage(): Promise<{ items: Row[]; total: number }> {
  const params = new URLSearchParams()
  if (keyword.value.trim()) {
    params.set('keyword', keyword.value.trim())
  }
  if (statusFilter.value) {
    params.set('status', statusFilter.value)
  }
  const response = await request(`${ENDPOINT}?${params.toString()}`)
  if (!response.ok) {
    throw new Error(`馈线列表读取失败（${response.status}）`)
  }
  const payload = (await response.json()) as { items?: Row[]; total?: number }
  return { items: payload.items ?? [], total: payload.total ?? 0 }
}

async function reload() {
  errorMessage.value = ''
  // 清单拉不到时再取一次，别停在半截；两次都失败才报错，且保留上次的数据
  try {
    const page = await fetchPage()
    rows.value = page.items
    total.value = page.total
  } catch (firstError) {
    try {
      const retry = await fetchPage()
      rows.value = retry.items
      total.value = retry.total
    } catch {
      errorMessage.value = firstError instanceof Error ? firstError.message : '馈线巡检列表读取失败'
    }
  }
  void loadStats()
}

async function loadStats() {
  // 状态卡片统计的是全量馈线，不受当前筛选条件影响
  try {
    const response = await request(`${ENDPOINT}?page=1&size=200`)
    if (!response.ok) {
      return
    }
    const payload = (await response.json()) as { items?: Row[] }
    const all = payload.items ?? []
    const count = (status: string) => all.filter((row) => rowStatus(row) === status).length
    stats.value[0].value = count('正常')
    stats.value[1].value = count('防水失效')
    stats.value[2].value = count('接地超标')
    stats.value[3].value = count('已修复')
  } catch {
    // 统计刷新失败不影响主列表，下一轮 reload 会再试
  }
}

onMounted(reload)
</script>

<style scoped>
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 20;
}
.modal {
  background: #fff;
  border-radius: 10px;
  padding: 18px 20px;
  width: 520px;
  max-width: calc(100vw - 32px);
  max-height: 86vh;
  overflow: auto;
}
.modal h3 { margin: 0 0 14px; font-size: 16px; }
.form-item { display: flex; flex-direction: column; gap: 4px; margin-bottom: 10px; }
.form-item span { font-size: 12px; color: var(--muted); }
.form-item input { border: 1px solid var(--border); border-radius: 6px; padding: 6px 8px; }
.form-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 6px; }
.detail-list { margin: 0; display: grid; grid-template-columns: 1fr 1fr; gap: 8px 16px; }
.detail-list div { display: flex; flex-direction: column; gap: 2px; }
.detail-list dt { font-size: 12px; color: var(--muted); }
.detail-list dd { margin: 0; font-size: 13px; }
.row-actions .link:disabled { color: #9aa6b2; cursor: not-allowed; }
.filter-item select { border: 1px solid var(--border); border-radius: 6px; padding: 6px 8px; }
</style>
