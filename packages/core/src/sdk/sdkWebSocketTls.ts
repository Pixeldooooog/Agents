export type SdkWebSocketTlsEnv = Record<string, string | undefined>;

export type SdkWebSocketTlsConfig = {
  caCertFile?: string;
  clientCertFile?: string;
  clientKeyFile?: string;
  clientKeyPassword?: string;
};

export type SdkWebSocketTlsConfigOptions = {
  caCertFile?: string;
  clientCertFile?: string;
  clientKeyFile?: string;
  clientKeyPassword?: string;
  env?: SdkWebSocketTlsEnv;
};

export function resolveWebSocketTlsConfig(options: SdkWebSocketTlsConfigOptions): SdkWebSocketTlsConfig | undefined {
  const env = options.env || environmentWebSocketTlsValues();
  const tlsConfig: SdkWebSocketTlsConfig = {
    caCertFile: stringValue(options.caCertFile) || firstEnv(env, "KEVIN_SDK_CA_CERTS", "NODE_EXTRA_CA_CERTS"),
    clientCertFile: stringValue(options.clientCertFile) || firstEnv(env, "KEVIN_SDK_CLIENT_CERT", "CLAUDE_CODE_CLIENT_CERT"),
    clientKeyFile: stringValue(options.clientKeyFile) || firstEnv(env, "KEVIN_SDK_CLIENT_KEY", "CLAUDE_CODE_CLIENT_KEY"),
    clientKeyPassword: stringValue(options.clientKeyPassword) || firstEnv(
      env,
      "KEVIN_SDK_CLIENT_KEY_PASSPHRASE",
      "CLAUDE_CODE_CLIENT_KEY_PASSPHRASE"
    )
  };
  return Object.values(tlsConfig).some(Boolean) ? tlsConfig : undefined;
}

function firstEnv(env: SdkWebSocketTlsEnv, ...names: string[]): string | undefined {
  for (const name of names) {
    const value = stringValue(env[name]);
    if (value) return value;
  }
  return undefined;
}

function stringValue(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

function environmentWebSocketTlsValues(): SdkWebSocketTlsEnv {
  return {
    KEVIN_SDK_CA_CERTS: process.env.KEVIN_SDK_CA_CERTS,
    NODE_EXTRA_CA_CERTS: process.env.NODE_EXTRA_CA_CERTS,
    KEVIN_SDK_CLIENT_CERT: process.env.KEVIN_SDK_CLIENT_CERT,
    CLAUDE_CODE_CLIENT_CERT: process.env.CLAUDE_CODE_CLIENT_CERT,
    KEVIN_SDK_CLIENT_KEY: process.env.KEVIN_SDK_CLIENT_KEY,
    CLAUDE_CODE_CLIENT_KEY: process.env.CLAUDE_CODE_CLIENT_KEY,
    KEVIN_SDK_CLIENT_KEY_PASSPHRASE: process.env.KEVIN_SDK_CLIENT_KEY_PASSPHRASE,
    CLAUDE_CODE_CLIENT_KEY_PASSPHRASE: process.env.CLAUDE_CODE_CLIENT_KEY_PASSPHRASE
  };
}
