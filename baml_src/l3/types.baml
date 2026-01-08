// ═══════════════════════════════════════════════════════════════════
// L3 Generic Agent - Type Definitions
// ═══════════════════════════════════════════════════════════════════


// === FetchStrategy ===
enum FetchStrategy {
  SINGLE_PAGE @description("Default mode. Use this when finding specific persons, departments, or a small set of records (e.g., 'Find John's email').")
  ALL_PAGES @description("Aggregation mode. Use this ONLY when the user asks for STATISTICS, TOTAL COUNTS, RANKINGS, or SEARCHING ALL records (e.g., 'How many...', 'Most common...', 'List all...').")
}


// === API Selection ===
// Single API Choice
class ApiChoice {
  api_id string @description("Unique API identifier from the doc, e.g. 'listDepartments' or 'listEmployees'")
  depends_on string[] @description("List of api_ids that must complete before this one starts. Use [] if none.")
  field_mappings FieldMapping[] @description("Fields to extract from previous results. Empty if no dependency.")
  confidence float @description("Confidence for this specific API, 0.0-1.0")
  reason string @description("Why this API is needed to answer the question")
}

// class ApiStage {
//   stage_id int
//   apis ApiChoice[] @description("APIs in this stage can be executed in PARALLEL")
//   reason string @description("Why these APIs are grouped in this stage")
// }

// Multi-API Selection Result
class ApiSelection {
  // stages ApiStage[] @description("List of execution stages. Stages run SEQUENTIALLY. APIs within a stage run in PARALLEL.")
  selected_apis ApiChoice[] @description("All APIs needed to answer the question, with dependency info")
  confidence float @description("Confidence that these APIs can answer the question, 0.0-1.0")
  reason string @description("Why these APIs together can answer the question")
}

// === Step 2: HTTP Request Generation ===
// class FilterCondition {
//   field string                // "name"
//   operator string             // "==" | "!=" | ">" | "<"
//   value string                // "研發部" (從 user_query 抽取)
// }
class FieldMapping {
  from_api string @description("Source API id")
  from_field string @description("Field path in response, e.g. 'data.items[0].id' or 'department_id', use only simple dot notation or array indexing")
  // filter FilterCondition?
  to_param string @description("Target parameter name in this API")
}
// Generic HTTP Request (LLM fills everything)
class HttpRequest {
  method string @description("HTTP method: GET, POST, PUT, DELETE")
  path string @description("Full path with path parameters filled, e.g. /api/employees/123")
  query_params map<string, string> @description("Query string parameters")
  body string @description("Request body as JSON string or POST/PUT body. Use '{}' for empty string for GET/DELETE")
  headers map<string, string> @description("Additional headers if needed")
  fetch_strategy FetchStrategy @description("Analyze user intent: is this a specific lookup (SINGLE) or a statistical/global query (ALL)?")
  aggregation_field string? @description("If fetch_strategy is ALL_PAGES and user asks for statistics (e.g. 'most common surname'), specify the field name to count (e.g. 'lastName'). Otherwise null.")
}

// Generic Summary Output
class Summary {
  title string @description("Summary title in user's language")
  key_points string[] @description("Key findings, max 5 items")
  metrics map<string, string> @description("Important numbers/metrics")
  recommendation string @description("Suggested next action")
}

// For multi-tool scenarios (future)
// class ToolCall {
//   tool_name string
//   parameters string @description("JSON string of parameters")
// }