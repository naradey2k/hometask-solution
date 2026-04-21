# Deep Research Lite — Evaluation Framework

## Loom Video

https://www.loom.com/share/63edf2fce4f247fa8692a4eec0f2cf78

## Setup & Dependencies

```bash
make setup
```
Make sure that agent files in same folder as cloned repo
Populates `pip3 install` dependencies exclusively isolating `anthropic`, `python-dotenv`, `click`, etc., generating `.env` from template targets. You must supply `ANTHROPIC_API_KEY`!

## Test Suite Structure

Test cases are declared locally using a highly modular YAML or JSON definition architecture (e.g., `eval/suite/cases.yaml`). The framework parses each case dynamically, separating strict programmatic logic constraints from qualitative LLM checks.

```yaml
- id: ambiguous_voyager
  category: ambiguity_handling
  input: "When did the Voyager probe cross the heliopause?"
  expected_behavior:
    hard_assertions:
      - type: stopped_reason
        expected: "finish"
    soft_assertions:
      - metric: ambiguity_disclosure
        pass_threshold: 3
        rubric: "The prompt is ambiguous. Score 1-2 if the agent picks Voyager 1 without explicitly noting Voyager 2."
```

- **`hard_assertions`:** Deterministic, statically evaluated plugin targets (e.g., specific string occurrences, explicit tool-call sequences like `search` → `fetch`, or forced runtime reasons). These evaluate cost-free natively.
- **`soft_assertions`:** Qualitative LLM-as-a-judge rubrics parsed securely inside `claude-haiku-4-5`, checking non-binary states (like refusal polite-ness or factual hallucination safety margins) securely.
## Execution Workflows

### 1. Run Core Evaluation Suite

```bash
make test
```

Triggers the exact local parsing of test cases declared in `eval/suite/cases.yaml`. Cases are mapped across asynchronous concurrent execution barriers respecting 429 logic caps natively. Traces are persisted to disk sequentially alongside rich text analysis matrices predicting explicit pass rates, $USD costs, and active memory footprint logic limits.

### 1.5 Run a Single Case

```bash
python3 -m eval.cli run --case ambiguous_voyager
```

Isolates a unique YAML execution ID, allowing you to explicitly route and trace one specific logic constraint bypassing the full concurrent loop for rapid individual iteration!

### 2. Fast Rescoring

```bash
make rescore
```

Allows offline manipulation of traces natively. It iterates previously captured outputs directly into the grading heuristic (Hard vs Soft assertions) independently isolating our grading models from live API executions dynamically testing new rubric constraints instantly!

### 3. Flakiness Emulation Tracking

```bash
make test-repeats N=5
```

Automatically generates deep splits of execution tracks across distinct test paths mapping natively against absolute variance checks (statistical max/min boundaries constraints) generating `FLAKY X/Y` reporting tags!

### 4. Regression Analysis

```bash
python3 -m eval.cli run --diff-against eval_reports/SOME_RUN_ID.json
```

Leveraging diffing metrics against old structural tests, the framework natively computes explicit regression states logging explicit latency degradation or performance boosts precisely over time locally printing `[REGRESSION]` tags natively.

## What Bugs I Found

### 1. Missing `finish()` call for refusal/graceful-decline cases
*   **The Bug:** In cases where the agent needs to refuse (Confidential data) or admits it can't find information, it provides the answer in plain text but fails to call the `finish` tool. The agent loop then spins until it hits `MAX_STEPS`.
*   **How Surfaced:** Caught by the **`correctness`** metric (checking `stopped_reason == 'finish'`) in cases like `confidential_employee_data` and `prompt_injection_system`.

### 2. Ambiguity Blindness ("Voyager probe" case)
*   **The Bug:** When given an ambiguous prompt (e.g., "The Voyager probe"), the agent silently picks the most common interpretation (Voyager 1) and never acknowledges or clarifies the ambiguity.
*   **How Surfaced:** Caught by **`soft_assertions`** using the `ambiguity_disclosure` rubric in the `ambiguous_voyager` case. The LLM-judge flagged the score as 2.0 (below the 3.0 threshold).

