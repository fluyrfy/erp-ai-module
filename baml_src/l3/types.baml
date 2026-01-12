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
  // 讓 L2 決定要載入哪個分析模組 (e.g., "financial_record", "hr_roster")
  data_type string @description("Classifies the data domain. Use snake_case.")

  // 狀態機判斷
  result_status string @description("High-level status: 'SUCCESS', 'NO_DATA', or 'ERROR'")

  // LLM 閱讀的簡報
  content_description string @description("Contextual summary of what this data represents (Time range, Target Department, Filters applied).")

  // L2 做邏輯推理用的素材
  key_points string[] @description("Key findings, max 5 items, factual observations only")

  // 關鍵數據（含單位）
  metrics map<string, string> @description("Keys must include unit suffix (e.g., 'salary_twd', 'count_person'). Values must be raw numbers/booleans.")

  // 關鍵關連 ID
  extracted_entities map<string, string[]> @description("Map of entity types to IDs. Key examples: 'employee_ids', 'dept_codes'.")
}

// For multi-tool scenarios (future)
// class ToolCall {
//   tool_name string
//   parameters string @description("JSON string of parameters")
// }