import { AgentSdkClient } from "./agentSdkClient.js";
import { SdkJsonlDecodeError, SdkStdinDecodeError } from "./sdkJsonl.js";
import { SdkHybridJsonlTransport } from "./sdkHybridJsonlTransport.js";
import { SdkQueueJsonlTransport } from "./sdkQueueJsonlTransport.js";
import { SdkRetryableBatchError, SdkSerialBatchUploader } from "./sdkSerialBatchUploader.js";
import { SdkSession } from "./sdkSession.js";
import { SdkSseJsonlTransport, SdkSseLivenessTimeoutError } from "./sdkSseJsonlTransport.js";
import {
  SdkControlRequestCancelledError,
  SdkControlRequestError,
  SdkControlStreamClosedError,
  SdkStructuredIo
} from "./sdkStructuredIo.js";
import { SdkWebSocketJsonlTransport } from "./sdkWebSocketJsonlTransport.js";
import type {
  SdkControlCancelRequestMessage,
  SdkControlErrorResponse,
  SdkControlInitializeRequest,
  SdkControlMessage,
  SdkControlPermissionRequest,
  SdkControlRequestMessage,
  SdkControlRequestPayload,
  SdkControlResponseMessage,
  SdkControlSuccessResponse,
  SdkElicitationRequest,
  SdkHookCallbackRequest,
  SdkKeepAliveMessage,
  SdkStdinMessage,
  SdkStdoutMessage,
  SdkUpdateEnvironmentVariablesMessage
} from "./sdkControlTypes.js";
import type {
  SdkApiRetryMessage,
  SdkAssistantMessage,
  SdkAuthStatusMessage,
  SdkCompactBoundaryMessage,
  SdkElicitationCompleteMessage,
  SdkFilesPersistedMessage,
  SdkHookProgressMessage,
  SdkHookResponseMessage,
  SdkHookStartedMessage,
  SdkLocalCommandOutputMessage,
  SdkMessage,
  SdkModelRecoveryMessage,
  SdkPostTurnSummaryMessage,
  SdkPromptSuggestionMessage,
  SdkRateLimitEventMessage,
  SdkResultMessage,
  SdkSessionStateChangedMessage,
  SdkStatusMessage,
  SdkStreamEventMessage,
  SdkSystemMessage,
  SdkTaskNotificationMessage,
  SdkTaskProgressMessage,
  SdkTaskStartedMessage,
  SdkToolProgressMessage,
  SdkToolUseSummaryMessage,
  SdkUserMessage
} from "./sdkMessages.js";
import type { SdkQueryOptions } from "./sdkQueryOptions.js";
import type { SdkForkSessionOptions, SdkForkSessionResult } from "./sdkSessionMutations.js";
import type {
  SdkGetSessionMessagesOptions,
  SdkListSessionsOptions,
  SdkSessionInfo
} from "./sdkSessionRecords.js";
import type { SdkSseFrame } from "./sdkSseFrames.js";
import type {
  SdkSseCloseHandler,
  SdkSsePostHandler,
  SdkSseReadChunksFactory
} from "./sdkSseJsonlTransport.js";
import type {
  SdkBatchDropHandler,
  SdkBatchSendHandler
} from "./sdkSerialBatchUploader.js";
import type { SdkHybridPostHandler } from "./sdkHybridJsonlTransport.js";
import type { SdkJsonlTransport } from "./sdkJsonlTransport.js";
import type {
  SdkWebSocketConnectOptions,
  SdkWebSocketConnector
} from "./sdkWebSocketConnection.js";
import type { SdkWebSocketCloseHandler } from "./sdkWebSocketJsonlTransport.js";

type SdkControlPayloadOf<Subtype extends SdkControlRequestPayload["subtype"]> =
  Extract<SdkControlRequestPayload, { subtype: Subtype }>;

