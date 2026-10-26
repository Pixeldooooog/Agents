/** Invalid local configuration, rejected before a provider request is sent. */
export class ModelConfigError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ModelConfigError";
  }
}

/** A provider response cannot safely become a runtime turn. */
export class ModelProtocolError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ModelProtocolError";
  }
}

export class ModelHttpError extends Error {
  constructor(readonly status: number, message: string) {
    super(message);
    this.name = "ModelHttpError";
  }
}
