// ═══════════════════════════════════════════════════════════════════
// L3 Generic Agent - Type Definitions
// ═══════════════════════════════════════════════════════════════════

// API Selection Result
class ApiSelection {
  api_id string @description("Unique API identifier from the doc")
  confidence float @description("Confidence score 0.0-1.0")
  reasoning string @description("Why this API was selected")
}

// Generic HTTP Request (LLM fills everything)
class HttpRequest {
  method string @description("HTTP method: GET, POST, PUT, DELETE")
  path string @description("Full path with path parameters filled, e.g. /api/employees/123")
  query_params map<string, string> @description("Query string parameters")
  body string @description("Request body as JSON string or POST/PUT body. Use '{}' for empty string for GET/DELETE")
  headers map<string, string> @description("Additional headers if needed")
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