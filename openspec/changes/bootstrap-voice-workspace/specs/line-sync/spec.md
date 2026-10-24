## Purpose

Defines how Dialogic lines reach the companion: a manual, one-way push from the Godot
editor that creates or updates lines by UUID, and never writes line text back.

## ADDED Requirements

### Requirement: Manual push from the Godot editor

The Godot extension SHALL provide an action that pushes the selected voice events, either
one or many, to the companion in a single request.

#### Scenario: Push a single line

- **WHEN** the user selects one voice event in the editor and runs “push to Voice Partner”
- **THEN** the companion receives one line and reports it as created or updated

#### Scenario: Push many lines

- **WHEN** the user selects several voice events and runs the same action
- **THEN** the companion receives all of them in one request and reports created, updated and orphaned counts

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
