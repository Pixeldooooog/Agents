import { describe, expect, test } from "bun:test";
import { sdkMessagesFromRuntimeEvent } from "@agents/core/sdk";
import type { RuntimeEvent } from "../src/index.js";

describe("SDK event projection", () => {
  test("projects user runtime messages with replay metadata", () => {
    expect(project({
      type: "user_message",
      name: "user",
      payload: {
        uuid: "user_1",
        session_id: "session_from_event",
        message: {
          role: "user",
          content: [{ type: "text", text: "hello " }, { type: "text", text: "sdk" }]
        },
        parent_tool_use_id: "tool_parent",
        timestamp: "2026-06-10T00:00:00.000Z",
        isSynthetic: true,
        tool_use_result: { ok: true },
        priority: "now",
        isReplay: false
      }
    })[0]).toEqual({
      type: "user_message",
      uuid: "user_1",
      sessionId: "session_from_event",
      content: "hello sdk",
      message: {
        role: "user",
        content: [{ type: "text", text: "hello " }, { type: "text", text: "sdk" }]
      },
      parentToolUseId: "tool_parent",
      isSynthetic: true,
      toolUseResult: { ok: true },
      priority: "now",
      timestamp: "2026-06-10T00:00:00.000Z",
      isReplay: false
    });
  });

  test("projects model messages with assistant API payload parity", () => {
    const rawMessage = {
      id: "raw_msg_1",
      type: "message",
      role: "assistant",
      content: [{ type: "text", text: "raw assistant text" }]
    };
    expect(project({
      type: "model_message",
      name: "assistant",
      payload: {
        raw: { message: rawMessage },
        parent_tool_use_id: "tool_parent",
        error: "rate_limit",
        uuid: "assistant_1",
        model_usage: { totalTokens: 9 }
      }
    })[0]).toEqual({
      type: "assistant_message",
      runId: "run_1",
      sessionId: "session_1",
      content: "raw assistant text",
      message: rawMessage,
      parentToolUseId: "tool_parent",
      error: "rate_limit",
      uuid: "assistant_1",
      modelUsage: { totalTokens: 9 }
    });

    expect(project({
      type: "model_message",
      name: "assistant",
      payload: {
        message_id: "fallback_msg_1",
        content: "fallback assistant text",
        model: "gpt-test",
        stop_reason: "end_turn",
        usage: { input_tokens: 2 }
      }
    })[0]).toMatchObject({
      type: "assistant_message",
      content: "fallback assistant text",
      message: {
        id: "fallback_msg_1",
        type: "message",
        role: "assistant",
        content: [{ type: "text", text: "fallback assistant text" }],
        model: "gpt-test",
        stop_reason: "end_turn",
        usage: { input_tokens: 2 }
      },
      uuid: "fallback_msg_1"
    });
  });

  test("projects explicit SDK runtime events into first-class stream messages", () => {
    expect(project({
      type: "model_retry",
      name: "openai",
      payload: {
        failed_attempt: 1,
        max_retries: 3,
        delay_seconds: 1.25,
        status_code: 429,
        error: { message: "rate limited" }
      }
    })[0]).toMatchObject({
      type: "system",
      subtype: "api_retry",
      attempt: 2,
      maxRetries: 3,
      retryDelayMs: 1250,
      errorStatus: 429,
      error: { message: "rate limited" }
    });

    expect(project({
      type: "model_recovery",
      name: "fallback",
      payload: {
        attempt: 2,
        maxAttempts: 3,
        stopReason: "rate_limit",
        message: "retrying",
        uuid: "recovery_1"
      }
    })[0]).toMatchObject({
      type: "system",
      subtype: "model_recovery",
      reason: "fallback",
      attempt: 2,
      maxAttempts: 3,
      stopReason: "rate_limit",
      message: "retrying",
      uuid: "recovery_1"
    });

    expect(project({
      type: "rate_limit_event",
      payload: { rate_limit_info: { retryAfterMs: 500 }, uuid: "rate_1" }
    })[0]).toEqual({
      type: "rate_limit_event",
      runId: "run_1",
      sessionId: "session_1",
      rateLimitInfo: { retryAfterMs: 500 },
      uuid: "rate_1"
    });

    expect(project({
      type: "local_command_output",
      payload: { content: "<local-command-stdout>ok</local-command-stdout>", uuid: "local_1" }
    })[0]).toMatchObject({
      type: "system",
      subtype: "local_command_output",
      content: "ok",
      uuid: "local_1"
    });

    expect(project({
      type: "done",
      payload: {
        status: "error",
        content: "",
        error: "tool-call loop exceeded max iterations",
        duration_ms: 42,
        num_turns: 3,
        event_count: 7,
        modelUsage: { totalTokens: 128 }
      }
    })[0]).toMatchObject({
      type: "result",
      status: "error",
      subtype: "error_during_execution",
      content: "",
      result: "",
      isError: true,
      durationMs: 42,
      numTurns: 3,
      eventCount: 7,
      errors: ["tool-call loop exceeded max iterations"],
      modelUsage: { totalTokens: 128 }
    });
  });

  test("projects hook, elicitation, prompt, and turn summary events", () => {
    expect(project({
      type: "hook_response",
      payload: {
        hook_id: "hook_1",
        hook_name: "lint",
        hook_event: "post_tool_use",
        output: "ok",
        stdout: "ok",
        stderr: "",
        exit_code: 0,
        outcome: "success",
        uuid: "hook_response_1"
      }
    })[0]).toMatchObject({
      type: "system",
      subtype: "hook_response",
      hookId: "hook_1",
      hookName: "lint",
      hookEvent: "post_tool_use",
      exitCode: 0,
      outcome: "success"
    });

    expect(project({
      type: "elicitation_complete",
      payload: { mcp_server_name: "forms", elicitation_id: "ask_1", uuid: "elicitation_1" }
    })[0]).toMatchObject({
      type: "system",
      subtype: "elicitation_complete",
      mcpServerName: "forms",
      elicitationId: "ask_1"
    });

    expect(project({
      type: "prompt_suggestion",
      payload: { suggestion: "Run tests", uuid: "suggestion_1" }
    })[0]).toEqual({
      type: "prompt_suggestion",
      runId: "run_1",
      sessionId: "session_1",
      suggestion: "Run tests",
      uuid: "suggestion_1"
    });

    expect(project({
      type: "post_turn_summary",
      payload: {
        summarizes_uuid: "message_1",
        status_category: "review_ready",
        status_detail: "ready",
        is_noteworthy: true,
        title: "Ready",
        description: "Patch is ready",
        recent_action: "Ran checks",
        needs_action: "Review",
        artifact_urls: ["file://patch"],
        uuid: "summary_1"
      }
    })[0]).toMatchObject({
      type: "system",
      subtype: "post_turn_summary",
      summarizesUuid: "message_1",
      statusCategory: "review_ready",
      isNoteworthy: true,
      artifactUrls: ["file://patch"]
    });

    expect(project({
      type: "status",
      name: "status",
      payload: { uuid: "status_1", status: "compacting", permissionMode: "ask" }
    })[0]).toEqual({
      type: "system",
      subtype: "status",
      runId: "run_1",
      sessionId: "session_1",
      status: "compacting",
      permissionMode: "ask",
      uuid: "status_1"
    });
  });

  test("projects rich tool progress contracts and auth side-channel results", () => {
    expect(project({
      type: "tool_progress",
      name: "shell.run",
      payload: {
        tool_use_id: "tool_1",
        toolName: "shell.run",
        status: "stalled",
        input: { command: "make check" },
        result: { partial: true },
        contract: {
          activity: { phase: "waiting" },
          target: "make check",
          paths: ["packages/core"],
          metadata: { kind: "shell" }
        },
        metadata: { source: "runtime" },
        output: "partial",
        full_output: "partial output",
        elapsed_time_seconds: 2.5,
        total_lines: 3,
        total_bytes: 32,
        task_id: "task_1",
        timeout_ms: 30000
      }
    })[0]).toMatchObject({
      type: "tool_progress",
      toolCallId: "tool_1",
      name: "shell.run",
      status: "stalled",
      activity: { phase: "waiting" },
      target: "make check",
      paths: ["packages/core"],
      metadata: { kind: "shell", source: "runtime" },
      fullOutput: "partial output",
      elapsedTimeSeconds: 2.5,
      totalLines: 3,
      totalBytes: 32,
      taskId: "task_1",
      timeoutMs: 30000
    });

    const authMessages = project({
      type: "tool_result",
      name: "github__authenticate",
      payload: {
        tool_call_id: "auth_call",
        name: "github__authenticate",
        is_error: false,
        content: JSON.stringify({
          status: "auth_url",
          message: "Open browser",
          authUrl: "https://example.test/auth"
        })
      }
    });

    expect(authMessages.map((message) => message.type)).toEqual(["tool_progress", "tool_result", "auth_status"]);
    expect(authMessages[2]).toMatchObject({
      type: "auth_status",
      isAuthenticating: true,
      output: ["Open browser", "https://example.test/auth"],
      error: "",
      metadata: {
        status: "auth_url",
        message: "Open browser",
        authUrl: "https://example.test/auth"
      }
    });
  });

  test("projects legacy tool result error fields as failed results", () => {
    const messages = project({
      type: "tool_result",
      name: "shell.run",
      payload: {
        tool_call_id: "tool_error_1",
        name: "shell.run",
        error: "command failed"
      }
    });

    expect(messages[0]).toMatchObject({
      type: "tool_progress",
      toolCallId: "tool_error_1",
      name: "shell.run",
      status: "failed",
      error: "command failed"
    });
    expect(messages[1]).toMatchObject({
      type: "tool_result",
      toolName: "shell.run",
      toolCallId: "tool_error_1",
      content: "command failed",
      isError: true
    });
  });

  test("normalizes legacy tool call id aliases across tool lifecycle events", () => {
    expect(project({
      type: "tool_start",
      name: "shell.run",
      payload: {
        toolCallId: "tool_camel_start",
        arguments: { command: "pwd" }
      }
    })[0]).toMatchObject({
      type: "tool_progress",
      toolCallId: "tool_camel_start",
      status: "started",
      input: { command: "pwd" }
    });

    expect(project({
      type: "tool_start",
      name: "shell.run",
      payload: {
        id: "tool_start_id",
        arguments: { command: "date" }
      }
    })[0]).toMatchObject({
      type: "tool_progress",
      toolCallId: "tool_start_id",
      input: { command: "date" }
    });

    const generatedStartId = (project({
      type: "tool_start",
      name: "shell.run",
      payload: { arguments: { command: "whoami" } }
    })[0] as any).toolCallId;
    expect(generatedStartId).toBeTruthy();

    const resultMessages = project({
      type: "tool_result",
      name: "shell.run",
      payload: {
        tool_use_id: "tool_legacy_result",
        content: "ok"
      }
    });
    expect(resultMessages[0]).toMatchObject({
      type: "tool_progress",
      toolCallId: "tool_legacy_result",
      status: "completed"
    });
    expect(resultMessages[1]).toMatchObject({
      type: "tool_result",
      toolCallId: "tool_legacy_result",
      content: "ok",
      isError: false
    });

    expect(project({
      type: "tool_result",
      name: "artifact.save",
      payload: {
        id: "artifact_result_id",
        content: "saved"
      }
    })[0]).toMatchObject({
      type: "tool_progress",
      toolCallId: ""
    });

    const approvalMessages = project({
      type: "tool_approval_required",
      name: "shell.run",
      payload: {
        approvalId: "approval_camel",
        tool_call: {
          toolUseId: "tool_nested_approval",
          name: "shell.run",
          arguments: { command: "deploy" }
        },
        permission: { reason: "manual review" }
      }
    });
    expect(approvalMessages[0]).toMatchObject({
      type: "tool_progress",
      toolCallId: "tool_nested_approval",
      status: "awaiting_approval"
    });
    expect(approvalMessages[1]).toMatchObject({
      type: "approval_required",
      approvalId: "approval_camel",
      toolName: "shell.run",
      arguments: { command: "deploy" },
      reason: "manual review"
    });

    const generatedApprovalMessages = project({
      type: "tool_approval_required",
      name: "shell.run",
      payload: {
        tool_call: { name: "shell.run", arguments: { command: "review" } },
        permission: { reason: "missing id" }
      }
    }) as any[];
    expect(generatedApprovalMessages[0].toolCallId).toBeTruthy();
    expect(generatedApprovalMessages[1].approvalId).toBe(generatedApprovalMessages[0].toolCallId);

    expect(project({
      type: "tool_approval_decision",
      name: "shell.run",
      payload: {
        approved: false,
        tool_call: {
          toolCallId: "tool_nested_decision",
          name: "shell.run"
        }
      }
    })[0]).toMatchObject({
      type: "tool_progress",
      toolCallId: "tool_nested_decision",
      status: "denied"
    });
  });

  test("projects legacy task tool aliases into side-channel task messages", () => {
    const started = project({
      type: "tool_result",
      name: "TaskCreate",
      payload: {
        tool_call_id: "task_create_call",
        content: JSON.stringify({
          task: {
            task_id: "task_legacy_start",
            title: "Legacy task",
            input: "Run legacy task",
            metadata: { task_type: "agent", workflow_name: "review" }
          }
        })
      }
    });

    expect(started.find((message) => message.type === "system" && (message as any).subtype === "task_started")).toMatchObject({
      taskId: "task_legacy_start",
      toolUseId: "task_create_call",
      description: "Legacy task",
      taskType: "agent",
      workflowName: "review",
      prompt: "Run legacy task"
    });

    const progress = project({
      type: "tool_result",
      name: "TaskUpdate",
      payload: {
        tool_call_id: "task_update_call",
        content: JSON.stringify({
          task: { task_id: "task_legacy_start", title: "Legacy task" },
          step: { name: "shell.run", output: "compiled" },
          usage: { total_tokens: 12, tool_uses: 2, duration_ms: 34 }
        })
      }
    });

    expect(progress.find((message) => message.type === "system" && (message as any).subtype === "task_progress")).toMatchObject({
      taskId: "task_legacy_start",
      toolUseId: "task_update_call",
      lastToolName: "shell.run",
      summary: "compiled",
      usage: {
        totalTokens: 12,
        toolUses: 2,
        durationMs: 34,
        total_tokens: 12,
        tool_uses: 2,
        duration_ms: 34
      }
    });

    const completed = project({
      type: "tool_result",
      name: "Task",
      payload: {
        tool_call_id: "task_run_call",
        content: JSON.stringify({
          status: "succeeded",
          output_file: "result.md",
          task: { task_id: "task_legacy_start", title: "Legacy task", status: "succeeded" },
          result: { content: "done" }
        })
      }
    });

    expect(completed.filter((message) => message.type === "system").map((message) => (message as any).subtype)).toEqual([
      "task_started",
      "task_notification"
    ]);
    expect(completed.find((message) => message.type === "system" && (message as any).subtype === "task_notification")).toMatchObject({
      taskId: "task_legacy_start",
      toolUseId: "task_run_call",
      status: "completed",
      outputFile: "result.md",
      summary: "done"
    });

    const backgrounds = project({
      type: "tool_result",
      name: "TaskBackgrounds",
      payload: {
        content: JSON.stringify({
          background_tasks: [{
            task_id: "task_background_1",
            result: {
              status: "timeout",
              task: { task_id: "task_background_1", status: "timeout" }
            }
          }]
        })
      }
    });

    expect(backgrounds.find((message) => message.type === "system" && (message as any).subtype === "task_notification")).toMatchObject({
      taskId: "task_background_1",
      status: "failed"
    });
  });

  test("projects direct task lifecycle runtime events", () => {
    expect(project({
      type: "task_started",
      name: "shell.run",
      payload: {
        task_id: "shell_123",
        tool_call_id: "shell_run_call",
        description: "Run background shell",
        metadata: { task_type: "shell", workflow_name: "checks" },
        prompt: "python -m pytest"
      }
    })[0]).toEqual({
      type: "system",
      subtype: "task_started",
      runId: "run_1",
      sessionId: "session_1",
      taskId: "shell_123",
      toolUseId: "shell_run_call",
      description: "Run background shell",
      taskType: "shell",
      workflowName: "checks",
      prompt: "python -m pytest"
    });

    expect(project({
      type: "task_notification",
      name: "shell.output",
      payload: {
        task_id: "shell_123",
        tool_call_id: "shell_output_call",
        status: "succeeded",
        output_file: ".agents/task-output/shell_123.log",
        summary: "tests passed",
        usage: { total_tokens: 10, tool_uses: 2, duration_ms: 42 }
      }
    })[0]).toEqual({
      type: "system",
      subtype: "task_notification",
      runId: "run_1",
      sessionId: "session_1",
      taskId: "shell_123",
      toolUseId: "shell_output_call",
      status: "completed",
      outputFile: ".agents/task-output/shell_123.log",
      summary: "tests passed",
      usage: {
        totalTokens: 10,
        toolUses: 2,
        durationMs: 42,
        total_tokens: 10,
        tool_uses: 2,
        duration_ms: 42
      }
    });

    expect(project({
      type: "task_notification",
      payload: { task_id: "shell_123", status: "running" }
    })).toEqual([]);
  });
});

function project(event: RuntimeEvent) {
  return sdkMessagesFromRuntimeEvent("run_1", "session_1", event);
}
