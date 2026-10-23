export type SdkFileHistoryBackupRef = {
  exists: boolean;
  backupFileName: string;
  backupPath: string;
  version: number;
  backupTime?: unknown;
};

export type SdkFileHistorySnapshot = {
  messageId: string;
  backups: Map<string, SdkFileHistoryBackupRef>;
  backupRoot: string;
  historySessionId: string;
};
