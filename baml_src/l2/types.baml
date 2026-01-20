// ═══════════════════════════════════════════════════════════════════
// L2 Planner - Type Definitions
// ═══════════════════════════════════════════════════════════════════

// 拆解出的單一任務
class Task {
  task_id string @description("Task ID for reference, e.g., T1, T2")

  target_module string @description("Target module")
  
  action_required string @description("What needs to be done in business terms")
  
  search_criteria map<string, string> @description("Filters; values must be verbatim from user query")

  query_terms string[] @description("Verbatim key terms extracted from user query")
  
  output_goal string @description("What this task should retrieve or achieve")

  decision DecisionMetadata @description("Why this task is needed and how confident we are in its design")
}

// 完整執行計畫
class ExecutionPlan {
  thought_process string @description("CoT: reasoning steps before generating tasks")

  decision DecisionMetadata @description("The high-level strategy decision for this plan.")
  
  tasks Task[]
  
  final_answer_hint string @description("How to synthesize task results into final answer")
}


// Synthesis Output
class Briefing {
  narrative NarrativeMetadata  // → 給 User（自然語言）
  insight InsightMetadata      // → 給 L1（結構化）
}