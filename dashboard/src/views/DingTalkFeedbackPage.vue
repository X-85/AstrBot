<template>
  <v-container fluid class="pa-4 pa-md-6">
    <div class="d-flex flex-wrap align-center justify-space-between ga-3 mb-4">
      <div>
        <h1 class="text-h4">钉钉回复反馈</h1>
        <div class="text-body-2 text-medium-emphasis mt-1">仅展示已保存的最终模型回复，不含普通文本指令。</div>
      </div>
      <v-btn variant="tonal" color="primary" prepend-icon="mdi-refresh" :loading="loading" @click="load">
        刷新
      </v-btn>
    </div>

    <v-alert v-if="error" type="error" variant="tonal" class="mb-4">{{ error }}</v-alert>

    <v-card flat border class="mb-4">
      <v-card-text>
        <div class="d-flex flex-wrap ga-3">
          <v-text-field v-model="filters.platform_id" label="平台实例" density="compact" variant="outlined" hide-details clearable />
          <v-text-field v-model="filters.requester" label="提问人" density="compact" variant="outlined" hide-details clearable />
          <v-text-field v-model="filters.session_id" label="会话 ID" density="compact" variant="outlined" hide-details clearable />
          <v-select v-model="filters.vote" :items="voteOptions" label="反馈状态" density="compact" variant="outlined" hide-details />
          <v-text-field v-model="filters.start_time" label="开始时间" type="datetime-local" density="compact" variant="outlined" hide-details />
          <v-text-field v-model="filters.end_time" label="结束时间" type="datetime-local" density="compact" variant="outlined" hide-details />
          <v-checkbox v-model="filters.include_tests" label="包含测试记录" density="compact" hide-details />
          <v-btn color="primary" variant="tonal" @click="applyFilters">筛选</v-btn>
        </div>
      </v-card-text>
    </v-card>

    <v-card flat border class="mb-4">
      <v-card-title class="text-h6">互动卡片预检</v-card-title>
      <v-card-text>
        <div v-if="preflight.length" class="d-flex flex-wrap ga-3">
          <div v-for="item in preflight" :key="item.platform_id" class="preflight-item">
            <strong>{{ item.platform_id }}</strong>
            <span>模式：{{ item.mode }}</span>
            <span>模板：{{ item.template_configured ? '已配置' : '未配置' }}</span>
            <span>Stream：{{ item.stream_connected ? '已连接' : '未连接' }}</span>
            <span>回调：{{ item.callback_registered ? '已注册' : '未注册' }}</span>
          </div>
        </div>
        <span v-else class="text-medium-emphasis">未发现正在运行的钉钉反馈增强适配器。</span>
        <div class="text-caption text-medium-emphasis mt-3">预检不能确认钉钉后台权限。请由管理员在钉钉私聊发送 /dingtalk_card_test，并点击赞或踩完成端到端验证。</div>
      </v-card-text>
    </v-card>

    <v-card flat border>
      <v-data-table :headers="headers" :items="items" :loading="loading" hide-default-footer density="comfortable">
        <template #item.requester_name="{ item }">{{ item.requester_name || item.requester_id }}</template>
        <template #item.feedback="{ item }"><span class="text-success">{{ item.likes }} 赞</span> / <span class="text-error">{{ item.dislikes }} 踩</span></template>
        <template #item.created_at="{ item }">{{ formatTime(item.created_at) }}</template>
        <template #item.actions="{ item }"><v-btn icon="mdi-text-box-search-outline" size="small" variant="text" title="查看详情" @click="selected = item" /></template>
      </v-data-table>
      <v-divider />
      <div class="d-flex justify-end pa-3"><v-pagination v-model="page" :length="totalPages" :total-visible="7" @update:model-value="load" /></div>
    </v-card>

    <v-dialog v-model="detailOpen" max-width="840">
      <v-card v-if="selected">
        <v-card-title class="text-h3 pa-4 pb-0 pl-6">反馈详情</v-card-title>
        <v-card-text class="pt-4">
          <div class="detail-meta">{{ selected.platform_id }} · {{ selected.session_id }} · {{ formatTime(selected.created_at) }}</div>
          <h2 class="text-h6 mt-4">提问</h2><pre>{{ selected.question }}</pre>
          <h2 class="text-h6 mt-4">回复</h2><pre>{{ selected.answer }}</pre>
          <div class="mt-4">模式：{{ selected.mode }}；{{ selected.likes }} 赞 / {{ selected.dislikes }} 踩</div>
          <div v-if="selected.mode === 'interactive_card'" class="mt-2">卡片发送：{{ selected.card_sent ? '成功' : '失败' }}；回调：{{ selected.card_callback_received ? '已接收' : '未接收' }}<div v-if="selected.card_error" class="text-error">{{ selected.card_error }}</div></div>
        </v-card-text>
        <v-card-actions class="justify-end px-5 pb-5"><v-btn variant="text" @click="selected = null">关闭</v-btn></v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { fetchWithAuth } from '@/api/http'

