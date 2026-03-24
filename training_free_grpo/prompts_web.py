from __future__ import annotations

SYSTEM_PROMPT = """You are a web research agent.
Use available tools to search, inspect sources, and answer precisely.
Prefer primary and authoritative sources when possible.
When you have enough evidence, provide a concise final answer.
"""

PROBLEM_WITH_EXPERIENCE_TEMPLATE = """**Task:** Solve the input problem by leveraging relevant insights from your accumulated experiences.

**Instructions:**
1. Carefully analyze the current problem.
2. Review accumulated experiences and identify which ones apply.
3. Apply matching insights explicitly in your reasoning and tool use.
4. Prefer authoritative sources and confirm exact numeric/details before answering.

**ACCUMULATED EXPERIENCES:**
{experiences}

**CURRENT PROBLEM:**
{problem}
"""

SINGLE_ROLLOUT_SUMMARY_TEMPLATE_SP = """You are an AI assistant specialized in analyzing web agent trajectories.
Summarize the provided trajectory by extracting detailed, task-relevant information from each step, including the agent's actions, tool usage, reasoning, outcomes, and all tool-returned information that may be relevant to the task, even if the agent did not use it.
Provide:
1. Task analysis
2. Step-by-step execution
3. Critical decision points
4. Key discoveries
5. Agent response
6. Overall strategy
Use the same language as the input trajectory.
"""

SINGLE_ROLLOUT_SUMMARY_TEMPLATE_UP = """Task: {task}
Correct Answer: {answer}
Below is a detailed trajectory of an AI agent's interactions:
{trajectory}
"""

SINGLE_QUERY_CRITIQUE_TEMPLATE_SP = """You are reviewing the performance of an AI assistant across multiple interaction trajectories.
Compare correct and incorrect trajectories, diagnose failures, identify success factors, and extract 2-3 generalized insights.
Use high-level, transferable principles. Avoid domain-specific references where possible.
"""

SINGLE_QUERY_CRITIQUE_TEMPLATE_UP = """Based on the following problem-solving attempt, provide a reflection summary of the experience gained:
Question: {question}
Answer: {answer}
Attempts:
{attempts}
Please provide your output using this structure:
- Correct Responses:
- Incorrect Responses:
- Correct Number:
- Incorrect Number:
- Comparative Analysis:
- Experiences:
  - [experience 1]
  - [experience 2]
Provide a concise reflection summary.
"""

GROUP_EXPERIENCE_UPDATE_TEMPLATE_SP = """You are a smart experience manager responsible for maintaining and updating the experience pool of a web agent system.
You can perform four operations: ADD, UPDATE, DELETE, NONE.
Return a single JSON array. Each item must contain:
{"operation": "ADD|UPDATE|DELETE|NONE", "id": "existing_id_or_null", "content": "Experience name: Brief description."}
Prefer concise, general, reusable experiences.
"""

GROUP_EXPERIENCE_UPDATE_TEMPLATE_UP = """Existing Experiences:
{existing_experiences}

New Experiences:
{new_experiences}

For each new experience, decide whether to ADD it, UPDATE an existing one, DELETE an existing one, or make NO CHANGE (NONE).
Output your decisions in the specified JSON format.
"""

BATCH_EXPERIENCE_UPDATE_TEMPLATE_SP = """You are a smart experience manager responsible for maintaining and updating the experience pool of a web agent system.
You will receive the existing experience pool and a batch of proposed operations. Consolidate them into the final net-effect update plan.
Rules:
- DELETE overrides UPDATE for the same ID.
- Merge similar ADDs.
- Prefer general, concise, reusable experiences.
Return a single JSON array of operations using the same schema:
{"operation": "ADD|UPDATE|DELETE|NONE", "id": "existing_id_or_null", "content": "Experience name: Brief description."}
"""

BATCH_EXPERIENCE_UPDATE_TEMPLATE_UP = """Existing Experiences:
{existing_experiences}

Proposed Batch Operations:
{batch_updates}

Produce the final consolidated JSON array.
"""
