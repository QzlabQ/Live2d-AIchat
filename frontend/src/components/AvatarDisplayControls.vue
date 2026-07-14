<script setup lang="ts">
import { computed } from 'vue'

import {
  AVATAR_DISPLAY_LIMITS,
  clampAvatarDisplayConfig,
  type AvatarDisplayConfig,
} from '../lib/avatarDisplay'

const props = withDefaults(
  defineProps<{
    modelValue: AvatarDisplayConfig
    compact?: boolean
    showOffsetX?: boolean
    showOffsetY?: boolean
    showStageHeight?: boolean
  }>(),
  {
    compact: false,
    showOffsetX: true,
    showOffsetY: true,
    showStageHeight: true,
  },
)

const emit = defineEmits<{
  (event: 'update:modelValue', value: AvatarDisplayConfig): void
  (event: 'reset'): void
}>()

const displayConfig = computed(() => clampAvatarDisplayConfig(props.modelValue))

function updateField(key: keyof AvatarDisplayConfig, rawValue: string | number) {
  emit(
    'update:modelValue',
    clampAvatarDisplayConfig({
      ...props.modelValue,
      [key]: Number(rawValue),
    }),
  )
}
</script>

<template>
  <div class="avatar-display-controls" :class="{ 'avatar-display-controls-compact': compact }">
    <label>
      <span>模型缩放</span>
      <output>{{ displayConfig.displayScale.toFixed(2) }}</output>
      <input
        type="range"
        :min="AVATAR_DISPLAY_LIMITS.displayScale.min"
        :max="AVATAR_DISPLAY_LIMITS.displayScale.max"
        step="0.01"
        :value="displayConfig.displayScale"
        @input="updateField('displayScale', ($event.target as HTMLInputElement).value)"
      />
    </label>

    <label v-if="showOffsetX">
      <span>水平偏移</span>
      <output>{{ displayConfig.displayOffsetX.toFixed(2) }}</output>
      <input
        type="range"
        :min="AVATAR_DISPLAY_LIMITS.displayOffsetX.min"
        :max="AVATAR_DISPLAY_LIMITS.displayOffsetX.max"
        step="0.01"
        :value="displayConfig.displayOffsetX"
        @input="updateField('displayOffsetX', ($event.target as HTMLInputElement).value)"
      />
    </label>

    <label v-if="showOffsetY">
      <span>垂直偏移</span>
      <output>{{ displayConfig.displayOffsetY.toFixed(2) }}</output>
      <input
        type="range"
        :min="AVATAR_DISPLAY_LIMITS.displayOffsetY.min"
        :max="AVATAR_DISPLAY_LIMITS.displayOffsetY.max"
        step="0.01"
        :value="displayConfig.displayOffsetY"
        @input="updateField('displayOffsetY', ($event.target as HTMLInputElement).value)"
      />
    </label>

    <label v-if="showStageHeight">
      <span>舞台高度</span>
      <output>{{ Math.round(displayConfig.stageHeight) }}px</output>
      <input
        type="range"
        :min="AVATAR_DISPLAY_LIMITS.stageHeight.min"
        :max="AVATAR_DISPLAY_LIMITS.stageHeight.max"
        step="1"
        :value="displayConfig.stageHeight"
        @input="updateField('stageHeight', ($event.target as HTMLInputElement).value)"
      />
    </label>

    <button type="button" class="avatar-display-reset" @click="emit('reset')">
      重置显示
    </button>
  </div>
</template>
