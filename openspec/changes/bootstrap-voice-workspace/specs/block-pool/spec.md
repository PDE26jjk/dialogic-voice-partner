## Purpose

Defines the project-wide pool of generation blocks: independent units that hold per-model
prompts and parameters, share one take history, and can be linked to several lines and
sections.

## ADDED Requirements

### Requirement: Blocks live at the project level

A block SHALL belong to the project, SHALL be independent of any timeline, and SHALL NOT
be owned by a single line.

#### Scenario: Pool shows blocks without a line

- **WHEN** the user opens the block pool
- **THEN** blocks are listed even when no line is selected

#### Scenario: Block survives line deletion

- **WHEN** the linked line disappears
- **THEN** the block and its takes remain in the pool

### Requirement: Blocks link to lines and sections

A block SHALL be able to link to zero or more lines and zero or more sections, and the
links SHALL NOT imply ownership.

#### Scenario: One block linked to two lines

- **WHEN** the user links a block to line A and line B
- **THEN** both lines list the block and neither link is treated as the owner

#### Scenario: Unlink leaves the block intact

- **WHEN** the user removes the link to line A
- **THEN** the block remains linked to line B and its takes are unchanged

### Requirement: Per-model slots are created lazily

A block SHALL keep one slot per provider and model, each containing a prompt and that
provider's parameters, and a slot SHALL be created only when that model is selected for
the block.

#### Scenario: First use of a model creates a slot

- **WHEN** the user changes a block's model from provider X to provider Y
- **THEN** a slot for provider Y is created with a prompt converted from the line and default parameters

#### Scenario: Switching back reuses the slot

- **WHEN** the user switches the block back to provider X
- **THEN** the existing provider X prompt and parameters are restored unchanged

### Requirement: Prompt initialization and conversion

A new slot's prompt SHALL start as a copy of the line text, and the interface SHALL offer a
conversion action that rewrites that copy into the target model's prompt or tag form; the
user SHALL also be able to edit the prompt directly.

#### Scenario: Initial prompt equals line text

- **WHEN** a block is created from a line
- **THEN** the first slot's prompt equals the line text

#### Scenario: Conversion is explicit

- **WHEN** the user presses “convert prompt for this model”
- **THEN** the prompt is replaced with a converted version and the previous text is recoverable from history

### Requirement: Takes are shared across models

A block SHALL keep one append-only take history shared by all of its model slots, and each
take SHALL record the provider and model that produced it.

#### Scenario: Switch model and keep history

- **WHEN** the user generates with a second model and then switches back to the first
- **THEN** takes produced by both models are still listed and each shows its source model

#### Scenario: Filter by model

- **WHEN** the user filters the take history by one model
- **THEN** only takes produced by that model are listed

### Requirement: Take retention and deletion

Takes SHALL NOT be removed automatically, and the user SHALL be able to delete a take
unless a clip references it.

#### Scenario: Delete an unreferenced take

- **WHEN** the user deletes a take that no clip references
- **THEN** the take is removed from the block and its media file is scheduled for deletion

#### Scenario: Referenced take is protected

- **WHEN** the user deletes a take referenced by at least one clip
- **THEN** the deletion is refused and the referencing lines are listed

### Requirement: Duplication and regeneration

The user SHALL be able to duplicate a block, regenerate a block, and select which take is
active for playback.

#### Scenario: Duplicate a block

- **WHEN** the user duplicates a block
- **THEN** a new block document is created with copied slots, and its take list references the same media files without copying them

#### Scenario: Regenerate

- **WHEN** the user regenerates a block
- **THEN** a new generation job is submitted for the block's current slot and its outcome is appended as a new take

### Requirement: Block title

A block SHALL have an editable title that defaults to the character name followed by the
first characters of the line text.

#### Scenario: Default title

- **WHEN** a block is created from character “chen_mo” with text “架子塌下来那一下”
- **THEN** the title defaults to a form containing the character name and a prefix of the text

#### Scenario: Rename

- **WHEN** the user renames a block
- **THEN** the new title is stored without changing any link or take

### Requirement: Pushing lines does not create blocks

A line push SHALL NOT create blocks automatically.

#### Scenario: Push without blocks

- **WHEN** ten lines are pushed and no block is created for them
- **THEN** the pool remains unchanged and each line shows an empty block list
