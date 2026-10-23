export type SdkJsonSchema = Record<string, unknown>;
export type JsonSchemaProperties = Record<string, SdkJsonSchema>;

export const emptyRecordSchema = { type: "object", additionalProperties: true };
export const stringSchema = { type: "string" };
export const numberSchema = { type: "number" };
export const booleanSchema = { type: "boolean" };
export const stringArraySchema = { type: "array", items: stringSchema };
export const objectArraySchema = { type: "array", items: emptyRecordSchema };

export function strictObject(properties: JsonSchemaProperties, required: string[] = []): SdkJsonSchema {
  return {
    type: "object",
    additionalProperties: false,
    properties,
    ...(required.length ? { required } : {})
  };
}

export function oneOf(schemas: SdkJsonSchema[]): SdkJsonSchema {
  return { oneOf: schemas };
}

export function constSchema(value: string): SdkJsonSchema {
  return { const: value };
}

export function enumSchema(values: string[]): SdkJsonSchema {
  return { enum: values };
}

export function nullable(schema: SdkJsonSchema): SdkJsonSchema {
  return { anyOf: [schema, { type: "null" }] };
}

export function subtypeOnlySchema(subtype: string): SdkJsonSchema {
  return strictObject({ subtype: constSchema(subtype) }, ["subtype"]);
}

export function cloneSchema(schema: SdkJsonSchema): SdkJsonSchema {
  return JSON.parse(JSON.stringify(schema)) as SdkJsonSchema;
}