export const AgentSDKClient = AgentSdkClient;
export const SDKHybridJsonlTransport = SdkHybridJsonlTransport;
export const SDKJsonlDecodeError = SdkJsonlDecodeError;
export const SDKQueueJsonlTransport = SdkQueueJsonlTransport;
export const SDKRetryableBatchError = SdkRetryableBatchError;
export const SDKSerialBatchUploader = SdkSerialBatchUploader;
export const SDKSSEJsonlTransport = SdkSseJsonlTransport;
export const SDKSSELivenessTimeoutError = SdkSseLivenessTimeoutError;
export const SDKSession = SdkSession;
export const SDKStdinDecodeError = SdkStdinDecodeError;
export const SDKStructuredIO = SdkStructuredIo;
export const SDKControlRequestCancelledError = SdkControlRequestCancelledError;
export const SDKControlRequestError = SdkControlRequestError;
export const SDKControlStreamClosedError = SdkControlStreamClosedError;
export const SDKWebSocketJsonlTransport = SdkWebSocketJsonlTransport;

export type AgentSDKClient = AgentSdkClient;
export type SDKAPIRetryMessage = SdkApiRetryMessage;
export type SDKAssistantMessage = SdkAssistantMessage;
export type SDKAuthStatusMessage = SdkAuthStatusMessage;
export type SDKBatchDropHandler = SdkBatchDropHandler;
export type SDKBatchSendHandler = SdkBatchSendHandler;
export type SDKCompactBoundaryMessage = SdkCompactBoundaryMessage;
export type SDKControlApplyFlagSettingsRequest = SdkControlPayloadOf<"apply_flag_settings">;
export type SDKControlCancelAsyncMessageRequest = SdkControlPayloadOf<"cancel_async_message">;
export type SDKControlCancelRequest = SdkControlCancelRequestMessage;
export type SDKControlElicitationRequest = SdkElicitationRequest;
export type SDKControlErrorResponse = SdkControlErrorResponse;
export type SDKControlGetContextUsageRequest = SdkControlPayloadOf<"get_context_usage">;
export type SDKControlGetSettingsRequest = SdkControlPayloadOf<"get_settings">;
export type SDKControlInitializeRequest = SdkControlInitializeRequest;
export type SDKControlInterruptRequest = SdkControlPayloadOf<"interrupt">;
export type SDKControlMcpMessageRequest = SdkControlPayloadOf<"mcp_message">;
export type SDKControlMcpReconnectRequest = SdkControlPayloadOf<"mcp_reconnect">;
export type SDKControlMcpSetServersRequest = SdkControlPayloadOf<"mcp_set_servers">;
export type SDKControlMcpStatusRequest = SdkControlPayloadOf<"mcp_status">;
export type SDKControlMcpToggleRequest = SdkControlPayloadOf<"mcp_toggle">;
export type SDKControlMessage = SdkControlMessage;
export type SDKControlPermissionRequest = SdkControlPermissionRequest;
export type SDKControlReloadPluginsRequest = SdkControlPayloadOf<"reload_plugins">;
export type SDKControlRequest = SdkControlRequestMessage;
export type SDKControlRequestCancelledError = SdkControlRequestCancelledError;
export type SDKControlRequestError = SdkControlRequestError;
export type SDKControlResponse = SdkControlResponseMessage;
export type SDKControlRewindFilesRequest = SdkControlPayloadOf<"rewind_files">;
export type SDKControlSeedReadStateRequest = SdkControlPayloadOf<"seed_read_state">;
export type SDKControlSetMaxThinkingTokensRequest = SdkControlPayloadOf<"set_max_thinking_tokens">;
export type SDKControlSetModelRequest = SdkControlPayloadOf<"set_model">;
export type SDKControlSetPermissionModeRequest = SdkControlPayloadOf<"set_permission_mode">;
export type SDKControlStopTaskRequest = SdkControlPayloadOf<"stop_task">;
export type SDKControlStreamClosedError = SdkControlStreamClosedError;
export type SDKControlSuccessResponse = SdkControlSuccessResponse;
export type SDKElicitationCompleteMessage = SdkElicitationCompleteMessage;
export type SDKFilesPersistedMessage = SdkFilesPersistedMessage;
export type SDKForkSessionOptions = SdkForkSessionOptions;
export type SDKForkSessionResult = SdkForkSessionResult;
export type SDKGetSessionMessagesOptions = SdkGetSessionMessagesOptions;
export type SDKHookCallbackRequest = SdkHookCallbackRequest;
export type SDKHookProgressMessage = SdkHookProgressMessage;
export type SDKHookResponseMessage = SdkHookResponseMessage;
export type SDKHookStartedMessage = SdkHookStartedMessage;
export type SDKHybridJsonlTransport = SdkHybridJsonlTransport;
export type SDKHybridPostHandler = SdkHybridPostHandler;
export type SDKJsonlDecodeError = SdkJsonlDecodeError;
export type SDKJsonlTransport = SdkJsonlTransport;
export type SDKKeepAliveMessage = SdkKeepAliveMessage;
export type SDKListSessionsOptions = SdkListSessionsOptions;
export type SDKLocalCommandOutputMessage = SdkLocalCommandOutputMessage;
export type SDKMessage = SdkMessage;
export type SDKModelRecoveryMessage = SdkModelRecoveryMessage;
export type SDKOptions = SdkQueryOptions;
export type SDKPostTurnSummaryMessage = SdkPostTurnSummaryMessage;
export type SDKPromptSuggestionMessage = SdkPromptSuggestionMessage;
export type SDKQueueJsonlTransport = SdkQueueJsonlTransport;
export type SDKRateLimitEventMessage = SdkRateLimitEventMessage;
export type SDKResultMessage = SdkResultMessage;
export type SDKRetryableBatchError = SdkRetryableBatchError;
export type SDKSSECloseHandler = SdkSseCloseHandler;
export type SDKSSEFrame = SdkSseFrame;
export type SDKSSEJsonlTransport = SdkSseJsonlTransport;
export type SDKSSELivenessTimeoutError = SdkSseLivenessTimeoutError;
export type SDKSSEPostHandler = SdkSsePostHandler;
export type SDKSSEReadChunksFactory = SdkSseReadChunksFactory;
export type SDKSerialBatchUploader = SdkSerialBatchUploader;
export type SDKSession = SdkSession;
export type SDKSessionInfo = SdkSessionInfo;
export type SDKSessionStateChangedMessage = SdkSessionStateChangedMessage;
export type SDKStatusMessage = SdkStatusMessage;
export type SDKStdinDecodeError = SdkStdinDecodeError;
export type SDKStdinMessage = SdkStdinMessage;
export type SDKStdoutMessage = SdkStdoutMessage;
export type SDKStreamEventMessage = SdkStreamEventMessage;
export type SDKStructuredIO = SdkStructuredIo;
export type SDKSystemMessage = SdkSystemMessage;
export type SDKTaskNotificationMessage = SdkTaskNotificationMessage;
export type SDKTaskProgressMessage = SdkTaskProgressMessage;
export type SDKTaskStartedMessage = SdkTaskStartedMessage;
export type SDKToolProgressMessage = SdkToolProgressMessage;
export type SDKToolUseSummaryMessage = SdkToolUseSummaryMessage;
export type SDKUpdateEnvironmentVariablesMessage = SdkUpdateEnvironmentVariablesMessage;
export type SDKUserMessage = SdkUserMessage;
export type SDKWebSocketCloseHandler = SdkWebSocketCloseHandler;
export type SDKWebSocketConnectOptions = SdkWebSocketConnectOptions;
export type SDKWebSocketConnector = SdkWebSocketConnector;
export type SDKWebSocketJsonlTransport = SdkWebSocketJsonlTransport;
