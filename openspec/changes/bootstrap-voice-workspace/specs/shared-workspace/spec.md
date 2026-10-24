## Purpose

Defines the shared production surface where audio is auditioned, trimmed, cut, uploaded and
recorded, and where selections become reusable assets.

## ADDED Requirements

### Requirement: Load audio for audition

The shared workspace SHALL accept any take, asset or line render as its current source and
SHALL display a waveform for it.

#### Scenario: Load a take

- **WHEN** the user sends a take to the shared workspace
- **THEN** the waveform is displayed and the take can be played from the workspace

### Requirement: Non-destructive trim and cut

The workspace SHALL let the user set in and out points and preview the resulting selection
without modifying the source audio.

#### Scenario: Set in and out

- **WHEN** the user drags the in and out markers
- **THEN** playback of the selection is bounded by those markers and the source file is unchanged

#### Scenario: Cut preview

- **WHEN** the user cuts a region and previews
- **THEN** only the kept regions play and the source file is unchanged

### Requirement: Save selection as asset

The workspace SHALL turn the current selection into a new media asset stored in the project
and usable by clips.

#### Scenario: Save a selection

- **WHEN** the user saves a selection from 1.2 s to 3.0 s
- **THEN** a new asset containing only that range is created in `media/assets/` and appears in the pool

### Requirement: Uploads and recordings

The workspace SHALL accept uploaded audio files and microphone recordings as new assets.

#### Scenario: Upload a file

- **WHEN** the user uploads an audio file
- **THEN** the file is copied into `media/assets/` and becomes available to every line

#### Scenario: Record from the microphone

- **WHEN** the user records and stops
- **THEN** the recording is stored as a new asset and its waveform is shown

### Requirement: Assets are reusable

An asset SHALL be usable by any number of clips and lines without being copied per use.

#### Scenario: Same asset in two lines

- **WHEN** an asset is dropped into two different lines
- **THEN** both clips reference the same asset file

### Requirement: Workspace playback obeys the global rule

Workspace playback SHALL stop any other playback and SHALL stop when playback starts
elsewhere.

#### Scenario: Auditioning while a timeline plays

- **WHEN** a line timeline is playing and the user auditions an asset
- **THEN** the timeline stops and only the asset is audible
