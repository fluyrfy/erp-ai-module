// ═══════════════════════════════════════════════════════════════════
// L2 Planner - Type Definitions
// ═══════════════════════════════════════════════════════════════════

// 拆解出的單一任務
class Task {
  task_id string @description("Task ID for reference, e.g., T1, T2")

  target_module string @description("Target module: HR, Inventory, Finance")
  
  action_required string @description("What needs to be done in business terms")
  
  search_criteria map<string, string> @description("Filter conditions as key-value pairs")
  
  output_goal string @description("What this task should retrieve or achieve")
}

// 完整執行計畫
class ExecutionPlan {
  thought_process string @description("CoT: reasoning steps before generating tasks")
  
  tasks Task[]
  
  final_answer_hint string @description("How to synthesize task results into final answer")
}

// Synthesis Output
class Synthesis {
  answer string @description("Answer in user's language")
  key_findings string[] @description("Key points from task results")
  conclusion string @description("Direct answer to user's question")
}