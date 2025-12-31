// ═══════════════════════════════════════════════════════════════════
// L3 Generic Agent - Functions
// ═══════════════════════════════════════════════════════════════════

// Step 1: Select which API to call
function SelectApi(
  user_query: string,
  api_doc: string,
  module_context: string
) -> ApiSelection {
  client DefaultL3LLM
  prompt #"
    You are an API router for an ERP system.

    USER QUERY:
    {{ user_query }}

    MODULE CONTEXT:
    {{ module_context }}

    AVAILABLE APIs (OpenAPI spec):
    {{ api_doc }}

    Select the most appropriate API to answer the user's question.
    If no API matches, set confidence to 0.

    {{ ctx.output_format }}
  "#
}

// Step 2: Generate complete HTTP request (LLM fills all params)
function GenerateHttpRequest(
  user_query: string,
  api_spec: string,
  current_date: string
) -> HttpRequest {
  client DefaultL3LLM
  prompt #"
    You are an API parameter generator.

    USER QUERY:
    {{ user_query }}

    TARGET API SPECIFICATION:
    {{ api_spec }}

    CURRENT DATE: {{ current_date }}

    Generate a complete HTTP request to call this API.
    - Fill path parameters directly in the path (e.g., /users/{id} → /users/123)
    - Include all necessary query parameters
    - For date ranges, infer from user query (e.g., "this month" → start/end dates)
    - Leave body as empty {} for GET/DELETE requests

    {{ ctx.output_format }}
  "#
}

// Step 3: Generate summary from API response
function GenerateSummary(
  user_query: string,
  api_response: string,
  output_language: string
) -> Summary {
  client DefaultL3LLM
  prompt #"
    You are an ERP assistant that summarizes data.

    USER'S ORIGINAL QUESTION:
    {{ user_query }}

    API RESPONSE DATA:
    {{ api_response }}

    OUTPUT LANGUAGE: {{ output_language }}

    Generate a clear, concise summary.
    - Title should directly answer the question
    - Key points: max 5, most important findings
    - Data highlights: key numbers/metrics
    - Recommendation: actionable next step

    {{ ctx.output_format }}
  "#
}