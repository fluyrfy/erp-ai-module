// ═══════════════════════════════════════════════════════════════════
// L2 Planner - Functions
// ═══════════════════════════════════════════════════════════════════

function PlanExecution(
  user_query: string,
  available_modules: string[]
) -> ExecutionPlan {
  client GPT4o
  prompt #"
    You are an Expert Task Planner.
    Break down User Query into executable tasks for Worker Agent.

    === AVAILABLE MODULES ===
    {{ available_modules }}

    === PLANNING RULES ===
    1. Each task must have clear action_required in business terms.
    2. search_criteria should contain concrete key-value filters.
    3. All tasks will execute in PARALLEL, do NOT assume sequential dependency.
    4. If query is simple, output only 1 task. Do not over-decompose.
    5. output_goal should specify what data fields are needed.

    === EXAMPLES ===

    User: "研發部有多少人？"
    {
      "thought_process": "User wants headcount of R&D department. Need to query employees filtered by department name.",
      "tasks": [
        {
          "task_id": "T1",
          "action_required": "Query employee count in R&D department",
          "search_criteria": { "department": "研發部" },
          "output_goal": "Get total employee count"
        }
      ],
      "final_answer_hint": "Report the headcount number directly"
    }

    User: "比較研發部和業務部的人數"
    {
      "thought_process": "User wants to compare headcount between two departments. Need two parallel queries.",
      "tasks": [
        {
          "task_id": "T1",
          "action_required": "Query employee count in R&D department",
          "search_criteria": { "department": "研發部" },
          "output_goal": "Get R&D headcount"
        },
        {
          "task_id": "T2",
          "action_required": "Query employee count in Sales department",
          "search_criteria": { "department": "業務部" },
          "output_goal": "Get Sales headcount"
        }
      ],
      "final_answer_hint": "Compare the two numbers and present which is larger"
    }

    === YOUR TASK ===
    User Query: {{ user_query }}

    {{ ctx.output_format }}
  "#
}

// Synthesizer - 整合多個 L3 結果
function SynthesizeResults(
  user_query: string,
  plan: ExecutionPlan,
  task_results: string,
) -> Synthesis {
  client GPT4o
  prompt #"
    You are an Expert Analyst (L2).
    Synthesize multiple task results into a coherent answer.

    === ORIGINAL QUERY ===
    {{ user_query }}

    === EXECUTION PLAN ===
    Thought Process: {{ plan.thought_process }}
    Final Answer Hint: {{ plan.final_answer_hint }}

    === TASK RESULTS ===
    {{ task_results }}

    === RULES ===
    1. If all tasks succeeded, synthesize a comprehensive answer.
    2. If some tasks failed, acknowledge the gaps and answer with available data.
    3. If all tasks failed, explain what went wrong.
    4. Be concise and directly answer the user's question.

    {{ ctx.output_format }}
  "#
}