type FeedbackItem = { response_id: string; platform_id: string; session_id: string; requester_id: string; requester_name: string; question: string; answer: string; mode: string; is_test: boolean; card_sent: boolean; card_callback_received: boolean; card_error: string | null; created_at: string; likes: number; dislikes: number }
type PreflightItem = { platform_id: string; mode: string; template_configured: boolean; stream_connected: boolean; callback_registered: boolean }

const items = ref<FeedbackItem[]>([])
const preflight = ref<PreflightItem[]>([])
const loading = ref(false)
const error = ref('')
const page = ref(1)
const totalPages = ref(1)
const selected = ref<FeedbackItem | null>(null)
const detailOpen = computed({ get: () => selected.value !== null, set: value => { if (!value) selected.value = null } })
const filters = ref({ platform_id: '', requester: '', session_id: '', vote: '', start_time: '', end_time: '', include_tests: false })
const voteOptions = [{ title: '全部', value: '' }, { title: '有赞', value: 'like' }, { title: '有踩', value: 'dislike' }]
const headers = [{ title: '时间', key: 'created_at' }, { title: '平台', key: 'platform_id' }, { title: '提问人', key: 'requester_name' }, { title: '模式', key: 'mode' }, { title: '赞 / 踩', key: 'feedback' }, { title: '', key: 'actions', sortable: false }]

function formatTime(value: string) { return new Date(value).toLocaleString() }
function queryValue(value: string) { return value ? value : undefined }
async function load() {
  loading.value = true; error.value = ''
  try {
    const query = new URLSearchParams({ page: String(page.value), page_size: '20', include_tests: String(filters.value.include_tests) })
    for (const key of ['start_time', 'end_time'] as const) { const value = queryValue(filters.value[key]); if (value) query.set(key, new Date(value).toISOString()) }
    query.set('platform_id', filters.value.platform_id || '')
    query.set('requester', filters.value.requester || '')
    query.set('session_id', filters.value.session_id || '')
    query.set('vote', filters.value.vote || '')
    const response = await fetchWithAuth(`/api/v1/dingtalk-feedback?${query}`)
    if (!response.ok) throw new Error('无法加载反馈记录。')
    const payload = await response.json()
    items.value = payload.data.items; totalPages.value = payload.data.pagination.total_pages
    const statusResponse = await fetchWithAuth('/api/v1/dingtalk-feedback/preflight')
    if (statusResponse.ok) preflight.value = (await statusResponse.json()).data.adapters
  } catch (reason) { error.value = reason instanceof Error ? reason.message : '无法加载反馈记录。' } finally { loading.value = false }
}
function applyFilters() { page.value = 1; void load() }
onMounted(() => { void load() })
</script>

<style scoped>
.preflight-item { display: grid; gap: 4px; min-width: 200px; padding: 10px; border: 1px solid rgb(var(--v-theme-outline)); border-radius: 4px; font-size: 13px; }
.detail-meta { color: rgb(var(--v-theme-on-surface-variant)); font-size: 13px; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; font-family: inherit; margin: 8px 0 0; }
</style>
