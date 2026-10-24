## Purpose

Defines the desktop shell that hosts the voice-production workspace: one window with five
regions, a managed local service, and exactly one audible playback source at a time.

## ADDED Requirements

### Requirement: Five-region workspace layout

The shell SHALL present a single window divided into five regions: a project list on the
left, a line list in the center, a block and media pool plus an inspector on the right, and
a shared workspace across the bottom.

#### Scenario: All regions visible on launch

- **WHEN** the application opens a project
- **THEN** the project list, line list, pool, inspector, and shared workspace are all visible and reachable without opening a dialog

#### Scenario: Regions resize independently

- **WHEN** the user drags the divider between the line list and the shared workspace
- **THEN** the line list and workspace change height independently of the right-hand column

### Requirement: Line timeline visibility per line

Each line SHALL have a local timeline that can be shown or hidden, and its panel height
SHALL be adjustable by dragging.

#### Scenario: Toggle a line timeline

- **WHEN** the user hides the timeline of a line
- **THEN** the line's timeline collapses while the rest of the line row keeps its position

#### Scenario: Adjust timeline height

- **WHEN** the user drags the timeline handle of a visible line
- **THEN** only that line's timeline height changes and the change persists when the project is reopened

### Requirement: Managed local service

The shell SHALL start and supervise a local service that performs audio decoding, provider
calls and rendering, and SHALL keep working offline once started.

#### Scenario: Service ready before interaction

- **WHEN** the application launches
- **THEN** project data becomes interactive only after the local service reports healthy

#### Scenario: Service crash recovery

- **WHEN** the local service exits unexpectedly
- **THEN** the shell reports the failure, offers a restart, and does not lose unsaved project documents

### Requirement: Single global playback

Only one audio source SHALL be audible at a time across the pool, line timelines and the
shared workspace.

#### Scenario: Starting playback elsewhere stops the current source

- **WHEN** audio is playing from a block preview and the user starts playback of a line timeline
- **THEN** the block preview stops and only the line timeline is audible

#### Scenario: Timeline playback stops on navigation

- **WHEN** the user switches to another line while a line timeline is playing
- **THEN** the previous line's playback stops

### Requirement: Cross-region drag targets

The shell SHALL allow dragging an item from the pool or the shared workspace onto a line
timeline and onto the inspector.

#### Scenario: Drag a take onto a timeline

- **WHEN** the user drags a block take onto a line timeline
- **THEN** a clip is created at the drop position using that take

#### Scenario: Drop rejected for silent source

- **WHEN** the user drags a block that has no playable take onto a line timeline
- **THEN** the drop is rejected with a visible reason and no clip is created

### Requirement: Workspace state persistence

The shell SHALL persist the selected project, the selected section, panel visibility and
region sizes, and SHALL restore them on next launch.

#### Scenario: Restore after restart

- **WHEN** the application is closed with section “act_2” selected and reopened
- **THEN** the same project and section are selected and panel sizes are restored
