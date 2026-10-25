## Purpose

Defines the on-disk project contract: a human-readable JSON file tree, the section list,
atomic writes, in-memory indexing, and orphan handling. No relational database is used.

## ADDED Requirements

### Requirement: Project folder contract

A project SHALL be a folder containing `project.json`, a `blocks/` directory, a `lines/`
directory, a `workspaces/` directory and a `media/` directory, and each document SHALL remain
readable and editable outside the application.

#### Scenario: Project created

- **WHEN** the user creates a project bound to a Godot project path
- **THEN** the folder contains `project.json`, `blocks/`, `lines/`, `workspaces/` and `media/`, and `project.json` records the bound Godot path

#### Scenario: Document edited by hand

- **WHEN** a user edits a block document outside the application and reopens the project
- **THEN** the application loads the edited document without requiring a migration step

### Requirement: Workspace state is stored per section

Each section SHALL have its own workspace document at `workspaces/<section_id>.json`
containing the current source reference, the in/out points and any selection, and the
application SHALL load that document whenever the section becomes current.

#### Scenario: Switching sections restores that section's workspace

- **WHEN** the user switches from section A to section B
- **THEN** the workspace shows B's saved source and in/out points, or an empty workspace when B has none

#### Scenario: Edits are written to the current section

- **WHEN** the user loads a take into the workspace and moves the in point
- **THEN** `workspaces/<current_section>.json` is updated and no other workspace document changes

### Requirement: Block documents are independent files

Each block SHALL be stored as its own document under `blocks/`, and a block SHALL record
its model slots, its takes, and its links to lines and sections.

#### Scenario: Editing one block rewrites one file

- **WHEN** a take is added to a block
- **THEN** only that block's document is rewritten and other block documents are untouched

### Requirement: Line documents own their track

Each line SHALL be stored as its own document under `lines/`, keyed by the Godot-generated
UUID, and SHALL contain the line text, its section, its source timeline path, its character,
and its single track of clips.

#### Scenario: Line document lookup

- **WHEN** a line with UUID `0b6f…` is opened
- **THEN** the application reads `lines/0b6f….json` and no other line document is loaded for that access

### Requirement: Section list

The project SHALL keep a section list in `project.json` with an identifier, a display name
and an order, plus the identifier of the current section.

#### Scenario: New push uses the current section

- **WHEN** a line is pushed while section `act_2` is current
- **THEN** the line is assigned to section `act_2`

#### Scenario: No section exists yet

- **WHEN** a line is pushed while the project has no sections
- **THEN** the application creates a default section named “Inbox”, makes it current, and assigns the line to it

### Requirement: Atomic writes

Every document write SHALL be atomic, so that an interrupted write never leaves a partially
written document.

#### Scenario: Interrupted write

- **WHEN** the process terminates during a block document write
- **THEN** the previous version of the document remains readable and the partial content is discarded

### Requirement: In-memory index

Opening a project SHALL build an in-memory index of sections, lines, blocks, takes and
their links, and the index SHALL be the source for cross-document queries.

#### Scenario: Blocks of a line

- **WHEN** the user opens a line
- **THEN** the pool lists the blocks linked to that line without reading every block document from disk

### Requirement: Orphan handling

A block whose linked lines no longer exist SHALL be kept and marked as orphaned; the
application SHALL NEVER delete blocks or takes automatically.

#### Scenario: Line removed in Godot

- **WHEN** a linked line is absent after a reconcile action
- **THEN** the block remains on disk and is flagged as orphaned in the pool

#### Scenario: Explicit cleanup

- **WHEN** the user runs “clean orphan blocks”
- **THEN** only orphaned blocks are removed and any take referenced by a clip is protected from deletion
