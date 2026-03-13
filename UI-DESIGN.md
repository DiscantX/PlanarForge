# Planar Forge --- Area Editor UI & Scene Architecture Design

## Purpose of This Document

This document describes the current design direction for the **Planar
Forge area editor UI and scene architecture**.\
It summarizes concepts discussed during early planning so that both
developers and automated systems can understand:

-   The intended editor workflow
-   Internal scene representation
-   User-facing editing tools
-   Long‑term extensibility considerations

This document does **not** define final implementation details. Some
sections represent experimental or optional systems that may evolve.

------------------------------------------------------------------------

# 1. Infinity Engine Area Resource Dependencies

Infinity Engine areas are composed of multiple interdependent resources
that together define how an area renders and behaves.

Example resource set:

AR0001.TIS -- Area tileset graphics\
AR0001.WED -- Tile layout, wall groups, overlays, door tiles\
AR0001.MOS -- Minimap image (unused in BGEE)\
AR0001.ARE -- Area definition (animations, actors, containers,
triggers)\
AR0001SR.BMP -- Search map (walkability / interaction boundaries)\
AR0001LM.BMP -- Light map\
AR0001HT.BMP -- Height map\
AR0001.BCS -- Area script

These files function together to form the final playable area.

### Editor Implication

The editor must treat an area not as a single file but as a **compound
asset** composed of several synchronized resources.

Editing operations may affect multiple files simultaneously.

Example:

Placing a prop might modify:

-   TIS tiles
-   WED layout
-   search map pixels
-   height map pixels

Therefore the editor must maintain an **internal representation of the
scene** that can later compile into these engine formats.

------------------------------------------------------------------------

# 2. Internal Scene Representation

The editor should not operate directly on Infinity Engine data
structures.

Instead, it should maintain an **editor-native scene model** that
compiles to the engine's file formats during export.

This abstraction allows the editor to:

-   Support modern editing workflows
-   Provide features that the original engine never supported
-   Maintain undo/redo safety
-   Enable higher level tools

The scene model acts as a **compilation layer** between the editor and
the Infinity Engine.

------------------------------------------------------------------------

# 3. Scene Tree (Hierarchy System)

A scene hierarchy similar to the structure used in modern game engines
is recommended.

The hierarchy provides a clear overview of objects present in the area
and enables easier editing and organization.

Example scene tree:

Area ├ Terrain ├ Props │ ├ Table_01 │ ├ Tree_02 │ └ Barrel_03 ├ Actors │
├ Minsc │ └ Guard_01 ├ Containers ├ Regions ├ Triggers └ Lights

### Goals

The scene tree allows users to:

-   View all objects in the scene
-   Select objects quickly
-   Toggle visibility
-   Lock layers for editing
-   Organize complex areas

### Implementation Scope

A **simple hierarchical structure** is sufficient.

Objects should usually exist within category nodes but **not parent each
other arbitrarily**.

Example simplified structure:

Area ├ Props ├ Actors ├ Containers ├ Regions

This avoids unnecessary complexity while still providing organizational
benefits.

------------------------------------------------------------------------

# 4. Component-Based Object Model

Objects in the scene should expose editable properties through a
**component system**.

Scene Tree = object hierarchy\
Inspector = object components

Example:

Scene Node: Table_01

Inspector Components:

Transform\
Sprite\
Collision Polygon\
Search Map Effect\
Height Offset

Components represent features of the object rather than additional scene
nodes.

This keeps the hierarchy readable and prevents clutter.

------------------------------------------------------------------------

# 5. Prop System (Editor-Native Objects)

A key planned feature is the concept of **props**.

Props are editor-native scene objects that represent visual objects
placed into the area such as:

-   tables
-   trees
-   rocks
-   furniture

Each prop contains metadata describing:

-   sprite asset
-   bounding polygon
-   search map effect
-   height map effect
-   placement transform

Props exist as **editable objects in the editor** but do not exist
directly in Infinity Engine formats.

Instead they are **flattened into engine resources during export**.

Example export behavior:

Prop sprite → integrated into tileset or overlay\
Collision polygon → written into search map\
Height data → written into height map\
Tile layout changes → written into WED

This allows complex editing workflows while still producing valid
Infinity Engine assets.

------------------------------------------------------------------------

# 6. Map Overlay Editing

The Infinity Engine uses several pixel maps to define gameplay behavior:

Search Map (walkability)\
Height Map (vertical offsets)\
Light Map (lighting)

The editor should support these maps as **overlay layers** that can be
edited directly.

Overlay layers allow the user to:

-   visualize gameplay boundaries
-   paint walkable regions
-   edit elevation
-   modify lighting

Overlays should be toggleable and editable independently.

------------------------------------------------------------------------

# 7. Terrain Editing Concepts

Future versions of the editor may support terrain editing through
tileset tools.

Possible features include:

-   brush-based tile placement
-   terrain palettes
-   ground texture painting

These tools would modify the WED tile layout and reference the TIS
tileset.

This system is considered **long-term functionality**.

------------------------------------------------------------------------

# 8. Editor-Only Scene Objects

The scene architecture should allow objects that exist only inside the
editor.

Examples:

EditorGrid\
LightingPreview\
NavigationOverlay

These objects improve the editing experience but are **not exported to
the game**.

The exporter simply ignores them.

------------------------------------------------------------------------

# 9. Export / Compilation Pipeline

The editor's internal scene must eventually compile into Infinity Engine
resources.

Example export pipeline:

Scene Model ↓ Prop flattening ↓ Tile composition ↓ Search map generation
↓ Height map generation ↓ WED tile structure generation ↓ ARE object
serialization

Final output:

TIS\
WED\
ARE\
BMP overlays\
BCS scripts

This pipeline should remain separate from the editor's scene
representation.

------------------------------------------------------------------------

# 10. Backend Schema Considerations (Experimental)

Future backend architecture may involve a formal schema describing scene
objects.

Example conceptual structure:

SceneNode - id - type - name - parent - children - components

Components may include:

TransformComponent\
SpriteComponent\
CollisionComponent

This schema would support:

-   serialization
-   undo/redo systems
-   editor plugins
-   automated processing

This concept is **experimental and optional**.

The editor can function without a full schema system if necessary.

------------------------------------------------------------------------

# 11. Design Principles

Several guiding principles influence the architecture.

### Separation of Concerns

Editor scene representation must remain separate from Infinity Engine
file formats.

### Non-Destructive Editing

All editing should occur within the scene model rather than modifying
engine files directly.

### Expandability

The architecture should support future features such as:

-   advanced terrain tools
-   procedural prop placement
-   automated map generation

### Human and AI Readability

Structures and naming conventions should remain simple enough that both
humans and automated systems can understand them easily.

------------------------------------------------------------------------

# 12. Open Questions

Several design questions remain unresolved.

Examples include:

-   Exact prop compilation strategy
-   Efficient tile merging during export
-   Optimal UI layout for overlay editing
-   Terrain tool implementation

These will be addressed in later design stages.

------------------------------------------------------------------------

End of Document
