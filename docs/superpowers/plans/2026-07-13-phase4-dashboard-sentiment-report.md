# Phase 4 数据大屏与感受度报告 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 补齐管理后台的 phase4 能力，提供可视化数据大屏与可按日期筛选的感受度报告页。

**Architecture:** 后端新增轻量聚合接口，基于现有 `sessions`、`messages` 和 `daily_emotion_reports` 生成大屏所需的 KPI、情绪趋势和热门问题。前端在现有管理后台中增加独立“大屏”页与“感受度报告”页，复用当前登录、筛选和日报接口，尽量不改动已有管理能力。

**Tech Stack:** FastAPI、SQLAlchemy、Pydantic、Vue 3、TypeScript、现有后台样式系统、原生 SVG/CSS 图表。

---

### Task 1: 后端大屏聚合接口

**Files:**
- Create: `backend/app/schemas/dashboard.py`
- Create: `backend/app/services/dashboard.py`
- Create: `backend/app/api/routes/dashboard.py`
- Modify: `backend/app/api/router.py`
- Test: `backend/tests/test_dashboard_api.py`

- [x] **Step 1: Write the failing test**

```python
async def test_dashboard_overview_and_emotion_endpoints():
    ...
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_dashboard_api -v`
Expected: 路由不存在或响应结构不匹配。

- [x] **Step 3: Write minimal implementation**

```python
@router.get("/admin/dashboard/overview")
@router.get("/admin/dashboard/emotion")
```

- [x] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_dashboard_api -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/dashboard.py backend/app/services/dashboard.py backend/app/api/routes/dashboard.py backend/app/api/router.py backend/tests/test_dashboard_api.py
git commit -m "feat: add admin dashboard aggregation"
```

### Task 2: 前端数据大屏页

**Files:**
- Modify: `frontend/src/AdminApp.vue`
- Modify: `frontend/src/services/adminApi.ts`
- Modify: `frontend/src/types/admin.ts`
- Modify: `frontend/src/admin.css`
- Test: `frontend/src/AdminApp.vue` (build via `npm run build`)

- [x] **Step 1: Write the failing test**

```ts
// 目标：dashboard 页面能渲染 KPI、趋势图和热门问题列表
```

- [x] **Step 2: Run test to verify it fails**

Run: `npm run build`
Expected: 缺少 dashboard 页面/类型/接口导致构建或类型错误。

- [x] **Step 3: Write minimal implementation**

```vue
<div v-else-if="activePage === 'dashboard'">
  ...
</div>
```

- [x] **Step 4: Run test to verify it passes**

Run: `npm run build`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/AdminApp.vue frontend/src/services/adminApi.ts frontend/src/types/admin.ts frontend/src/admin.css
git commit -m "feat: add admin dashboard page"
```

### Task 3: 感受度报告页增强

**Files:**
- Modify: `frontend/src/AdminApp.vue`
- Modify: `frontend/src/services/adminApi.ts`
- Modify: `frontend/src/types/admin.ts`
- Modify: `frontend/src/admin.css`
- Test: `frontend/src/AdminApp.vue` (build via `npm run build`)

- [x] **Step 1: Write the failing test**

```ts
// 目标：报告页能按日期筛选、展示情绪趋势、摘要和关注点
```

- [x] **Step 2: Run test to verify it fails**

Run: `npm run build`
Expected: 报告页缺少趋势图/筛选联动或类型错误。

- [x] **Step 3: Write minimal implementation**

```vue
<section class="admin-report-chart">
  ...
</section>
```

- [x] **Step 4: Run test to verify it passes**

Run: `npm run build`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/AdminApp.vue frontend/src/services/adminApi.ts frontend/src/types/admin.ts frontend/src/admin.css
git commit -m "feat: enhance admin sentiment report"
```

### Task 4: 验证与文档

**Files:**
- Modify: `backend/README.md`
- Modify: `docs/roadmap.md`
- Test: `backend/tests/test_dashboard_api.py`
- Test: `npm run build`

- [x] **Step 1: Run backend and frontend verification**

```bash
python -m unittest tests.test_dashboard_api -v
npm run build
```

- [x] **Step 2: Update docs**

```md
- 新增 dashboard 接口说明
- 说明大屏与感受度报告的数据来源
```

- [ ] **Step 3: Commit**

```bash
git add backend/README.md docs/roadmap.md
git commit -m "docs: record phase4 dashboard and report"
```
