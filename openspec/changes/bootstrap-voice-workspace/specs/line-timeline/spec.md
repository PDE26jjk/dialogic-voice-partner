## Purpose

Defines the per-line single-track timeline: clips that reference a take or a media asset,
fixed in/out points chosen at creation, free placement, additive overlap, and line duration.

## ADDED Requirements

### Requirement: One track per line with local time

Each line SHALL own exactly one track whose time origin is the line's start, and clips
SHALL be positioned on that local timeline.

#### Scenario: Line opens with an empty track

- **WHEN** a line with no clips is opened
- **THEN** its timeline shows a single empty track starting at zero

#### Scenario: Position is local to the line

- **WHEN** a clip is placed at 2.0 s in one line and another clip at 2.0 s in a different line
- **THEN** both positions are interpreted relative to their own line and are independent

### Requirement: Clip sources

A clip SHALL reference either a block take or a media asset, and both kinds SHALL share the
same placement, in/out and overlap rules.

#### Scenario: Clip from a take

- **WHEN** the user drops a block take on a line timeline
- **THEN** a clip is created whose source is that take

#### Scenario: Clip from an asset

- **WHEN** the user drops an asset produced by the shared workspace on a line timeline
- **THEN** a clip is created whose source is that asset

### Requirement: Clips require playable audio

A clip SHALL NOT be creatable from a block until that block has at least one take, and the
interface SHALL reject the action with a visible reason.

#### Scenario: Block without takes

- **WHEN** the user drags a block with no takes onto a timeline
- **THEN** no clip is created and the reason is shown

### Requirement: In and out points are fixed at creation

Creating a clip SHALL set its in point to the start and its out point to the end of the
first take (or of the asset), and switching the active take SHALL NOT change those points.

#### Scenario: First take defines the span

- **WHEN** a clip is created from a take of 4.82 s
- **THEN** the clip has in 0 and out 4.82

#### Scenario: Switching take keeps the span

- **WHEN** the block's active take changes
- **THEN** the clip's in and out points stay the same and the clip occupies the same timeline span

### Requirement: Short source fills with silence

When the active take is shorter than a clip's span, the remainder SHALL be rendered as
silence and the clip's span SHALL NOT change.

#### Scenario: New take is shorter

- **WHEN** a clip spans 4.82 s and its active take is replaced by a 3.10 s take
- **THEN** the clip still spans 4.82 s, the last 1.72 s is silent, and overlapping clips keep their layout

### Requirement: Free placement and additive overlap

Clips SHALL be placeable at any time position, MAY overlap, and overlapping regions SHALL
be summed during playback and export.

#### Scenario: Overlapping clips

- **WHEN** two clips overlap between 1.0 s and 2.0 s
- **THEN** both are audible in that range and their gains add

### Requirement: Adding to the timeline end

The interface SHALL offer an action that appends the selected audio item to the end of the
current line's timeline.

#### Scenario: Append to end

- **WHEN** the user selects a take and presses “add to end”
- **THEN** a clip is created starting at the current line duration

### Requirement: Cross-line references are allowed

A clip SHALL be able to reference a take that belongs to a block linked to another line,
and creating such a clip SHALL NOT change the block's links.

#### Scenario: Borrow a take from another line

- **WHEN** the user drags a take from a block linked to line B onto line A's timeline
- **THEN** the clip is created on line A and the block link is unchanged

### Requirement: Line duration

A line's rendered duration SHALL be the maximum end time of its clips, and a line with no
clips SHALL have zero duration.

#### Scenario: Duration from last clip

- **WHEN** a line contains clips ending at 3.0 s and 5.5 s
- **THEN** the line duration is 5.5 s
