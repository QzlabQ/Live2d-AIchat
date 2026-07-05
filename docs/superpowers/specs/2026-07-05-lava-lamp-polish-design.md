# Lava Lamp Polish Design

## Goal

Refine the Phase 2 emotion lava lamp so it more clearly communicates `preview` vs `final` emotion states while keeping the visual style stable and presentation-friendly.

## Scope

This change is frontend-only and limited to the existing lava lamp card. It does not change backend WebSocket payloads, emotion categories, or Live2D behavior.

## Design

### 1. Stage Contrast

- `preview` uses a softer pulse, smaller glow radius, and slightly lower opacity.
- `final` uses a steadier brighter lamp body with only subtle fluid motion.
- The UI continues to show the current stage label in text for debugging.

### 2. Emotion Personality

- `happy`: warm and smooth, medium glow, calm motion.
- `thinking`: cooler tone, slightly slower wave motion, restrained glow.
- `excited`: brightest state, but without aggressive flicker or jitter.
- `sad`: dimmer and more compact, slowest motion.
- `neutral`: baseline state with the least visual emphasis.

### 3. Implementation Shape

- Keep the existing lamp markup in `frontend/src/App.vue`.
- Add computed style variables for glow strength, pulse amplitude, opacity, and animation speed.
- Update `frontend/src/style.css` so the lamp body, fluid layers, and core react to those CSS variables.
- Preserve mobile layout and current telemetry text.

## Error Handling

- If stage metadata is missing, treat it as `final`.
- If an unknown emotion is received, fall back to the existing `neutral` visual preset.

## Testing

- Run `npm run build`.
- Manually verify that:
  - `preview` looks softer than `final`
  - switching between emotions remains smooth
  - the lamp still renders correctly on the existing telemetry card layout
