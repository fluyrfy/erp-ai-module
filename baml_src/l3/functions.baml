// ═══════════════════════════════════════════════════════════════════
// L3 Generic Agent - Functions
// ═══════════════════════════════════════════════════════════════════

// Step 1: Select which API to call
function SelectApi(
  task: Task,
  api_doc: string,
  module_context: string
) -> ApiSelection {
  client GPT4o
  // [G1, G2, G3, G4]: 20B High
  // client GptOss20bHigh
  // [G5, G6]: 120B High
  // client GptOss120bHigh
  // client GptOss20bLow
  prompt #"
    You are an API Planner. Your goal is to create an efficient execution plan.

    === TASK ===
    - Action: {{ task.action_required }}
    - Filters: {{ task.search_criteria }}
    - Goal: {{ task.output_goal }}

    === MODULE CONTEXT ===
    {{ module_context }}

    === AVAILABLE APIs ===
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
  task: Task,
  api_spec: string,
  current_date: string
) -> HttpRequest {
  client GPT4oMini
  // [G1, G2]: 20B Low
  // client GptOss20bLow
  // [G3, G4, G5, G6]: 120B Low
  // client GptOss120bLow
  // client GptOss20bLow
  prompt #"
    You are an API parameter generator.

    === TASK ===
    - Action: {{ task.action_required }}
    - Filters: {{ task.search_criteria }}
    - Goal: {{ task.output_goal }}

    === CURRENT DATE ===
    {{ current_date }}

    === TARGET API SPECIFICATION ===
    {{ api_spec }}

    TASK:
    1. Generate HTTP request based on USER QUERY only.
    2. Fill path parameters in path (e.g., /users/{id} → /users/123).
    3. Fill query/body parameters from user query context.
    4. For date ranges, infer from query (e.g., "this month" → start/end of current month).
    5. Use "" for body on GET/DELETE.
    6. DO NOT fill parameters that come from other APIs.
    7. Determine `aggregation_field`:
       - If the user wants to count/group by a specific attribute (e.g., "most common Last Name"), set this to the corresponding JSON field name (e.g., "lastName").
       - If no specific field grouping is needed (e.g. just "count total employees"), leave as null.

    *** STRICT CONSTRAINTS ***
    1. SCHEMA COMPLIANCE: You must ONLY use parameters explicitly defined in the 'parameters' or 'request_body' of the TARGET API SPECIFICATION.
    2. NO INVENTED FIELDS: Even if the User Query implies a filter (e.g., "departmentId"), if the API spec doesn't have it, DO NOT add it to the body/query. Ignore that part of the query.
    3. SAFE DEFAULTS: If a required parameter cannot be inferred, use a reasonable default or leave it blank.
    
    {{ ctx.output_format }}
  "#
}

// Step 3: Generate summary from API response
function GenerateSummary(
  task: Task,
  api_response: string,
) -> Summary {
  client GPT4o
  // [G1]: 20B Medium
  // client GptOss20bMedium
  // [G2]: 20B High
  // client GptOss20bHigh
  // [G3, G5]: 120B Low
  // client GptOss120bLow
  // [G4, G6]: 120B High
  // client GptOss120bHigh
  // client GptOss20bMedium
  prompt #"
    You are an Data Summarizer. 
    Your output is piped directly into a Analysis Agent.

    === TASK ===
    - Action: {{ task.action_required }}
    - Filters: {{ task.search_criteria }}
    - Goal: {{ task.output_goal }}

    === RAW DATA ===
    {{ api_response }}

    *** CRITICAL INSTRUCTIONS ***

    - **Data Type & Status**:
       - Analyze the API response structure.
       - If response is empty list [] or null -> result_status: "NO_DATA".
       - If response indicates error -> result_status: "ERROR".
       - Otherwise -> result_status: "SUCCESS".
       - data_type: Classify the entity (e.g., "employee_list", "department_info").

    - **Context Description**:
       - Generate 'content_description'. 
       - Do NOT just repeat the TASK OBJECTIVE. Explain the *scope* of the data.
       - Example: "Salary data for Dept A01 filtered by date > 2024-01-01."

    - **Metrics Extraction (Machine Readable)**:
       - Keys: snake_case, MUST imply the unit (e.g., use 'count' instead of 'num', 'salary_twd' instead of 'salary').
       - Values: RAW NUMBERS ONLY. No symbols, no text.
         - BAD: "156 people", "$50,000", "3.2%"
         - GOOD: "156", "50000", "0.032"

    - **Entities Extraction**:
       - Extract all unique primary identifiers (IDs, Codes) from the response.
       - This allows the analyze agent to query other modules using these entities.

    - **Key Points**:
       - Max 5 factual observations
       - STRICTLY FORBIDDEN: Recommendations, suggestions, next steps, "User should...".
       - If status is ERROR, describe the error cause factually.

    {{ ctx.output_format }}
  "#
}