import type { SdkCcrRequestHandler, SdkCcrShutdownHandler } from "./sdkCcrTypes.js";

export type SdkCcrTransportEventSource = {
  setOnEvent?: (handler: (event: Record<string, unknown>) => void) => void;
  set_on_event?: (handler: (event: Record<string, unknown>) => void) => void;
};

export type SdkCcrClientOptions = {
  transport?: SdkCcrTransportEventSource;
  request?: SdkCcrRequestHandler;
  getAuthHeaders?: () => Record<string, string>;
  get_auth_headers?: () => Record<string, string>;
  getAuthToken?: () => string | undefined;
  get_auth_token?: () => string | undefined;
  onShutdown?: SdkCcrShutdownHandler;
  on_shutdown?: SdkCcrShutdownHandler;
  maxConsecutiveAuthFailures?: number;
  max_consecutive_auth_failures?: number;
  heartbeatIntervalMs?: number | null;
  heartbeat_interval_seconds?: number | null;
  streamEventFlushIntervalMs?: number;
  stream_event_flush_interval_seconds?: number;
  getBaseDelayMs?: number;
  get_base_delay_seconds?: number;
  getMaxDelayMs?: number;
  get_max_delay_seconds?: number;
  sleep?: (milliseconds: number) => Promise<void>;
  now?: () => number;
};
