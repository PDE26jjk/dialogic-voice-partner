## Purpose

Defines line-level rendering: one line or a batch of lines is mixed from its clips,
encoded to a configured format, delivered into the bound Godot project, and registered
back into Dialogic through the editor MCP endpoint.

## ADDED Requirements

### Requirement: Export scope is lines

Export SHALL operate on one line or on a user-selected set of lines, and SHALL NOT be
scoped to a whole `.dtl` timeline.

#### Scenario: Export one line

- **WHEN** the user exports a single line
- **THEN** one audio file is written for that line

#### Scenario: Export a batch

- **WHEN** the user selects twelve lines and exports
- **THEN** twelve files are written and the result reports per-line success or failure

### Requirement: Rendering is additive

A line render SHALL sum all clips on its track at their placed positions, pad ranges where
the active take is shorter than the clip span with silence, and SHALL NOT change clip spans.

#### Scenario: Overlap sum

- **WHEN** two clips overlap between 1.0 s and 2.0 s
- **THEN** the rendered audio in that range is the sum of both clips

#### Scenario: Silence padding

- **WHEN** a clip spans 4.82 s with a 3.10 s take
- **THEN** the render contains 1.72 s of silence after the take and the total line duration is unchanged

### Requirement: Configurable export format

The project SHALL expose export settings for container, sample rate, bit depth and channel
layout, and rendering SHALL honour them.

#### Scenario: Change format

- **WHEN** the user sets the container to WAV and the sample rate to 48000
- **THEN** exported files are WAV at 48000 Hz

### Requirement: Destination naming

An exported line SHALL be written into the bound Godot project at
`audio/voice/<section_slug>/<line_uuid>.<ext>`, overwriting an existing file with the same
name.

#### Scenario: Destination path

- **WHEN** line `0b6f…` in section `act_2` is exported as WAV
- **THEN** the file appears at `<godot_project>/audio/voice/act_2/0b6f….wav`

#### Scenario: Re-export overwrites

- **WHEN** the same line is exported again
- **THEN** the existing file is replaced and no duplicate copy is left behind

### Requirement: Write-back through the editor HTTP endpoint

After writing a line file, the application SHALL POST the line UUID, destination path and
source `.dtl` path to the Godot editor extension's local HTTP endpoint, and SHALL report a
failed write-back separately from a successful file export.

#### Scenario: Write-back success

- **WHEN** the export finishes and the extension confirms the update
- **THEN** the line is marked exported with the destination path

#### Scenario: Write-back failure

- **WHEN** the editor endpoint is unreachable or rejects the request
- **THEN** the exported file remains on disk, the line is marked exported-with-pending-write-back, and the user can retry the write-back alone

### Requirement: Batch failures do not abort the batch

A failure on one line in a batch SHALL NOT prevent the remaining lines from being rendered
and written.

#### Scenario: One line fails to render

- **WHEN** one line in a batch has no playable clips
- **THEN** the other lines are exported and the failing line is reported with its reason