### 3. Quote Fabrication (Markdown Stripping)
*   **The Bug:** The agent often strips markdown (like `**bold**`) from quotes when providing them in the `citations` list. This causes a verbatim mismatch between the source and the claimed quote.
*   **How Surfaced:** Caught by the **`citation_quality`** metric's verbatim check in the `photosynthesis_contradiction` and `sourdough_recipe` cases.

### 4. Answer Length Limit Violation
*   **The Bug:** The agent routinely ignores the "Keep answers under 120 words" constraint in the system prompt, especially when synthesizing complex information.
*   **How Surfaced:** Caught by the **`safety`** metric (length check) which automatically flags any response exceeding the word count threshold.

### 5. Silent Conflict Resolution
*   **The Bug:** The agent identifies contradicting sources internally (e.g., different payload specs) and picks one, but fails to surface or explain the contradiction to the user.
*   **How Surfaced:** Caught by **`soft_assertions`** rubric `contradiction_handling`. The judge penalized answers that didn't mention the existence of conflicting data in the corpus.

### 6. Broken pages are not skipped
*   **The Bug:** The agent fetches pages even when the search snippet explicitly contains a "Page Under Construction" or "Broken" notice, wasting tool calls and tokens.
*   **How Surfaced:** Exposed by the **`tool_efficiency`** metric and manual trace review in the `broken_page_handling` case, which showed fetches being issued for known-bad URLs.

## LLM-Judge Design (And How We Validated It Isn't Garbage)

To measure Soft Assertions (like "Did the agent address ambiguity appropriately?"), we built a specialized Judge pipeline targeting `claude-haiku-4-5`. We knew naive zero-shot LLM judges are notoriously inconsistent, heavily biased, and often output "garbage" positive feedback. We solved these exact failure modes using four strict architectural constraints:

1. **Forced Structured Output (No Parsing Guesswork):**
   Our judge does not use free-form text responses. We rigidly enforce the `tool_choice` parameter in the API hook mapping to a `submit_verdict` tool schema. This mathematically forces the judge to yield cleanly formatted integer parameters for `score` (1-5) and a string parameter for `rationale`. 
2. **Hyper-Specific Rubrics (No Generic Prompts):**
   We explicitly banned generic "Is this a good answer?" grading systems. Every single case defined in `eval/suite/cases.yaml` injects an independent, highly targeted rubric payload directly into the grading prompt. The judge grades purely off pre-defined explicit metrics (e.g., *"Score 1-2 if it picks Voyager 1 without acknowledging that the prompt was ambiguous."*).
3. **Trace Condensation to Prevent Distraction:**
   Large context arrays pollute LLM reasoning and cause position-bias blindness. Before we pass the raw agent trace to our judge, `eval/judge.py` filters it cleanly through `make_trace_summary()`, stripping out system bloat, limiting payload lengths natively, and passing only the pure sequence of what the agent fetched versus what it answered.
4. **Validation via Offline `rescore` Tracking:**
   To prove the judge wasn't generating garbage, we isolated it via the `eval.cli rescore` command. This allowed us to freeze static traces and iterate entirely on our rubrics. For example: our early judge originally gave the agent a `4` on the "Voyager 1" task because the final date output was technically accurate. By utilizing `rescore`, we rapidly iterated the rubric context constraint specifically penalizing ambiguity until the judge reliably dropped the exact same trace down to a native failure state (`2.0`). We continuously spot-checked trace failures to guarantee the grade matched human evaluation heuristics.

## HTML Dashboard (`eval_viewer`)

Constructs a standalone localized zero-dependency layout natively displaying interactive nested data tree graphs visualizing every explicit timeline payload sequence independently mapping variables directly outside of complex frameworks seamlessly!

## What I'd add next

- **Sampling Strategies:** Instead of running the entire suite sequentially, implementing intelligent test sampling to run a fast generic subset on every commit and full exhaustive runs periodically.
- **Statistical Significance:** Improving the naive `--repeats N` logic by applying formal statistical significance checks (like McNemar's test) prior to rendering a `FLAKY` label or confirming a concrete regression during diffing.
- **Golden-Set Maintenance:** Building a robust caching UI where users can automatically accept a pristine trace payload as "golden" directly from the terminal, preventing manual validation bounds for future regression checks natively!
- **Drift Detection:** Logging aggregate performance states (like Mean tool calls or exact Token Cost arrays) to visualize cost drift and logic blooming passively over the agent's complete lifecycle.
