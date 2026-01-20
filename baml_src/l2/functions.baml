// ═══════════════════════════════════════════════════════════════════
// L2 Planner - Functions
// ═══════════════════════════════════════════════════════════════════

function PlanExecution(
  user_query: string,
  available_modules: string[],
  sys_context: string
) -> ExecutionPlan {
  client GPT4o
  prompt #"
    You are an Expert Task Planner.
    Break down User Query into executable tasks for Worker Agent.

    {{ sys_context }}

    === USER QUERY ===
    {{ user_query }}

    === AVAILABLE MODULES ===
    {{ available_modules }}

    === PLANNING RULES ===
    - **Module-Based Decomposition**: Split tasks ONLY when data resides in different modules. Do NOT split steps within the same module.
    - **Action Clarity**: Define 'action_required' as a high-level business goal, not a low-level API step.
    - **Output Goal**: Clearly specify the final data needed.
    - **VERBATIM FILTER VALUES (MANDATORY)**:
      - All values in 'search_criteria' MUST be copied verbatim from the USER QUERY (exact substring, same script, same casing).
      - Do NOT translate, paraphrase, normalize, or internationalize user-provided filter values.
      - If a needed filter value is not explicitly present in the USER QUERY, omit that key from 'search_criteria'.
    - **LANGUAGE CONSISTENCY (MANDATORY)**:
      - Keep task text and filters in the same language as USER QUERY.
      - Do not invent English labels for entities or departments.

    === YOUR TASK ===
    {{ ctx.output_format }}
  "#
}

// Synthesizer - 整合多個 L3 結果
function GenerateBriefing(
  user_query: string,
  plan: ExecutionPlan,
  task_results: string,
  sys_context: string
) -> Briefing {
  client GPT4o
  prompt #"
    You are an Expert Analyst.
    Synthesize multiple task results into a coherent answer.

    {{ sys_context }}

    === ORIGINAL QUERY ===
    {{ user_query }}

    === EXECUTION PLAN ===
    Thought Process: {{ plan.thought_process }}
    Final Answer Hint: {{ plan.final_answer_hint }}

    === TASK RESULTS ===
    {{ task_results }}

    === INSTRUCTIONS ===
    1. **InsightMetadata:**
       - Analyze the execution status strictly.
       - Extract key entities that might be needed for *follow-up actions*.
       - Keep `key_points` factual and dense.

    2. **NarrativeMetadata (For User Display):**
       - **answer**: 
         - Provide a concise, professional executive summary in the user's language.
         - Focus on the "So What?" (the conclusion).
         - Refer to the attachment if one is generated.

       - **data_attachment**:
         - **PHILOSOPHY**: "Show, Don't Just Tell." Proactively visualize complex information.
         - **VISUALIZATION LOGIC (Meta-Rules)**:
           Analyze the *topology* and *dimensionality* of the `Raw Results`:
           1. **Multidimensional / Comparative Data**:
              - IF data has rows and columns (e.g., entities with attributes, statistics).
              - ACTION: Project into a **Markdown Table**.
           2. **Sequential / Temporal / Process Data**:
              - IF data implies a sequence, a workflow, a lifecycle, or dependency steps.
              - ACTION: Project into a **Mermaid Flowchart** or **Sequence Diagram**.
           3. **Hierarchical / Relational Data**:
              - IF data represents trees, ownership structures, or nested categories.
              - ACTION: Project into a **Mermaid Class Diagram**, **Mindmap**, or **Nested List**.
           4. **Technical / Code Data**:
              - IF data is raw code, snippets, or configuration.
              - ACTION: Project into a **Code Block**.
         - **TRIGGER**:
           - Do NOT wait for an explicit user request.
           - IF the data structure implies a visualization reduces cognitive load compared to plain text, YOU MUST generate it.
           - Only return `null` if the result is a singular scalar value (e.g., "Success", "Count: 0").

    {{ ctx.output_format }}
  "#
}