import { describe, expect, test } from "bun:test";
import {
  AgentSDKClient,
  AgentSdkClient,
  SDKControlRequestCancelledError,
  SDKControlRequestError,
  SDKControlStreamClosedError,
  SDKHybridJsonlTransport,
  SDKJsonlDecodeError,
  SDKQueueJsonlTransport,
  SDKRetryableBatchError,
  SDKSSEJsonlTransport,
  SDKSSELivenessTimeoutError,
  SDKSerialBatchUploader,
  SDKSession,
  SDKStdinDecodeError,
  SDKStructuredIO,
  SDKWebSocketJsonlTransport,
  SdkControlRequestCancelledError,
  SdkControlRequestError,
  SdkControlStreamClosedError,
  SdkHybridJsonlTransport,
  SdkJsonlDecodeError,
  SdkQueueJsonlTransport,
  SdkRetryableBatchError,
  SdkSerialBatchUploader,
  SdkSession,
  SdkSseJsonlTransport,
  SdkSseLivenessTimeoutError,
  SdkStdinDecodeError,
  SdkStructuredIo,
  SdkWebSocketJsonlTransport,
  type SDKAPIRetryMessage,
  type SDKAssistantMessage,
  type SDKAuthStatusMessage,
  type SDKBatchDropHandler,
  type SDKBatchSendHandler,
  type SDKCCRAuthFailureError,
  type SDKCCRClient,
  type SDKCCREpochMismatchError,
  type SDKCCRInitError,
  type SDKCCRRequestResult,
  type SDKCCRShutdownError,
  type SDKCompactBoundaryMessage,
  type SDKControlApplyFlagSettingsRequest,
  type SDKControlCancelAsyncMessageRequest,
  type SDKControlCancelRequest,
  type SDKControlElicitationRequest,
  type SDKControlErrorResponse,
  type SDKControlGetContextUsageRequest,
  type SDKControlGetSettingsRequest,
  type SDKControlInitializeRequest,
  type SDKControlInterruptRequest,
  type SDKControlMcpMessageRequest,
  type SDKControlMcpReconnectRequest,
  type SDKControlMcpSetServersRequest,
  type SDKControlMcpStatusRequest,
  type SDKControlMcpToggleRequest,
  type SDKControlPermissionRequest,
  type SDKControlReloadPluginsRequest,
  type SDKControlRequest,
  type SDKControlResponse,
  type SDKControlRewindFilesRequest,
  type SDKControlSeedReadStateRequest,
  type SDKControlSetMaxThinkingTokensRequest,
  type SDKControlSetModelRequest,
  type SDKControlSetPermissionModeRequest,
  type SDKControlStopTaskRequest,
  type SDKControlSuccessResponse,
  type SDKElicitationCompleteMessage,
  type SDKFilesPersistedMessage,
  type SDKForkSessionOptions,
  type SDKForkSessionResult,
  type SDKGetSessionMessagesOptions,
  type SDKHookCallbackRequest,
  type SDKHookProgressMessage,
  type SDKHookResponseMessage,
  type SDKHookStartedMessage,
  type SDKHybridPostHandler,
  type SDKJsonlTransport,
  type SDKKeepAliveMessage,
  type SDKListSessionsOptions,
  type SDKLocalCommandOutputMessage,
  type SDKMessage,
  type SDKModelRecoveryMessage,
  type SDKOptions,
  type SDKPostTurnSummaryMessage,
  type SDKPromptSuggestionMessage,
  type SDKRateLimitEventMessage,
  type SDKResultMessage,
  type SDKSSECloseHandler,
  type SDKSSEFrame,
  type SDKSSEPostHandler,
  type SDKSSEReadChunksFactory,
  type SDKSessionInfo,
  type SDKSessionStateChangedMessage,
  type SDKStatusMessage,
  type SDKStdinMessage,
  type SDKStdoutMessage,
  type SDKStreamEventMessage,
  type SDKSystemMessage,
  type SDKTaskNotificationMessage,
  type SDKTaskProgressMessage,
  type SDKTaskStartedMessage,
  type SDKToolProgressMessage,
  type SDKToolUseSummaryMessage,
  type SDKUpdateEnvironmentVariablesMessage,
  type SDKUserMessage,
  type SDKWebSocketCloseHandler,
  type SDKWebSocketConnectOptions,
  type SDKWebSocketConnector,
  type SDKWorkerStateUploader
} from "@agents/core/sdk";

