# Product Overview

## Summary

This project is a multi-agent Dungeons & Dragons runtime where a DM agent, multiple player agents, optional NPC agents, and human participants interact through a controlled game engine.

The goal is not merely to make agents chat in a fantasy setting. The real goal is to study and build:

- bounded autonomy
- multi-agent coordination
- hidden information handling
- turn orchestration
- structured action contracts
- memory systems
- human-in-the-loop control
- observability and replay

## Primary Use Cases

### 1. Spectate an autonomous campaign
Humans watch a party of AI-controlled characters play through a quest.

### 2. Direct an experiment
Operators inspect prompts, memory, event flow, and state transitions while the system runs.

### 3. Join the table
A human can take over one character, send tactical messages, whisper to the DM, and submit actions.

### 4. Evaluate agent behavior
The runtime supports replay, inspection, and testing so the team can compare policies, models, prompts, and coordination strategies.

## Product Goals

- Create a stable runtime for custom agents rather than relying on a large external agent framework.
- Make the system understandable enough for debugging and iteration.
- Preserve D&D table feel through discussion, banter, secrecy, and narrative pacing.
- Keep mechanics deterministic enough that the simulation does not collapse into improv soup.
- Support local-first inference through LM Studio.
- Leave a clean abstraction boundary for later Azure AI Foundry integration.

## Non-Goals for v1

- Full D&D 5e rules coverage
- large-scale world simulation
- polished production-grade streaming platform
- voice-first interaction
- autonomous long-form open-world sandboxing
- perfect tactical play

## Core Design Principles

### State is law
Agents may propose actions and messages. They do not directly mutate canonical state.

### Communication is separate from action execution
Conversation affects decisions, but only validated structured actions affect state.

### Hidden information is real
Each agent sees only the state and messages that should be visible to it.

### Deterministic rules beat creative bookkeeping
Narrative is flexible. HP, positions, inventory, and turn order are not.

### Human override is normal
A human operator or player can pause, inspect, correct, or take over at runtime.

## User Modes

### Spectator Mode
- watch transcript and events
- inspect map/state panels
- see turn order and dice results

### Director Mode
- pause/resume the session
- inspect agent context
- inspect private memory
- override an action
- inject an event
- edit state for testing

### Human Player Mode
- assume control of a character
- send tactical table talk
- speak in character
- whisper to the DM
- submit structured actions

## Success Criteria

The system is successful when:

- turns are coherent
- state remains consistent over long sessions
- hidden information boundaries hold
- agents coordinate without endless loops
- a human can understand what is happening in real time
- the session is replayable and debuggable
- the story feels emergent instead of purely scripted
