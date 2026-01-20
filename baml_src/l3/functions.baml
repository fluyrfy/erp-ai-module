// ═══════════════════════════════════════════════════════════════════
// L3 Generic Agent - Functions
// ═══════════════════════════════════════════════════════════════════

// Step 1: Select which API to call
function SelectApi(
  task: Task,
  api_doc: string,
  module_context: string,
  postprocess_doc: string
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

    === AVAILABLE POSTPROCESS STRATEGIES (schema + descriptions) ===
    {{ postprocess_doc }}

    TASK:
    1. List ALL APIs needed.
    2. Set depends_on for each API.
    3. For APIs with dependencies, pre-plan field_mappings.
    4  Decide optional `postprocess` per call using this rule:
    - Default: postprocess = null.
    - Only set postprocess when BOTH conditions hold:
      (a) The task goal explicitly requires aggregation/statistics or ordering/ranking on this call’s data.
      (b) The required field(s) explicitly exist in this call’s response schema (typically under data.records[*].<field>).
    - If either (a) or (b) is not satisfied, postprocess MUST be null.

    *** CRITICAL RULES ***
    1. CHECK PARAMETERS: Before creating a field_mapping, verify that the 'to_param' explicitly exists in the target API's definition.
      - REQUEST-PARAM ONLY (MANDATORY):
        - 'to_param' MUST be a request field of the target API (query parameter or request body field).
        - NEVER map into response-only fields (e.g., fields that appear only under response data.records[*]).
        - If the target API does not expose the needed request field, the mapping MUST be omitted.
      - NO FAKE FILTERS VIA IDS (MANDATORY):
        - Do NOT use 'ids' (or any identifier param) to emulate missing filters.
        - If a desired filter is not an explicit request field, fetch broader data and filter later.

    2. NO HALLUCINATED REQUEST FIELDS: If a request field is not explicitly defined for the target API, omit the mapping.

    3. DATA DEPENDENCY: Ensure the 'from_field' path actually exists in the source API's response schema.

    4. REFERENCE TRAVERSAL (MANDATORY):
      - When only an ID reference is available, plan intermediate fetches step-by-step; never skip required hops.

    5. ENTITY-AWARE MAPPING COMPATIBILITY (MANDATORY):
      - For every API call, infer its primary entity type from path/name/context and treat its identifier fields as entity-scoped identifiers (e.g., ids, id, *Id).
      - A field_mapping that injects into any identifier parameter (including but not limited to 'ids' and '*Id') MUST satisfy semantic compatibility:
        1) The source value’s entity type MUST match the target parameter’s expected entity type for the target API call.
        2) The source value’s identifier kind MUST match the target parameter’s identifier kind (e.g., employee_id cannot be used where department_id is expected).
      - Do NOT perform identifier substitution to emulate missing filters. If the target API lacks an explicit filter for the desired entity (e.g., no departmentId filter for employee listing), you MUST NOT force it via 'ids' or any other identifier parameter. Instead, fetch broader data and filter in a later stage.
      - For each field_mapping, you MUST output 'mapping_type' and 'reason' (semantic justification).


    {{ ctx.output_format }}
  "#
}

// ═══════════════════════════════════════════════════════════════════
// 針對 GET 
// ═══════════════════════════════════════════════════════════════════
function GenerateQueryParams(
  task: Task,
  parameter_schema: string
) -> GetParams {
  client GPT4oMini
  prompt #"
    You are an API Parameter Generator for a GET request.
    Generate the Query String parameters based on the goal.

    === GOAL ===
    Action: {{ task.action_required }}
    Filters: {{ task.search_criteria }}

    === ALLOWED QUERY PARAMETERS ===
    {{ parameter_schema }}

    *** RULES ***
    1. Use ONLY the keys defined in ALLOWED QUERY PARAMETERS.
    2. Do NOT invent fields.
    3. If a parameter is missing or ambiguous, leave it out.

    {{ ctx.output_format }}
  "#
}

// ═══════════════════════════════════════════════════════════════════
// 針對 POST / PUT / DELETE
// ═══════════════════════════════════════════════════════════════════
function GenerateBodyParams(
  task: Task,
  parameter_schema: string
) -> BodyParams {
  client GPT4oMini
  prompt #"
    You are an API Payload Generator for a POST/PUT request.
    Generate the JSON Body based on the goal.

    === GOAL ===
    Action: {{ task.action_required }}
    Filters: {{ task.search_criteria }}

    === ALLOWED BODY FIELDS (JSON Schema) ===
    {{ parameter_schema }}

    *** RULES ***
    1. Use ONLY the keys defined in ALLOWED BODY FIELDS.
    2. Output a valid JSON string structure matching the schema.
    3. Do NOT invent fields.

    {{ ctx.output_format }}
  "#
}


function GeneratePostProcessPlan(
  task: Task,
  response_schema_context: string
) -> PostProcessPlan {
  client GPT4oMini
  prompt #"
    Analyze the API response schema to determine the best post-processing strategy.

    === GOAL ===
    {{ task.action_required }}

    === RESPONSE SCHEMA (Fields & Descriptions) ===
    {{ response_schema_context }}

    *** INSTRUCTIONS ***
    1. Determine the user's intent (List vs Count vs Sort).
    2. Instantiate the appropriate Strategy class defined in the output format.
    3. Follow the specific field descriptions to fill the parameters.

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

    CORE RULES (MANDATORY):
    1) Goal Alignment:
      - Your answer must directly satisfy the goal using available data.
      - If the goal cannot be satisfied, set answer and explain the exact missing data in missing_info.

    2) Answer Preservation:
      - If raw_data contains a human-readable value that satisfies the goal (e.g., a name/label/title), you MUST surface it in answer.
      - IDs/codes are only secondary evidence unless the goal explicitly asks for an ID/code.

    3) No Hallucination:
      - Use only fields that exist in raw_data. Do not invent filters, entities, or values.

    4) Reference Resolution:
      - If the answer requires resolving references (e.g., id -> object -> property):
        - If the needed object/property is already present in raw_data, resolve it and answer.
        - If not present, list what must be fetched in missing_info (do NOT guess).

    5) Evidence Discipline:
      - Provide minimal but sufficient evidence paths from raw_data in "evidence" so a downstream agent can verify.


    {{ ctx.output_format }}
  "#
}