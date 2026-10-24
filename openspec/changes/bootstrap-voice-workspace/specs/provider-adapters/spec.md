## Purpose

Defines remote text-to-speech providers: a registry of models and their parameter schemas,
per-provider character-to-voice settings, compilation of a common intent into each
provider's parameters and tags, and persistent asynchronous generation jobs.

## ADDED Requirements

### Requirement: Remote providers only

Generation SHALL use remote provider APIs only; no local model inference is part of this
capability.

#### Scenario: Generation request

- **WHEN** the user generates a take
- **THEN** the application sends an HTTPS request to the configured provider and never loads a local synthesis model

### Requirement: Provider registry

The application SHALL expose a registry of providers and models, and each provider SHALL
declare its available models and the parameter schema used by the inspector.

#### Scenario: Model list per provider

- **WHEN** the user opens the model selector for a block
- **THEN** only models declared by the configured providers are listed and the inspector renders that model's declared parameters

### Requirement: Character to voice mapping per provider

Project settings SHALL map each Dialogic character to a voice identifier separately for
each provider.

#### Scenario: One character, two providers

- **WHEN** the project maps character `chen_mo` to voice A for provider X and voice B for provider Y
- **THEN** generating with provider X uses voice A and generating with provider Y uses voice B

#### Scenario: Character without a mapping

- **WHEN** a block targets a character that has no voice for the selected provider
- **THEN** generation is refused with a message naming the character and provider

### Requirement: Intent compilation

A block slot SHALL store a common intent (emotion, intensity, pace, style) plus an optional
raw prompt, and the provider adapter SHALL compile that intent into the provider's own
parameters and inline tags.

#### Scenario: Same intent, different providers

- **WHEN** the intent is “angry, fast, whispered” and the model changes between two providers
- **THEN** each provider receives its own parameter form and tag syntax for that intent

#### Scenario: Raw prompt passthrough

- **WHEN** the user writes raw provider tags in the prompt and enables raw mode
- **THEN** the adapter sends the prompt without rewriting it

### Requirement: Asynchronous job lifecycle

Each generation SHALL run as a job with the states queued, generating, succeeded, failed or
cancelled, and job state SHALL persist across application restarts.

#### Scenario: Restart during generation

- **WHEN** the application restarts while a job is generating
- **THEN** the job is restored as failed or resumable with its original block and slot, and is not silently dropped

#### Scenario: Cancel a queued job

- **WHEN** the user cancels a queued job
- **THEN** the job transitions to cancelled and no new take is appended for it

### Requirement: No application-level concurrency cap

Submitting a batch of blocks SHALL submit every job without an application-level limit, and
provider errors SHALL be reported per job without blocking the others.

#### Scenario: Batch with one failure

- **WHEN** ten blocks are submitted and one provider call returns an error
- **THEN** nine takes are appended and the failed job reports its provider error

### Requirement: Credentials are project-scoped and never logged

Provider credentials SHALL be stored per project, SHALL NOT appear in logs, job payloads or
exported documents, and SHALL be removable.

#### Scenario: Error message excludes the key

- **WHEN** a provider call fails with an authentication error
- **THEN** the reported message states that authentication failed and does not include the key value
