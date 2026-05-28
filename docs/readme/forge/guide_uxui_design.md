# UXUI Design Guide

Generate design tokens and UI component visual specs with UX evaluation from ASCII art screen layouts in requirements documents. Positioned as the **non-Figma complement to `/forge:start-requirements`**: used when you need to design UI from scratch without a Figma file or existing implementation. Design direction is acquired in Phase 2.0 (Design Intent) by reading the requirements document, inspecting existing code, or AI inference with user confirmation — no project-level mode config is involved.

## start-uxui-design

```
/forge:start-uxui-design [feature] [--platform ios|macos]
```

| Argument     | Description                                      |
| ------------ | ------------------------------------------------ |
| `feature`    | Feature name (omit for interactive)              |
| `--platform` | `ios` / `macos` (omit for interactive selection) |

### When to Use

- After requirements documents are complete, before creating design docs
- When building a design system for iOS / macOS apps
- When you need theory-backed UI without a designer

### Pipeline Position

```
start-requirements → start-uxui-design → start-design → start-plan → start-implement
 (what to build)       (how it looks)      (how to build)  (when)        (build)
```

start-uxui-design is optional. Skip it and go straight to start-design if design tokens are not needed.

### Usage Examples

```bash
# Generate design for iOS app
/forge:start-uxui-design user-auth --platform ios

# macOS app, Feature name decided interactively
/forge:start-uxui-design --platform macos
```

---

## 3-Layer Integrated Framework

The foundation for all design decisions. Applied bottom-up; upper layers cannot override lower layers.

| Layer                          | Role              | Examples                                  | Constraint                                   |
| ------------------------------ | ----------------- | ----------------------------------------- | -------------------------------------------- |
| Layer 1: Cognitive constraints | Obey (inviolable) | Fitts's law, Hick's law, contrast ratio   | Designs violating this layer are rejected    |
| Layer 2: Structural tools      | Combine           | Modular scale, color harmony, 8pt grid    | Combinations that break Layer 1 are rejected |
| Layer 3: Aesthetic direction   | Choose            | Dieter Rams, Don Norman, Tufte, wabi-sabi | Free within Layers 1 & 2                     |

---

## Workflow

| Phase | What                                                                                               | Knowledge Base                             |
| ----- | -------------------------------------------------------------------------------------------------- | ------------------------------------------ |
| 1     | Requirements intake (ASCII art analysis)                                                           | —                                          |
| 2.0   | **Design Intent acquisition** (requirements body → existing code → AI inference + AskUserQuestion) | design_philosophy.md                       |
| 2     | Design direction (tension, reference culture, divergence — conditional on Design Intent)           | design_philosophy.md                       |
| 3     | Design token creation (color, typography, spacing, signature rules)                                | apple_design_principles.md, platform guide |
| 4     | Component visual design (ASCII → HIG-compliant components)                                         | Platform guide, templates                  |
| 5     | UX self-evaluation (3-layer framework + distinctiveness / memorability, conditional)               | design_philosophy.md                       |
| 6     | Document generation & quality check (`/forge:review uxui --auto`)                                  | review_criteria_uxui.md                    |

### Design Intent-driven branching

Phase 2.0 acquires a structured Design Intent (user experience, tension axis, distinctiveness importance, references, anti-goals, signature requirement). The values determine which Phases activate:

| Design Intent                                                        | Branch                                    |
| -------------------------------------------------------------------- | ----------------------------------------- |
| `distinctiveness.importance: low` & `signature_required: none`       | Skip Phase 2.2-2.5, 3.5, 4.5, 5.4         |
| `distinctiveness.importance: medium`                                 | Run Phase 2.2 and 2.5, simplified 2.3-2.4 |
| `distinctiveness.importance: high` or `signature_required: required` | Run all phases fully                      |

No mode abstraction (stable/bold) is introduced. Branching follows naturally from Design Intent content.

### Reference images (optional)

Competitor screenshots and mood-board images can be placed under `{specs_root}/{feature}/requirements/uxui_references/{competitors,inspirations}/`. If present, Phase 5.4 review adds image-based similarity and integrity checks. `.gitignore` excludes competitor/inspiration images by default (copyright safety).

### Output

| Document               | ID scheme | Content                                                      |
| ---------------------- | --------- | ------------------------------------------------------------ |
| Design tokens          | THEME-xxx | Colors, typography, spacing, elevation                       |
| Component visual specs | CMP-xxx   | Visual design per UI component (sizes, states, interactions) |

---

## UX Review

Standalone review via `/forge:review uxui` is also available. Verifies against 4 perspectives in this priority order (higher overrides lower when they conflict):

| # | Perspective         | Focus                                                                  | Application                                                                                    |
| - | ------------------- | ---------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| 1 | **hig_compliance**  | Apple HIG 4 principles compliance                                      | Always                                                                                         |
| 2 | **usability**       | Nielsen heuristics, accessibility                                      | Always                                                                                         |
| 3 | **visual_system**   | Token consistency, Gestalt principles                                  | Always                                                                                         |
| 4 | **distinctiveness** | Differentiation, memorability, signature elements, anti-goal adherence | Conditional on Design Intent (auto-demoted to 🟢 when not specified or when importance is low) |

When `/forge:review uxui` runs without prior start-uxui-design output, Design Intent is inferred from the target document and shown as a prefix before findings. Distinctiveness criteria are AI-verifiable (no "5-second look" / "compare 5 competitors" style checks).

```bash
# Review design tokens and component specs
/forge:review uxui --files specs/user-auth/design/

# With auto-fix
/forge:review uxui --files specs/user-auth/design/ --auto
```

---

## Usage Scenarios

For detailed scenarios, see [uxui_scenario.md](../uxui_scenario.md).

| Scenario                    | Summary                                           |
| --------------------------- | ------------------------------------------------- |
| New iOS app                 | Build a design system from scratch                |
| Existing app UI unification | Migrate existing components to token-based        |
| macOS app                   | Generate tokens specialized for macOS HIG         |
| Design review only          | Review existing design specs from UX perspectives |
| Post-requirements update    | Update tokens after ASCII art changes             |
