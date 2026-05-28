# Document Creation Guide

Create development documents in three stages: requirements → design → plan. Each skill takes the previous stage's output as input and ends with a common completion flow: AI review → ToC update → commit.

```
start-requirements → start-design → start-plan → start-implement
 (what to build)      (how to build)   (when)        (build)
```

## Common Mechanisms

### Context Gathering

All three skills share a common context-gathering pattern. Before document creation, parallel agents collect:

| Agent       | Target                                     | Output            |
| ----------- | ------------------------------------------ | ----------------- |
| specs agent | Specifications (requirements, design docs) | `refs/specs.yaml` |
| rules agent | Project rule documents                     | `refs/rules.yaml` |
| code agent  | Existing implementations                   | `refs/code.yaml`  |

### Completion Flow

After document creation, the following steps execute sequentially:

1. `/forge:review {type} --auto` — AI review + auto-fix
2. `/forge:update-db-specs` — ToC update (when available)
3. `/anvil:commit` — commit/push confirmation

---

## start-requirements

Create requirements documents. Supports three modes with different input sources.

```
/forge:start-requirements [feature] [--mode interactive|reverse-engineering|from-figma] [--new|--add]
```

| Argument  | Description                         |
| --------- | ----------------------------------- |
| `feature` | Feature name (omit for interactive) |
| `--mode`  | Mode selection (omit for menu)      |
| `--new`   | New app                             |
| `--add`   | Adding features to existing app     |

### Mode Selection Guide

| Mode                  | Input source         | When to use                         | Prerequisites         |
| --------------------- | -------------------- | ----------------------------------- | --------------------- |
| `interactive`         | User dialog          | Defining requirements from scratch  | `.doc_structure.yaml` |
| `reverse-engineering` | Existing source code | Documenting existing code           | Source code           |
| `from-figma`          | Figma design files   | Extracting requirements from design | Figma MCP environment |

### Usage Examples

```bash
# Define requirements from scratch
/forge:start-requirements user-auth --mode interactive --new

# Reverse-engineer from existing code
/forge:start-requirements dashboard --mode reverse-engineering --add

# Extract from Figma design
/forge:start-requirements product-catalog --mode from-figma --new
```

### Execution Flow

1. Confirm mode, Feature name, and new/add
2. Create session (real-time progress in browser)
3. Context gathering (parallel)
4. Mode-specific workflow (dialog / source analysis / Figma analysis)
5. Completion flow (review → ToC → commit)

### Output

Generates requirements documents (Markdown) in `specs/{feature}/requirements/`. ID scheme:

| Prefix  | Type                        |
| ------- | --------------------------- |
| APP-xxx | App overview & policies     |
| SCR-xxx | Screen specifications       |
| FNC-xxx | Functional specifications   |
| NFR-xxx | Non-functional requirements |

### Reference Documents

- `plugins/forge/docs/requirement_format.md` — Requirements template
- `plugins/forge/docs/spec_format.md` — ID classification catalog
- `plugins/forge/docs/spec_design_boundary_spec.md` — Requirements/design boundary guide

---

## start-design

Create design documents from requirements. Emphasizes reuse of existing implementation assets.

```
/forge:start-design [feature]
```

| Argument  | Description                         |
| --------- | ----------------------------------- |
| `feature` | Feature name (omit for interactive) |

### When to Use

- After requirements documents are complete
- When you want to document architecture and module structure

### Execution Flow

1. Confirm Feature name
2. **Context gathering** (3 agents in parallel)
   - Retrieve requirements docs (`/query-specs`)
   - Collect project design rules (`/query-rules`)
   - Explore existing implementation assets (codebase scan)
3. Detailed requirements analysis
4. Create design document (ID assignment, format application)
5. Completion flow (review → ToC → commit)

### Design Principles

- **Existing assets first**: Reuse available components instead of creating new ones
- **What/How boundary**: Clearly separate requirements (what) from design (how)
- **Traceability**: Every requirement must be traceable to a design section

### Output

Generates design documents (Markdown) in `specs/{feature}/design/`. ID scheme: `DES-xxx`

### Reference Documents

- `plugins/forge/docs/design_format.md` — Design document template
- `plugins/forge/docs/design_principles_spec.md` — Design principles guide
- `plugins/forge/docs/spec_design_boundary_spec.md` — What/How boundary

---

## start-plan

Extract tasks from design documents and create a YAML plan.

```
/forge:start-plan [feature]
```

| Argument  | Description                         |
| --------- | ----------------------------------- |
| `feature` | Feature name (omit for interactive) |

### When to Use

- After design documents are complete
- When planning task breakdown and scheduling

### Execution Flow

1. Confirm Feature name
2. **Context gathering** (2 agents in parallel)
   - Retrieve requirements + design docs
   - Collect plan rules
3. Check for existing plan (update mode)
4. Create/update plan (task extraction → granularity check → ID assignment)
5. Completion flow (review → ToC → commit)

### Task Granularity Criteria

| Criterion    | Requirement                                              |
| ------------ | -------------------------------------------------------- |
| Unit         | A single agent can execute and complete it independently |
| Volume       | 5–10 actionable items per task                           |
| Completeness | Build and test must pass at task completion              |
| File scope   | 1 file or 2–3 closely related files                      |

### Plan Structure (Minimal Complete YAML)

The plan is a YAML file named `{feature}_plan.yaml`. **It is not Markdown.**
The top level has exactly four keys: `requirements_traceability` / `design_traceability` / `tasks` / `revision_history` (per the canonical schema in `plan_format.md`).

```yaml
# {feature} implementation plan

# === Traceability ===
requirements_traceability:
  - requirement_id: REQ-001
    title: Requirement title
    design_id: DES-001
    status: pending # pending / completed

design_traceability:
  - design_id: DES-001
    title: Design title
    requirement_ids:
      - REQ-001
    task_ids:
      - TASK-001

# === Tasks ===
tasks:
  - task_id: TASK-001
    title: Task name
    priority: 90 # High:70-99, Mid:40-69, Low:1-39
    status: pending # pending / in_progress / completed
    design_id: DES-001 # null when no design (not "-")
    depends_on: [] # Array of dependency task IDs. Use [] when none.
    group_id: null # null for independent tasks, e.g. "GROUP-001 (1/3)"
    build_check: per_task # per_task / skip / on_group_complete
    description:
      - Action item 1
      - Action item 2
    acceptance_criteria: Yes/No-judgable acceptance criteria # null when none
    required_reading: # Array of required reading paths. Use [] when none.
      - specs/{feature}/design/DES-001_xxx.md

# === Revision history ===
revision_history:
  - date: "2026-03-15"
    content: Initial revision
```

### Key Principles

- `description` should reference the design doc section, not contain implementation details
- `design_id` is `null` when absent (never `-` or `"-"`)
- `depends_on` / `required_reading` use `[]` when empty (never `null` or `-`)
- `build_check` must be one of `per_task` / `skip` / `on_group_complete`
- Dependencies must not form cycles
- The traceability matrix must verify all requirements and designs are covered

### Output

Generates the plan (YAML) at `specs/{feature}/plan/{feature}_plan.yaml`. **A Markdown plan is never emitted.**
A Claude Code plan-mode Markdown plan is a different artifact; if you want to derive requirements and design from one, use `/forge:create-feature-from-markdown-plan`.

### Reference Documents

- `plugins/forge/docs/plan_format.md` — Plan YAML schema
- `plugins/forge/docs/plan_principles_spec.md` — Task granularity and grouping guide