type PublicSdkFacadeTypeMap = {
  apiRetry: SDKAPIRetryMessage;
  assistant: SDKAssistantMessage;
  auth: SDKAuthStatusMessage;
  batchDrop: SDKBatchDropHandler;
  batchSend: SDKBatchSendHandler;
  ccrAuthFailureError: SDKCCRAuthFailureError;
  ccrClient: SDKCCRClient;
  ccrEpochMismatchError: SDKCCREpochMismatchError;
  ccrInitError: SDKCCRInitError;
  ccrRequestResult: SDKCCRRequestResult;
  ccrShutdownError: SDKCCRShutdownError;
  compact: SDKCompactBoundaryMessage;
  controlApplyFlagSettings: SDKControlApplyFlagSettingsRequest;
  controlCancelAsyncMessage: SDKControlCancelAsyncMessageRequest;
  controlCancel: SDKControlCancelRequest;
  controlElicitation: SDKControlElicitationRequest;
  controlError: SDKControlErrorResponse;
  controlGetContextUsage: SDKControlGetContextUsageRequest;
  controlGetSettings: SDKControlGetSettingsRequest;
  controlInitialize: SDKControlInitializeRequest;
  controlInterrupt: SDKControlInterruptRequest;
  controlMcpMessage: SDKControlMcpMessageRequest;
  controlMcpReconnect: SDKControlMcpReconnectRequest;
  controlMcpSetServers: SDKControlMcpSetServersRequest;
  controlMcpStatus: SDKControlMcpStatusRequest;
  controlMcpToggle: SDKControlMcpToggleRequest;
  controlPermission: SDKControlPermissionRequest;
  controlReloadPlugins: SDKControlReloadPluginsRequest;
  controlRequest: SDKControlRequest;
  controlResponse: SDKControlResponse;
  controlRewindFiles: SDKControlRewindFilesRequest;
  controlSeedReadState: SDKControlSeedReadStateRequest;
  controlSetMaxThinkingTokens: SDKControlSetMaxThinkingTokensRequest;
  controlSetModel: SDKControlSetModelRequest;
  controlSetPermissionMode: SDKControlSetPermissionModeRequest;
  controlStopTask: SDKControlStopTaskRequest;
  controlSuccess: SDKControlSuccessResponse;
  elicitationComplete: SDKElicitationCompleteMessage;
  filesPersisted: SDKFilesPersistedMessage;
  forkOptions: SDKForkSessionOptions;
  forkResult: SDKForkSessionResult;
  getSessionMessagesOptions: SDKGetSessionMessagesOptions;
  hookCallback: SDKHookCallbackRequest;
  hookProgress: SDKHookProgressMessage;
  hookResponse: SDKHookResponseMessage;
  hookStarted: SDKHookStartedMessage;
  hybridPost: SDKHybridPostHandler;
  jsonlTransport: SDKJsonlTransport;
  keepAlive: SDKKeepAliveMessage;
  listSessionsOptions: SDKListSessionsOptions;
  localCommandOutput: SDKLocalCommandOutputMessage;
  message: SDKMessage;
  modelRecovery: SDKModelRecoveryMessage;
  options: SDKOptions;
  postTurnSummary: SDKPostTurnSummaryMessage;
  promptSuggestion: SDKPromptSuggestionMessage;
  rateLimit: SDKRateLimitEventMessage;
  result: SDKResultMessage;
  sseClose: SDKSSECloseHandler;
  sseFrame: SDKSSEFrame;
  ssePost: SDKSSEPostHandler;
  sseReadChunks: SDKSSEReadChunksFactory;
  sessionInfo: SDKSessionInfo;
  sessionStateChanged: SDKSessionStateChangedMessage;
  status: SDKStatusMessage;
  stdin: SDKStdinMessage;
  stdout: SDKStdoutMessage;
  streamEvent: SDKStreamEventMessage;
  system: SDKSystemMessage;
  taskNotification: SDKTaskNotificationMessage;
  taskProgress: SDKTaskProgressMessage;
  taskStarted: SDKTaskStartedMessage;
  toolProgress: SDKToolProgressMessage;
  toolUseSummary: SDKToolUseSummaryMessage;
  updateEnvironmentVariables: SDKUpdateEnvironmentVariablesMessage;
  user: SDKUserMessage;
  websocketClose: SDKWebSocketCloseHandler;
  websocketConnectOptions: SDKWebSocketConnectOptions;
  websocketConnector: SDKWebSocketConnector;
  workerStateUploader: SDKWorkerStateUploader;
};

describe("SDK public aliases", () => {
  test("exposes Python-style SDK facade runtime names", () => {
    expect(AgentSDKClient).toBe(AgentSdkClient);
    expect(SDKControlRequestCancelledError).toBe(SdkControlRequestCancelledError);
    expect(SDKControlRequestError).toBe(SdkControlRequestError);
    expect(SDKControlStreamClosedError).toBe(SdkControlStreamClosedError);
    expect(SDKHybridJsonlTransport).toBe(SdkHybridJsonlTransport);
    expect(SDKJsonlDecodeError).toBe(SdkJsonlDecodeError);
    expect(SDKQueueJsonlTransport).toBe(SdkQueueJsonlTransport);
    expect(SDKRetryableBatchError).toBe(SdkRetryableBatchError);
    expect(SDKSerialBatchUploader).toBe(SdkSerialBatchUploader);
    expect(SDKSession).toBe(SdkSession);
    expect(SDKSSEJsonlTransport).toBe(SdkSseJsonlTransport);
    expect(SDKSSELivenessTimeoutError).toBe(SdkSseLivenessTimeoutError);
    expect(SDKStdinDecodeError).toBe(SdkStdinDecodeError);
    expect(SDKStructuredIO).toBe(SdkStructuredIo);
    expect(SDKWebSocketJsonlTransport).toBe(SdkWebSocketJsonlTransport);
    expect(new SDKSSELivenessTimeoutError()).toBeInstanceOf(SDKSSELivenessTimeoutError);
  });

  test("keeps Python-style SDK facade type names importable", () => {
    const publicTypeKeys = [] as Array<keyof PublicSdkFacadeTypeMap>;
    expect(publicTypeKeys).toEqual([]);
  });
});
