// ═══════════════════════════════════════════════════════════════════
// L3 Generic Agent - Type Definitions
// ═══════════════════════════════════════════════════════════════════

// ===============================
// Post-process (VIEW layer only)
// ===============================

// Tool A: Aggregation (Count/Group By)
class AggregationTool {
  target_field string @description("Field name in `data.records[*]` to group/count by (e.g. 'statusName', 'jobTitleName').")
  top_k int? @description("Optional: return only top K buckets.")
}

// Tool B: Sorting
class SortingTool {
  sort_field string @description("Field name in `data.records[*]` to sort by.")
  order string @description("ASC or DESC")
}

type PostProcessStrategy = AggregationTool | SortingTool

class PostProcessPlan {
  strategy PostProcessStrategy 
  confidence float @description("Confidence score 0.0-1.0")
  reason string @description("Why this postprocess is needed for the final answer.")
}

// === API Selection ===
// Single API Choice
class ApiChoice {
  call_id string @description("Unique call identifier within this plan, e.g. 'dept_lookup', 'manager_lookup'")
  api_id string @description("Unique API identifier from the doc/spec, e.g. 'listDepartments' or 'listEmployees'")
  depends_on string[] @description("List of call_ids that must complete before this one starts. Use [] if none.")
  field_mappings FieldMapping[] @description("Fields to extract from previous results. Empty if no dependency.")
  postprocess PostProcessPlan? @description("Optional postprocess plan. null means no postprocess.")
  decision DecisionMetadata @description("Why this API is needed")
}

// Multi-API Selection Result
class ApiSelection {
  // stages ApiStage[] @description("List of execution stages. Stages run SEQUENTIALLY. APIs within a stage run in PARALLEL.")
  selected_apis ApiChoice[] @description("All APIs needed to answer the question, with dependency info")
  decision DecisionMetadata @description("Why these APIs together can answer the question")
}

// === Step 2: HTTP Request Generation ===
class FieldMapping {
  from_call string @description("Source call_id")
  from_field string @description("Field path in response, e.g. 'data.items[0].id' or 'department_id', use only simple dot notation or array indexing")
  to_param string @description("Target parameter name in this API")
  mapping_type string @description("Semantic label for this mapping (entity + id/field kind), e.g. employee_id, department_id, name, code. Used to prevent ID-type mixups.")
  decision DecisionMetadata @description("Why this mapping is semantically correct")
}

// Generic HTTP Request (LLM fills parameters)
class GetParams {
  query_params map<string, string> @description("Query string parameters. ")
}
class BodyParams {
  body string @description("Request body as JSON string.")
}

type ApiPayload = GetParams | BodyParams

// Generic Summary Output
class Summary {
  insight InsightMetadata
}

// For multi-tool scenarios (future)
// class ToolCall {
//   tool_name string
//   parameters string @description("JSON string of parameters")
// }

