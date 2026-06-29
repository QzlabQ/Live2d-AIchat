# 口型同步方案

> 口型同步是本赛题技术分的核心亮点，需要重点打磨。

---

## 原理概述

```
TTS 合成音频
    ↓
提取音素时间戳（每个音素的起止时间）
    ↓
映射为 Live2D 口型参数值
    ↓
前端按时间轴驱动参数动画
```

---

## CosyVoice 2 音素时间戳

CosyVoice 2 合成时可返回对齐信息：

```python
from cosyvoice.cli.cosyvoice import CosyVoice2

cosyvoice = CosyVoice2("pretrained_models/CosyVoice2-0.5B")

result = cosyvoice.inference_sft(
    text="欢迎来到云溪景区，这里山清水秀",
    spk_id="中文女",
    stream=False
)

# result 包含：
# - result["audio"]：PCM音频数据
# - result["alignment"]：音素对齐列表
#   [{"ph": "h", "start": 0.05, "end": 0.12},
#    {"ph": "uan", "start": 0.12, "end": 0.28}, ...]
```

### 降级方案（Edge-TTS 无时间戳）

Edge-TTS 不提供音素时间戳，用**音量包络**近似驱动：

```python
import numpy as np

def audio_to_mouth_curve(audio_pcm: np.ndarray, sr=22050, fps=60) -> list[float]:
    """将PCM音频转换为每帧的嘴巴开合度（0~1）"""
    frame_size = sr // fps
    frames = []
    for i in range(0, len(audio_pcm) - frame_size, frame_size):
        chunk = audio_pcm[i:i + frame_size].astype(float)
        rms = np.sqrt(np.mean(chunk ** 2))
        # 归一化到 0~1，用指数映射使小声音更自然
        mouth_open = min(1.0, (rms / 3000) ** 0.6)
        frames.append(mouth_open)
    return frames
```

---

## 音素 → Live2D 参数映射

### Live2D 口型相关参数

| 参数名 | 范围 | 含义 |
|--------|------|------|
| `ParamMouthOpenY` | 0~1 | 嘴巴上下开合度 |
| `ParamMouthForm` | -1~1 | 嘴型（-1=圆/O，0=中性，1=宽/扁） |

### 中文音素映射表

中文发音的嘴型可以简化为5个口型（类似 Preston Blair 系统）：

| 口型 | 代表音素 | `MouthOpenY` | `MouthForm` |
|------|---------|-------------|------------|
| **A** | a, ia, ua | 0.9 | 0.0 |
| **I** | i, yi, ie | 0.4 | 0.8 |
| **U** | u, wu, uo | 0.6 | -0.8 |
| **E** | e, er, en | 0.5 | 0.3 |
| **N** | 静音/辅音 | 0.05 | 0.0 |

```python
PHONEME_TO_MOUTH: dict[str, tuple[float, float]] = {
    # (MouthOpenY, MouthForm)
    "a": (0.9, 0.0), "ia": (0.9, 0.0), "ua": (0.85, 0.0),
    "i": (0.4, 0.8), "yi": (0.4, 0.8),
    "u": (0.6, -0.8), "wu": (0.6, -0.8), "uo": (0.55, -0.5),
    "e": (0.5, 0.3), "er": (0.5, 0.2), "en": (0.4, 0.1),
    "o": (0.7, -0.6), "ou": (0.5, -0.4),
    "N": (0.05, 0.0),   # 闭口（默认）
}

def phoneme_to_params(ph: str) -> tuple[float, float]:
    # 降级：取音素首字符匹配
    return PHONEME_TO_MOUTH.get(ph) \
        or PHONEME_TO_MOUTH.get(ph[0] if ph else "N") \
        or PHONEME_TO_MOUTH["N"]
```

---

## 前端驱动实现（TypeScript）

### 时间轴调度器

