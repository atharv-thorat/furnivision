-- FurniVision database schema (PostgreSQL)
-- Covers: users/projects, room capture, agent execution trail (for the
-- LangGraph pipeline), design versions, and the furniture/material catalog.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email           TEXT UNIQUE NOT NULL,
    name            TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE projects (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    budget_max      NUMERIC(10, 2),
    style_prefs     JSONB DEFAULT '{}',   -- free-form onboarding preferences
    status          TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending','analyzing_room','designing',
                                           'planning','rendering','done','error')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE rooms (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id      UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    image_urls      TEXT[] NOT NULL DEFAULT '{}',
    dimensions      JSONB,               -- {"width_m":.., "length_m":.., "height_m":..}
    obstacles       JSONB DEFAULT '[]',  -- windows, doors, outlets, fixed fixtures
    detected_style  TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One row per LangGraph node execution — gives you a full audit/replay trail
-- of the agentic pipeline, including the ReAct scratchpad for that step.
CREATE TABLE agent_runs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id      UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    agent_name      TEXT NOT NULL
                        CHECK (agent_name IN ('room_intelligence','design_material',
                                               'planning_optimization','visualization')),
    status          TEXT NOT NULL DEFAULT 'running'
                        CHECK (status IN ('running','succeeded','failed')),
    input_state     JSONB,               -- state snapshot going in
    output_state    JSONB,               -- state slice produced
    messages        JSONB DEFAULT '[]',  -- ReAct message trace for this node
    tool_calls      JSONB DEFAULT '[]',  -- structured log of tool name + args + result
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ,
    error            TEXT
);

CREATE TABLE materials (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            TEXT NOT NULL,
    category        TEXT,                -- fabric, wood, stone, paint, etc.
    color_hex       TEXT,
    unit_cost       NUMERIC(10, 2),
    metadata        JSONB DEFAULT '{}'
);

CREATE TABLE furniture_items (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            TEXT NOT NULL,
    category        TEXT,                -- sofa, table, storage, lighting, etc.
    dimensions      JSONB,               -- {"width_cm":.., "depth_cm":.., "height_cm":..}
    price           NUMERIC(10, 2),
    material_id     UUID REFERENCES materials(id),
    vendor_url      TEXT,
    model_asset_url TEXT,                -- GLB/glTF 3D model, built to true real-world scale, for AR
    metadata        JSONB DEFAULT '{}'
);

-- A design_version is a full, versioned snapshot of one pipeline pass.
-- Lets users compare/regenerate designs without losing prior attempts.
CREATE TABLE design_versions (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id          UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    version_number      INT NOT NULL,
    parent_version_id   UUID REFERENCES design_versions(id),  -- null if this was a full run
    regenerated_agents  TEXT[] DEFAULT '{}',  -- which agents actually ran fresh vs inherited
    design_concepts     JSONB,               -- palette, materials, style rationale
    furniture_plan      JSONB,               -- chosen items + placements
    total_cost          NUMERIC(10, 2),
    render_urls         TEXT[] DEFAULT '{}',
    scene_ref           TEXT,                -- pointer to 3D scene file / asset
    ar_scene_manifest   JSONB,               -- {item_id, model_asset_url, position, rotation}[] for the AR client
    is_favorite         BOOLEAN NOT NULL DEFAULT false,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (project_id, version_number)
);

-- Join table: which furniture_items were used in a given design version,
-- with the specific placement for that item.
CREATE TABLE design_version_items (
    design_version_id  UUID NOT NULL REFERENCES design_versions(id) ON DELETE CASCADE,
    furniture_item_id  UUID NOT NULL REFERENCES furniture_items(id),
    position            JSONB,           -- {"x":.., "y":.., "rotation_deg":..}
    PRIMARY KEY (design_version_id, furniture_item_id)
);

CREATE INDEX idx_agent_runs_project ON agent_runs(project_id, started_at);
CREATE INDEX idx_design_versions_project ON design_versions(project_id, version_number);
CREATE INDEX idx_rooms_project ON rooms(project_id);
