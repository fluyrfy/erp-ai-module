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
    You are an API Planner. Your goal is to create an efficient execution plan.

    USER QUERY:
    {{ user_query }}

    MODULE CONTEXT:
    {{ module_context }}

    AVAILABLE APIs:
    {{ api_doc }}

    TASK:
    1. List ALL APIs needed to answer the question.
    2. Set depends_on for each API:
       - If API_B needs data from API_A's response → depends_on: ["API_A"]
       - If no dependency → depends_on: []
    3. Set confidence to 0 if no APIs can answer.

    EXAMPLE:
    Query: "List employees in Engineering department"
    → Need department_id first, then query employees
    apis: [
      { api_id: "listDepartments", depends_on: [], reason: "Get department_id" },
      { api_id: "listEmployees", depends_on: ["listDepartments"], reason: "Filter by department_id" }
    ]

    {{ ctx.output_format }}
  "#
}

// Step 2: Generate complete HTTP request (LLM fills all params)
function GenerateHttpRequest(
  user_query: string,
  api_spec: string,
  dependency_schemas: string,
  current_date: string
) -> HttpRequest {
  client DefaultL3LLM
  prompt #"
    You are an API parameter generator.

    USER QUERY:
    {{ user_query }}

    CURRENT DATE: {{ current_date }}

    TARGET API SPECIFICATION:
    {{ api_spec }}

    DEPENDENCY SCHEMAS (field names only, NO values):
    {{ dependency_schemas }}




    Generate a complete HTTP request to call this API.
    - If the user query or the target API requires data from previous steps:
      Look into 'PREVIOUS CALL RESULTS' to find the relevant field names.
      Map the value logically (e.g., if API_A has 'invoice_id', use it for API_B's 'id' parameter).
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