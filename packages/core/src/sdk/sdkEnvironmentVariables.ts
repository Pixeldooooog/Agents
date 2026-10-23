export function applySdkEnvironmentVariablesUpdate(
  options: { metadata?: Record<string, unknown> },
  variables: Record<string, string>
): void {
  const metadata = options.metadata || {};
  const currentVariables = metadataEnvironmentVariables(
    metadata.environment_variables ?? metadata.environmentVariables
  );
  metadata.environment_variables = {
    ...currentVariables,
    ...variables
  };
  options.metadata = metadata;
  for (const [key, value] of Object.entries(variables)) {
    process.env[key] = value;
  }
}

function metadataEnvironmentVariables(value: unknown): Record<string, string> {
  if (typeof value === "string") return metadataEnvironmentVariables(parseJsonObject(value));
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  return Object.fromEntries(
    Object.entries(value as Record<string, unknown>).map(([key, entry]) => [key, String(entry)])
  );
}

function parseJsonObject(value: string): Record<string, unknown> {
  try {
    const parsed = JSON.parse(value);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed as Record<string, unknown> : {};
  } catch {
    return {};
  }
}
