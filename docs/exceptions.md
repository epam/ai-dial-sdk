# Exceptions

The SDK turns exceptions into Unified API error responses. Everything on the wire comes from **one class, `aidial_sdk.HTTPException`** — the subclasses only preset a status code and a few fields. Raise one of them from your deployment and the caller gets it verbatim; raise anything else and the caller gets a generic 500 while the real reason goes to the log.

```python
from aidial_sdk.exceptions import InvalidRequestError

raise InvalidRequestError("The 'format' parameter must be 'json' or 'text'.")
```

## The response body

`json_error()` builds the body and drops every key whose value is `None`, so a minimal error carries just three fields:

```json
{"error": {"message": "Api-Key header is required", "type": "invalid_request_error", "code": "400"}}
```

| Field | Default | Purpose |
| --- | --- | --- |
| `message` | required | Returned to the caller and logged. Technical detail is fine here. |
| `type` | `runtime_error` | Error class identifier. |
| `code` | `str(status_code)` | Machine-readable code. Numeric string unless a subclass sets one. |
| `param` | omitted | The request field at fault. |
| `display_message` | omitted | Shown to the end user in DIAL Chat. `message` is not. |

Any extra keyword argument you pass is merged into the same object, so you can carry your own fields:

```python
raise HTTPException("Test error", 503, status=503, details="error details")
```
```json
{"error": {"message": "Test error", "type": "runtime_error", "details": "error details", "status": 503, "code": "503"}}
```

`headers` is the exception: it sets HTTP response headers rather than body fields, which is how you return `Retry-After` alongside a 429.

## The classes

| Class | Status | `type` | `code` |
| --- | --- | --- | --- |
| `HTTPException` | `500`, override it | `runtime_error` | `str(status_code)` |
| `InvalidRequestError` | `400` | `invalid_request_error` | `"400"` |
| `ContextLengthExceededError` | `400` | `invalid_request_error` | `context_length_exceeded` |
| `TruncatePromptSystemError` | `400` | `invalid_request_error` | `truncate_prompt_error` |
| `TruncatePromptSystemAndLastUserError` | `400` | `invalid_request_error` | `truncate_prompt_error` |
| `RequestValidationError` | `422` | `invalid_request_error` | `"422"` |
| `ResourceNotFoundError` | `404` | `runtime_error` | `"404"` |
| `DeploymentNotFoundError` | `404` | `runtime_error` | `DeploymentNotFound` |
| `RuntimeServerError` | `500` | `runtime_error` | `"500"` |
| `InternalServerError` | `500` | `internal_server_error` | `"500"` |

Only `HTTPException` takes a status code. Every subclass pins its own, and passing `status_code=` to one is a `TypeError`.

Most subclasses accept the remaining fields as keyword arguments, so you can add a `display_message` or your own keys. Three do not — they compose their message from numbers you supply and take nothing else:

```python
raise ContextLengthExceededError(max_context_length=8192, prompt_tokens=9500)
```
```txt
→ This model's maximum context length is 8192 tokens. However, your messages
  resulted in 9500 tokens. Please reduce the length of the messages.
```

`TruncatePromptSystemError` and `TruncatePromptSystemAndLastUserError` behave the same way and additionally set `display_message` to that text, because it is already phrased for the end user. They are for `truncate_prompt` implementations; `param` is `max_prompt_tokens`, against `messages` for `ContextLengthExceededError`.

`DeploymentNotFoundError` is the only class with a non-numeric `code`.

## Anything else you raise

An exception that is not one of these is caught, logged with its traceback, and replaced. The caller always sees exactly this, whatever went wrong:

```json
{"error": {"message": "Error during processing the request", "type": "runtime_error", "code": "500"}}
```

This applies to `ValueError`, `ZeroDivisionError` and everything else — and to `fastapi.HTTPException`, which gets no special treatment inside a deployment. If you want a status code other than 500 to reach the caller, raise one of the SDK's classes.

An invalid request body never reaches your code. It is rejected earlier as a `400`, with a message naming the offending path:

```txt
→ Your request contained invalid structure on path body.messages.0.role.
  field required
```

## Failing after the response has started

Once the first chunk of a streaming response is on the wire the status code is already `200` and cannot be changed. The SDK therefore writes the error into the stream as a data chunk, and still terminates it normally:

```txt
data: {"choices":[{"index":0,"delta":{"role":"assistant"}}],...}
data: {"choices":[{"index":0,"delta":{"content":"Partial content"}}],...}
data: {"error":{"message":"Something went wrong!","type":"runtime_error","code":"500"}}
data: [DONE]
```

The choice is left open — no `finish_reason` is emitted — so a client that assumes every choice closes will need to handle this. Fail before producing output and you get an ordinary HTTP error response instead, even for a streaming request.

One case is easy to miss: returning from `chat_completion` having produced fewer choices than `n` is also an error, and yields the same generic `Error during processing the request` chunk.

## Deprecated helpers

Nine snake_case factory functions remain for backwards compatibility and emit a `DeprecationWarning`. Call the class instead:

| Deprecated | Use |
| --- | --- |
| `resource_not_found_error` | `ResourceNotFoundError` |
| `deployment_not_found_error` | `DeploymentNotFoundError` |
| `request_validation_error` | `RequestValidationError` |
| `invalid_request_error` | `InvalidRequestError` |
| `context_length_exceeded_error` | `ContextLengthExceededError` |
| `truncate_prompt_error_system` | `TruncatePromptSystemError` |
| `truncate_prompt_error_system_and_last_user` | `TruncatePromptSystemAndLastUserError` |
| `runtime_server_error` | `RuntimeServerError` |
| `internal_server_error` | `InternalServerError` |
