export const ccrHeartbeatIntervalMs = 20000;
export const ccrUploadBaseDelayMs = 500;
export const ccrUploadMaxDelayMs = 30000;
export const ccrWorkerStateBaseDelayMs = 500;
export const ccrWorkerStateMaxDelayMs = 30000;
export const ccrStreamEventFlushIntervalMs = 100;
export const ccrGetMaxAttempts = 10;
export const ccrGetBaseDelayMs = 500;
export const ccrGetMaxDelayMs = 30000;
export const ccrMaxConsecutiveAuthFailures = 10;

export const CCR_HEARTBEAT_INTERVAL_SECONDS = ccrHeartbeatIntervalMs / 1000;
export const CCR_UPLOAD_BASE_DELAY_SECONDS = ccrUploadBaseDelayMs / 1000;
export const CCR_UPLOAD_MAX_DELAY_SECONDS = ccrUploadMaxDelayMs / 1000;
export const CCR_WORKER_STATE_BASE_DELAY_SECONDS = ccrWorkerStateBaseDelayMs / 1000;
export const CCR_WORKER_STATE_MAX_DELAY_SECONDS = ccrWorkerStateMaxDelayMs / 1000;
export const CCR_STREAM_EVENT_FLUSH_INTERVAL_SECONDS = ccrStreamEventFlushIntervalMs / 1000;
export const CCR_GET_MAX_ATTEMPTS = ccrGetMaxAttempts;
export const CCR_GET_BASE_DELAY_SECONDS = ccrGetBaseDelayMs / 1000;
export const CCR_GET_MAX_DELAY_SECONDS = ccrGetMaxDelayMs / 1000;
export const CCR_MAX_CONSECUTIVE_AUTH_FAILURES = ccrMaxConsecutiveAuthFailures;

export type SdkCcrDeliveryStatus = "received" | "processing" | "processed";
export type SdkCcrShutdownReason = "epoch_mismatch" | "auth_expired" | "auth_failures_exhausted";
export type SdkCcrShutdownHandler = (reason: SdkCcrShutdownReason) => void | Promise<void>;

export class SdkCcrInitError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SdkCcrInitError";
  }
}

export class SdkCcrShutdownError extends Error {
  constructor(readonly reason: SdkCcrShutdownReason, message?: string) {
    super(message || reason);
    this.name = "SdkCcrShutdownError";
  }
}

export class SdkCcrEpochMismatchError extends SdkCcrShutdownError {
  constructor() {
    super("epoch_mismatch", "worker epoch mismatch");
    this.name = "SdkCcrEpochMismatchError";
  }
}

export class SdkCcrAuthFailureError extends SdkCcrShutdownError {
  constructor(reason: SdkCcrShutdownReason = "auth_failures_exhausted", message?: string) {
    super(reason, message);
    this.name = "SdkCcrAuthFailureError";
  }
}

export type SdkCcrRequestResultOptions = {
  status?: number;
  data?: unknown;
  retryAfterMs?: number;
  retry_after_seconds?: number;
};

export class SdkCcrRequestResult {
  readonly ok: boolean;
  readonly status?: number;
  readonly data?: unknown;
  readonly retryAfterMs?: number;
  readonly retry_after_seconds?: number;

  constructor(ok: boolean, options: SdkCcrRequestResultOptions = {}) {
    this.ok = ok;
    this.status = options.status;
    this.data = options.data;
    this.retryAfterMs = options.retryAfterMs;
    this.retry_after_seconds = options.retry_after_seconds;
  }
}

export type SdkCcrRequestHandler = (
  method: string,
  path: string,
  headers: Record<string, string>,
  body?: Record<string, unknown>
) => Promise<SdkCcrRequestResult>;

export const SDKCCRInitError = SdkCcrInitError;
export const SDKCCRShutdownError = SdkCcrShutdownError;
export const SDKCCREpochMismatchError = SdkCcrEpochMismatchError;
export const SDKCCRAuthFailureError = SdkCcrAuthFailureError;
export const SDKCCRRequestResult = SdkCcrRequestResult;

export type SDKCCRInitError = SdkCcrInitError;
export type SDKCCRShutdownError = SdkCcrShutdownError;
export type SDKCCREpochMismatchError = SdkCcrEpochMismatchError;
export type SDKCCRAuthFailureError = SdkCcrAuthFailureError;
export type SDKCCRRequestResult = SdkCcrRequestResult;
export type SDKCCRDeliveryStatus = SdkCcrDeliveryStatus;
export type SDKCCRShutdownReason = SdkCcrShutdownReason;
export type SDKCCRShutdownHandler = SdkCcrShutdownHandler;
export type SDKCCRRequestHandler = SdkCcrRequestHandler;
