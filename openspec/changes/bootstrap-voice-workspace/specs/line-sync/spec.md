## Purpose

Defines how Dialogic lines reach the companion: a manual, one-way push from the Godot
editor that creates or updates lines by UUID, and never writes line text back.

## ADDED Requirements

### Requirement: Push from the timeline context menu

The Godot extension SHALL add a “Push to Voice Partner” entry to the Dialogic timeline
event context menu, and SHALL send the voice line paired with the clicked event, whether
that event is the voice event or its following text event.

#### Scenario: Push a voice event

- **WHEN** the user right-clicks a voice event and chooses “Push to Voice Partner”
- **THEN** the voice event's UUID and the following text event are sent as one line

#### Scenario: Push a text event

- **WHEN** the user right-clicks a text event and chooses “Push to Voice Partner”
- **THEN** the preceding voice event is paired with that text and sent as one line

#### Scenario: Text without a voice event

- **WHEN** the user pushes a text event that has no preceding voice event
- **THEN** the extension inserts a new voice event before it, gives it a UUID, and sends that line

#### Scenario: Push a multi-selection

- **WHEN** the user selects several events and chooses the menu entry on one of them
- **THEN** every selected line is sent once, deduplicated by UUID

### Requirement: Push uses the active project

The companion SHALL route pushed lines to the project it currently has active, and a push
SHALL NOT require the Godot side to know a filesystem path.

#### Scenario: Active project receives the push

- **WHEN** the user pushes a line while project A is active
- **THEN** the line document is written under project A

#### Scenario: No active project

- **WHEN** the user pushes a line and no project is active
- **THEN** the service answers 409 and the editor reports that a project must be created or activated

### Requirement: UUID upsert

The companion SHALL treat the Godot-generated UUID as the identity of a line: an incoming
line with an unknown UUID creates a line, and an incoming line with a known UUID updates
that line.

#### Scenario: Existing UUID updates in place

- **WHEN** a pushed line has a UUID that already exists and different text
- **THEN** the existing line's text is updated, its timeline and block links are preserved

#### Scenario: Unknown UUID creates a line

- **WHEN** a pushed line has a UUID that does not exist in the project
- **THEN** a new line document is created in the current section

### Requirement: One-way authority

The companion SHALL NOT modify line text, character, UUID or the `.dtl` source path; those
values are authoritative in the Godot project.

#### Scenario: Editing text in the companion

- **WHEN** the user attempts to edit a line's text in the companion
- **THEN** the field is read-only and the interface explains that text is edited in Dialogic

### Requirement: Missing lines are not deleted

A push SHALL NOT delete lines that are absent from the payload; absence SHALL be resolved
only by an explicit reconcile action.

#### Scenario: Partial push does not remove other lines

- **WHEN** the user pushes two lines out of a project that contains twenty
- **THEN** the other eighteen lines remain unchanged

### Requirement: Push feedback

The Godot extension SHALL display the outcome of a push, including created, updated and
orphaned counts, and the companion SHALL return a failure reason when the request is rejected.

#### Scenario: Companion unreachable

- **WHEN** the companion is not running
- **THEN** the editor reports that the push failed and the selection remains for a retry

### Requirement: Project binding is one to one

A companion project SHALL bind to exactly one Godot project, and rebinding SHALL be an
explicit user action.

#### Scenario: Bind on creation

- **WHEN** the user creates a project and chooses a Godot project path
- **THEN** that path is stored in `project.json` and used for subsequent pushes and exports

#### Scenario: Rebind keeps UUIDs

- **WHEN** the user rebinds the project to another Godot project path
- **THEN** existing lines, blocks and takes are preserved and only the destination path changes
