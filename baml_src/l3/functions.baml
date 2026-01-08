// ═══════════════════════════════════════════════════════════════════
// L3 Generic Agent - Functions
// ═══════════════════════════════════════════════════════════════════

// Step 1: Select which API to call
function SelectApi(
  user_query: string,
  api_doc: string,
  module_context: string
) -> ApiSelection {
  client GPT4o
  // client DefaultL3LLM
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
    3. For APIs with dependencies, pre-plan field_mappings.

    *** CRITICAL RULES ***
    1. CHECK PARAMETERS: Before creating a field_mapping, verify that the 'to_param' explicitly exists in the target API's definition.
    2. NO HALLUCINATION: If the target API does NOT have a filter parameter (e.g., departmentId), DO NOT create a mapping for it. Just select the API without mapping (you will filter data later in the summary step).
    3. DATA DEPENDENCY: Ensure the 'from_field' path actually exists in the source API's response schema.

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
    7. Determine `fetch_strategy`:
       - Set to 'ALL_PAGES' if the intent is aggregation, counting, statistics, or searching ALL records.
       - Set to 'SINGLE_PAGE' for specific entity lookups.
    8. Determine `aggregation_field`:
       - If `fetch_strategy` is 'ALL_PAGES' and the user wants to count/group by a specific attribute (e.g., "most common Last Name"), set this to the corresponding JSON field name (e.g., "lastName").
       - If no specific field grouping is needed (e.g. just "count total employees"), leave as null.

    *** STRICT CONSTRAINTS ***
    1. SCHEMA COMPLIANCE: You must ONLY use parameters explicitly defined in the 'parameters' or 'request_body' of the TARGET API SPECIFICATION.
    2. NO INVENTED FIELDS: Even if the User Query implies a filter (e.g., "departmentId"), if the API spec doesn't have it, DO NOT add it to the body/query. Ignore that part of the query.
    3. SAFE DEFAULTS: If a required parameter cannot be inferred, use a reasonable default or leave it blank.
    4. AGGREGATION OPTIMIZATION: If `fetch_strategy` is 'ALL_PAGES', and the API supports pagination (pageSize), you MUST set "pageSize" to a larger number (e.g., 100) in the body to minimize requests.

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

    *** LOGIC FOR HANDLING ERRORS ***
    1. **Dependency/Data Chain Failure**:
        - Look for entries with **"status": "error"** AND **"code": "DATA_DEPENDENCY_MISSING"**.
        - This strictly means the Target Object (e.g., Department, Employee) WAS NOT FOUND in the previous step.
        - You MUST reply: "Cannot find [Target Name]. Please check if the name is correct."
        - **Strictly FORBIDDEN** to say "No missing data found" or "Everything is fine" when you see this error code.

    2. **Normal Summary**:
        Generate a clear, concise summary.
        - Title should directly answer the question
        - Key points: max 5, most important findings
        - Data highlights: key numbers/metrics
        - Recommendation: actionable next step

    {{ ctx.output_format }}
  "#
}