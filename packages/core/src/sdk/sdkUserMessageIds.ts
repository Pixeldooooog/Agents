export function newSdkUserMessageUuid(): string {
  return `msg_${crypto.randomUUID().replaceAll("-", "")}`;
}
