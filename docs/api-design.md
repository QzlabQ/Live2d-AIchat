# API 接口设计

> Base URL: `http://localhost:8000/api/v1`  
> 认证：管理后台接口需 `Authorization: Bearer <token>`，游客端接口无需认证

---

## 游客端接口

### WebSocket：实时对话

**连接**：`WS /ws/chat/{session_id}`

#### 客户端 → 服务端消息

```typescript
// 文本输入
interface TextMessage {
  type: "text";
  content: string;
}

// 语音数据块（PCM 16kHz mono，每100ms一包）
interface AudioChunkMessage {
  type: "audio_chunk";
  data: string;          // base64 编码
  is_final: boolean;     // true = 本次说话结束，触发ASR
}

// 结束语音（强制触发ASR）
interface AudioEndMessage {
  type: "audio_end";
}
```

#### 服务端 → 客户端消息

```typescript
// LLM 文本流
interface TextDeltaMessage {
  type: "text_delta";
  content: string;       // 增量文本
}

// ASR识别结果（语音模式下回显）
interface AsrResultMessage {
  type: "asr_result";
  content: string;
}

// 音频块（TTS合成，分句流式返回）
interface AudioResponseMessage {
  type: "audio";
  data: string;          // base64 MP3
  seq: number;           // 顺序号，用于前端排队播放
}

// 音素时间戳（用于口型同步）
interface PhonemesMessage {
  type: "phonemes";
  seq: number;           // 对应 audio seq
  data: Array<{
    ph: string;          // 音素: "a"|"i"|"u"|"e"|"o"|"N"（闭口）
    start: number;       // 秒
    end: number;
  }>;
}

// 情感（驱动表情）
interface EmotionMessage {
  type: "emotion";
  value: "neutral" | "happy" | "thinking" | "excited" | "sad";
}

// 完成
interface DoneMessage {
  type: "done";
  session_id: string;
}

// 错误
interface ErrorMessage {
  type: "error";
  code: string;
  message: string;
}
```

---

### HTTP：会话管理

#### 创建会话

`POST /sessions`

```json
// Request
{
  "interest_tags": ["history", "nature"],  // 可选
  "device_type": "mobile"                  // mobile | kiosk
}

// Response 200
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

#### 获取推荐路线

`GET /sessions/{session_id}/recommend`

```json
// Response 200
{
  "routes": [
    {
      "name": "历史文化探索路线",
      "duration": "3小时",
      "spots": ["古城门", "博物馆", "历史街区"],
      "description": "适合对历史感兴趣的游客..."
    }
  ]
}
```

---

## 管理后台接口

### 认证

#### 登录

`POST /admin/auth/login`

```json
// Request
{ "username": "admin", "password": "..." }

// Response 200
{ "access_token": "eyJ...", "expires_in": 86400 }
```

---

### 知识库管理

#### 上传文档

`POST /admin/knowledge/upload`  
Content-Type: `multipart/form-data`

| 字段 | 类型 | 说明 |
|------|------|------|
| file | File | PDF/Word/TXT，最大50MB |
| category | string | `history` \| `scenery` \| `faq` \| `route` |

```json
// Response 202（异步处理）
{
  "doc_id": "uuid",
  "status": "processing",
  "message": "文档处理中，预计30秒完成"
}
```

#### 文档列表

`GET /admin/knowledge?page=1&size=20&category=history`

```json
{
  "total": 15,
  "items": [
    {
      "id": "uuid",
      "filename": "景区历史沿革.pdf",
      "category": "history",
      "chunk_count": 42,
      "status": "ready",
      "uploaded_at": "2026-07-01T10:00:00Z"
    }
  ]
}
```

#### 删除文档

`DELETE /admin/knowledge/{doc_id}`

```json
// Response 200
{ "message": "已删除文档及其 42 个向量片段" }
```

---

### 数字人配置

#### 获取配置

`GET /admin/avatar/config`

```json
{
  "model_path": "/live2d/models/guide/guide.model3.json",
  "voice_id": "cosyvoice_guide_v1",
  "persona": "你是「云溪」，景区专属AI导游，性格温柔活泼..."
}
```

#### 更新配置

`PUT /admin/avatar/config`

```json
// Request（字段均可选，只更新传入字段）
{
  "voice_id": "cosyvoice_female_warm",
  "persona": "你是「山灵」，..."
}

// Response 200
{ "message": "配置已更新" }
```

---

### 数据大屏

#### 大屏概览数据

`GET /admin/dashboard/overview?period=today`  
`period`: `today` | `week` | `month`

```json
{
  "service_count": 1284,
  "avg_satisfaction": 4.2,
  "avg_latency_ms": 2340,
  "top_questions": [
    { "question": "门票多少钱？", "count": 89 },
    { "question": "开放时间？", "count": 76 }
  ],
  "satisfaction_trend": [
    { "date": "2026-07-01", "score": 4.1 },
    { "date": "2026-07-02", "score": 4.3 }
  ]
}
```

#### 情感趋势

`GET /admin/dashboard/emotion?start=2026-07-01&end=2026-07-07`

```json
{
  "trend": [
    {
      "date": "2026-07-01",
      "happy": 0.62,
      "neutral": 0.30,
      "negative": 0.08
    }
  ]
}
```

---

### 感受度报告

#### 生成报告

`POST /admin/report/generate`

```json
// Request
{ "start_date": "2026-07-01", "end_date": "2026-07-07" }

// Response 200
{
  "report_id": "uuid",
  "summary": "本周共服务游客8960人次，整体满意度评分4.2/5.0...",
  "top_concerns": ["停车场位置", "餐饮价格", "景点讲解"],
  "keyword_cloud": [
    { "word": "历史", "weight": 156 },
    { "word": "风景", "weight": 134 }
  ],
  "suggestions": [
    "游客对停车场指引反馈较多，建议加强导引标识"
  ]
}
```

---

## 错误码规范

| code | 含义 |
|------|------|
| `AUTH_FAILED` | 未认证或token过期 |
| `KNOWLEDGE_PROCESSING` | 知识库处理中，暂不可查询 |
| `LLM_TIMEOUT` | 大模型响应超时（>10s） |
| `ASR_FAILED` | 语音识别失败（音频质量差） |
| `TTS_FAILED` | 语音合成失败（降级为纯文字） |
| `QUOTA_EXCEEDED` | API额度耗尽 |
