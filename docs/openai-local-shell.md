Local shell
===========

Enable agents to run commands in a local shell.

Local shell is a tool that allows agents to run shell commands locally on a machine you or the user provides. It's designed to work with [Codex CLI](https://github.com/openai/codex) and [`codex-mini-latest`](/docs/models/codex-mini-latest). Commands are executed inside your own runtime, **you are fully in control of which commands actually run** —the API only returns the instructions, but does not execute them on OpenAI infrastructure.

Local shell is available through the [Responses API](/docs/guides/responses-vs-chat-completions) for use with [`codex-mini-latest`](/docs/models/codex-mini-latest). It is not available on other models, or via the Chat Completions API.

Running arbitrary shell commands can be dangerous. Always sandbox execution or add strict allow- / deny-lists before forwarding a command to the system shell.

See [Codex CLI](https://github.com/openai/codex) for reference implementation.

How it works
------------

The local shell tool enables agents to run in a continuous loop with access to a terminal.

It sends shell commands, which your code executes on a local machine and then returns the output back to the model. This loop allows the model to complete the build-test-run loop without additional intervention by a user.

As part of your code, you'll need to implement a loop that listens for `local_shell_call` output items and executes the commands they contain. We strongly recommend sandboxing the execution of these commands to prevent any unexpected commands from being executed.

Integrating the local shell tool
--------------------------------

These are the high-level steps you need to follow to integrate the computer use tool in your application:

1. **Send a request to the model**: Include the `local_shell` tool as part of the available tools.

2. **Receive a response from the model**: Check if the response has any `local_shell_call` items. This tool call contains an action like `exec` with a command to execute.

3. **Execute the requested action**: Execute through code the corresponding action in the computer or container environment.

4. **Return the action output**: After executing the action, return the command output and metadata like status code to the model.

5. **Repeat**: Send a new request with the updated state as a `local_shell_call_output`, and repeat this loop until the model stops requesting actions or you decide to stop.

Example workflow
----------------

Below is a minimal (Python) example showing the request/response loop. For brevity, error handling and security checks are omitted—**do not execute untrusted commands in production without additional safeguards**.

```python
import subprocess, os
from openai import OpenAI

client = OpenAI()

# 1) Create the initial response request with the tool enabled
response = client.responses.create(
    model="codex-mini-latest",
    tools=[{"type": "local_shell"}],
    inputs=[
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "text", "text": "List files in the current directory"}],
        }
    ],
)

while True:
    # 2) Look for a local_shell_call in the model's output items
    shell_calls = [item for item in response.output if item["type"] == "local_shell_call"]
    if not shell_calls:
        # No more commands — the assistant is done.
        break

    call = shell_calls[0]
    args = call["action"]

    # 3) Execute the command locally (here we just trust the command!)
    #    The command is already split into argv tokens.
    completed = subprocess.run(
        args["command"],
        cwd=args.get("working_directory") or os.getcwd(),
        env={**os.environ, **args.get("env", {})},
        capture_output=True,
        text=True,
        timeout=(args["timeout_ms"] / 1000) if args["timeout_ms"] else None,
    )

    output_item = {
        "type": "local_shell_call_output",
        "call_id": call["call_id"],
        "output": completed.stdout + completed.stderr,
    }

    # 4) Send the output back to the model to continue the conversation
    response = client.responses.create(
        model="codex-mini-latest",
        tools=[{"type": "local_shell"}],
        previous_response_id=response.id,
        inputs=[output_item],
    )

# Print the assistant's final answer
final_message = next(
    item for item in response.output if item["type"] == "message" and item["role"] == "assistant"
)
print(final_message["content"][0]["text"])
```

Best practices
--------------

* **Sandbox or containerize** execution. Consider using Docker, firejail, or a jailed user account.
* **Impose resource limits** (time, memory, network). The `timeout_ms` provided by the model is only a hint—you should enforce your own limits.
* **Filter or scrutinize** high-risk commands (e.g. `rm`, `curl`, network utilities).
* **Log every command and its output** for auditability and debugging.

### Error handling

If the command fails on your side (non-zero exit code, timeout, etc.) you can still send a `local_shell_call_output`; include the error message in the `output` field.

The model can choose to recover or try executing a different command. If you send malformed data (e.g. missing `call_id`) the API returns a standard `400` validation error.
