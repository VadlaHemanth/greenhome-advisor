# Active explanation provider

The user requested the Xkiro Chat Completions endpoint and model identifier
`qwen/qwen3.8-max:free` on 11 October 2026. The identifier is present in Xkiro's
public catalogue. It is a gateway-reported identifier, not independent proof
of the upstream model's identity or comparative quality.

## Configuration

Set `GREENHOME_LLM_PROVIDER=xkiro`, `XKIRO_MODEL=qwen/qwen3.8-max:free`,
`XKIRO_API_KEY` privately and `GREENHOME_LIVE_LLM=true`. Secrets belong only in
ignored `.env` or a deployment secret manager. The URL is fixed in server code
to `https://api.xkiro.com/v1`; redirects are disabled, and no client request
can choose a destination. The official OpenAI Python SDK is used as a compatible
HTTP client, not as a claim that the provider/model is operated by OpenAI.

Gemini remains an explicit configuration option for reproducibility of earlier
tests. An Xkiro error never silently sends the request to Google or another
provider. The fallback is a local calculation explanation.

## Guarded flow

1. Interpret supported questions with local grammar.
2. Validate and recompute the actual package.
3. Construct claim IDs and server-rendered sentences.
4. After explicit opt-in, send de-identified evidence and the question for one
   JSON claim-selection call. No property identity or saved memory is transmitted.
5. Reject duplicate JSON keys, extra claim fields, invented IDs, free text,
   incomplete generation, tool calls and refusals. Append required caveats.
6. Render approved facts on the server, with explicit provider/live/fallback label.

The API retains the historical `use_gemini` request field and
`gemini_configured` health alias for compatibility. New UI uses `llm_*` metadata
and `live_llm` for a successful Xkiro explanation. The provider name is not hidden.
No LLM calculates the score, value or savings.

Timeout, concurrency and persistent attempt admission are retained. SDK retries
are disabled. A provider's “free” tier is not unlimited capacity or a guarantee
of permanent free access. Existing 100-client tests use local explanations;
they do not establish 100 simultaneous live-provider calls.

## Privacy and source verification

Xkiro's privacy policy, dated 6 July 2026, says request content is forwarded to
its model providers. It describes no routine body retention but permits limited
diagnostic content capture. Its docs also describe provider routing and response
model labels reflecting the requested model. These are provider statements,
not independently audited guarantees, and do not establish UK hosting.

Use fictional test inputs and do not submit real personal/confidential customer
information. Browser consent explains the third-party transfer. Before real
customer deployment, verify processor terms, hosting, downstream providers,
retention, deletion, rights and operational controls.

Primary documents checked on 11 October 2026:
- https://docs.xkiro.com/api/chat-completions/
- https://docs.xkiro.com/api/overview/
- https://docs.xkiro.com/models/tiers/
- https://xkiro.com/privacy
- https://api.xkiro.com/v1/models
- https://github.com/openai/openai-python

Run `scripts/evaluate_active_provider.py` offline by default or explicitly with
`--live` for the bounded fictional integration regression. The small fixed set
does not prove population-level groundedness or true physical predictions.
