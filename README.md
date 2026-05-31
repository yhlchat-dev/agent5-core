# Agent 5.0 — Controllable Self-Evolving Cognitive Operating System

Agent 5.0 is a cognitive operating system for multi‑agent collaboration, built on a microkernel (KernelBoot) and a unified decision core (CognitiveKernelV2). It solves four fundamental challenges of current agents: decision chaos, non‑evolving memory, absent safety auditing, and lack of temporal awareness.

## Key Innovations

- **Identity‑driven cognition** – IdentityCore drives curiosity, self‑evolution, and decisions.
- **Immutable memory ledger** – All memory changes are hash‑chained, rollbackable, and verifiable.
- **Triple‑teacher safety approval** – Planner + Critic + CausalJudge audit every action.
- **Memory→Capsule auto‑evolution** – Experience automatically distills into strategy capsules.
- **Unified cognitive flow + data chain** – 9‑step cognitive loop produces RL/SFT training samples.

## Current Status

- 852 modules, 86,869 lines of code, zero circular dependencies.
- 250+ unit tests pass, 407 regression tests pass.
- Production‑ready prototype already runs safety‑audit closed loop (see [DataChain examples](docs/golden_chains/)).
- Outstanding technical debt (195 nested functions, 112 I/O mixed, 121 hardcoded constants) will be fixed during the funded phase.

- [Full Technical Whitepaper (WHITEPAPER_EN.md)](WHITEPAPER_EN.md)

## License

MIT
