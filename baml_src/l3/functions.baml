// ═══════════════════════════════════════════════════════════════════
// L3 Generic Agent - Functions
// ═══════════════════════════════════════════════════════════════════

// Step 1: Select which API to call
function SelectApi(
  user_query: string,
  api_doc: string,
  module_context: string
) -> ApiSelection {
  // client DefaultL3LLM
  client GPT4o
  prompt #"
    You are an API Planner. Your goal is to create an efficient execution plan.

    USER QUERY:
    {{ user_query }}

    MODULE CONTEXT:
    {{ module_context }}

    AVAILABLE APIs:
    {{ api_doc }}

    TASK:
    1. List ALL APIs needed.
    2. Set depends_on for each API.
    3. For APIs with dependencies, pre-plan field_mappings:
       - Look at the dependency's RESPONSE SCHEMA
       - Specify which field maps to which parameter
    4. For APIs without dependencies, set field_mappings to [].

    EXAMPLE:
    Query: "List employees in Engineering department"
    → Need department_id first, then query employees
    apis: [
      { 
        api_id: "listWithTree", 
        depends_on: [], 
        field_mappings: [],
        reason: "Get department ID for Engineering department" 
      },
      { 
        api_id: "list", 
        depends_on: ["listWithTree"], 
        field_mappings: [
          { from_api: "listWithTree", from_field: "data[0].id", to_param: "departmentId" }
        ],
        reason: "Query employees by department ID" 
      }
    ]

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

    USER QUERY: {{ user_query }}
    CURRENT DATE: {{ current_date }}

    TARGET API SPECIFICATION:
    {{ api_spec }}

    TASK:
    1. Generate HTTP request based on USER QUERY only.
    2. Fill path parameters in path (e.g., /users/{id} → /users/123).
    3. Fill query/body parameters from user query context.
    4. For date ranges, infer from query (e.g., "this month" → start/end of current month).
    5. Use "" for body on GET/DELETE.
    6. DO NOT fill parameters that come from other APIs.

    {{ ctx.output_format }}
  "#
}

// Step 3: Generate summary from API response
function GenerateSummary(
  user_query: string,
  api_response: string,
  output_language: string
) -> Summary {
  client GPT4o
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