```typescript
interface PhonemeFrame {
  ph: string;
  start: number;   // 秒
  end: number;
}

class LipSyncController {
  private model: Live2DModel;
  private frames: PhonemeFrame[] = [];
  private startTime = 0;
  private rafId = 0;

  // 接收后端返回的音素数据 + 音频开始播放时间
  start(frames: PhonemeFrame[], audioStartTime: number) {
    this.frames = frames;
    this.startTime = audioStartTime;
    this.rafId = requestAnimationFrame(this.tick.bind(this));
  }

  private tick(now: number) {
    const elapsed = (now - this.startTime) / 1000;  // 转为秒

    // 找当前时刻对应的音素
    const frame = this.frames.find(f => elapsed >= f.start && elapsed < f.end);
    const ph = frame?.ph ?? "N";

    const [openY, form] = phonemeToParams(ph);
    this.setMouth(openY, form);

    if (elapsed < this.frames.at(-1)!.end + 0.2) {
      this.rafId = requestAnimationFrame(this.tick.bind(this));
    } else {
      this.setMouth(0.05, 0);  // 结束后闭嘴
    }
  }

  private setMouth(openY: number, form: number) {
    // Live2D 参数 ID 因模型而异，需确认模型中的参数名
    this.model.internalModel.coreModel.setParameterValueById(
      "ParamMouthOpenY", openY
    );
    this.model.internalModel.coreModel.setParameterValueById(
      "ParamMouthForm", form
    );
  }

  stop() {
    cancelAnimationFrame(this.rafId);
    this.setMouth(0.05, 0);
  }
}
```

### 平滑插值（避免口型突变）

```typescript
// 对目标值做线性插值，避免帧间跳变
private currentOpenY = 0.05;
private currentForm = 0.0;
private readonly LERP_FACTOR = 0.35;   // 越小越平滑，越大越跟随精准

private setMouth(targetOpenY: number, targetForm: number) {
  this.currentOpenY += (targetOpenY - this.currentOpenY) * this.LERP_FACTOR;
  this.currentForm += (targetForm - this.currentForm) * this.LERP_FACTOR;

  this.model.internalModel.coreModel.setParameterValueById(
    "ParamMouthOpenY", this.currentOpenY
  );
  this.model.internalModel.coreModel.setParameterValueById(
    "ParamMouthForm", this.currentForm
  );
}
```

---

## 表情驱动

### 情感 → Live2D 参数映射

```typescript
const EMOTION_PARAMS: Record<string, Record<string, number>> = {
  happy: {
    ParamBrowLY: 0.5,    // 眉毛上扬
    ParamBrowRY: 0.5,
    ParamEyeLSmile: 1.0, // 眼睛微笑
    ParamEyeRSmile: 1.0,
  },
  thinking: {
    ParamBrowLAngle: -0.5,  // 眉头微蹙
    ParamBrowRAngle: -0.3,
    ParamEyeLY: -0.2,       // 眼神轻微下移
  },
  excited: {
    ParamBrowLY: 0.8,
    ParamBrowRY: 0.8,
    ParamEyeOpenL: 1.5,     // 眼睛睁大
    ParamEyeOpenR: 1.5,
  },
  neutral: {
    // 所有参数恢复默认值 0
  }
};

function applyEmotion(model: Live2DModel, emotion: string) {
  const params = EMOTION_PARAMS[emotion] ?? EMOTION_PARAMS.neutral;
  Object.entries(params).forEach(([id, value]) => {
    model.internalModel.coreModel.setParameterValueById(id, value);
  });
}
```

> ⚠️ 参数 ID 因 Live2D 模型而异，需打开模型文件（`.model3.json`）查阅实际参数列表，并对照调整上表中的 ID 名称。

---

## 闲置动画

数字人无对话时播放自然的"呼吸+微动"动画，避免僵硬感：

```typescript
// 使用 Live2D 内置动作或自定义循环参数
function playIdleAnimation(model: Live2DModel) {
  // 方式1：播放模型自带的 idle 动作
  model.motion("idle");

  // 方式2：若无内置idle，手动做正弦摆动
  let t = 0;
  setInterval(() => {
    t += 0.03;
    model.internalModel.coreModel.setParameterValueById(
      "ParamBodyAngleX", Math.sin(t) * 3   // 身体左右微摆
    );
    model.internalModel.coreModel.setParameterValueById(
      "ParamBreath", (Math.sin(t * 0.5) + 1) / 2   // 呼吸
    );
  }, 16);  // ~60fps
}
```

---

## 调试技巧

1. **参数调试面板**：开发时在页面叠加滑动条实时调节各参数，找到最佳嘴型映射值
2. **慢放测试**：将音频播放速率设为0.5x，观察口型是否对应正确音素
3. **录屏比对**：录制数字人说话视频，逐帧与音频波形对比，调整LERP_FACTOR
