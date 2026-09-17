# ReWoo Paper Summary

## Paper

**"ReWOO: Decoupling Reasoning from Observations for Efficient Augmented Language Models"**
Xu et al., 2023
[arXiv:2305.18323](https://arxiv.org/abs/2305.18323)

## Key Idea

The paper proposes decoupling the reasoning (planning) step from the observation (execution) step in augmented language models. Instead of the standard ReAct loop where the model interleaves reasoning and action, ReWOO separates them into distinct phases.

## Architecture

1. **Planner:** Generates a complete plan with all tool calls identified, without seeing any observations
2. **Worker:** Executes each planned step independently, passing results forward
3. **Solver:** Synthesizes all observations into a final answer using a single LLM call

## Efficiency Gains

The paper demonstrates 3–5x token reduction compared to ReAct-style prompting because:

- The Solver receives all observations in a single context
- No repeated reasoning between tool calls
- The planning step is done once, not after each observation

## How ReWoo Extends ReWOO

This project extends the original paper's architecture with:

1. **Reviewer stage:** A human-in-the-loop approval gate between planning and execution
2. **Risk classification:** Automated per-step risk assessment
3. **Sandboxed execution:** Destructive tools run in restricted environments
4. **Immutable audit log:** Complete traceability of all decisions and actions
5. **Skill memory:** Learning from successful executions for future reuse

These additions make the architecture suitable for production use where safety and auditability are required.
