import type { RegisteredTool } from "./toolContracts.js";
import { commandToolDefinitions } from "./commandTools.js";
import { collaborationToolDefinitions } from "../collaboration/collaborationTools.js";
import { configToolDefinitions } from "../config/configTools.js";
import { extensionToolDefinitions } from "../extensions/extensionTools.js";
import { filesystemToolDefinitions } from "./filesystemTools.js";
import { gitToolDefinitions } from "./gitTools.js";
import { hookToolDefinitions } from "../hooks/hookTools.js";
import { memoryToolDefinitions } from "../memory/memoryTools.js";
import { createMetaToolDefinitions } from "./metaTools.js";
import { mcpToolDefinitions } from "../mcp/mcpTools.js";
import { patchToolDefinitions } from "./patchTools.js";
import { permissionToolDefinitions } from "./permissionTools.js";
import { planningToolDefinitions } from "../planning/planningTools.js";
import { processToolDefinitions } from "./processTools.js";
import { promptToolDefinitions } from "./promptTools.js";
import { scheduleToolDefinitions } from "../schedules/scheduleTools.js";
import { searchToolDefinitions } from "./searchTools.js";
import { sessionContextToolDefinitions } from "../session/sessionContextTools.js";
import { structuredToolDefinitions } from "./structuredTools.js";
import { taskToolDefinitions } from "../tasks/taskTools.js";
import { userInteractionToolDefinitions } from "./userInteractionTools.js";
import { browserToolDefinitions } from "../web/browserTools.js";
import { webToolDefinitions } from "../web/webTools.js";
import { lspToolDefinitions } from "../workspace/lspTools.js";
import { notebookToolDefinitions } from "../workspace/notebookTools.js";
import { worktreeToolDefinitions } from "../workspace/worktreeTools.js";
import { workflowToolDefinitions } from "../workflow/workflowTools.js";

export const toolDefinitions: RegisteredTool[] = [
  ...filesystemToolDefinitions,
  ...searchToolDefinitions,
  ...patchToolDefinitions,
  ...gitToolDefinitions,
  ...processToolDefinitions,
  ...webToolDefinitions,
  ...browserToolDefinitions,
  ...notebookToolDefinitions,
  ...lspToolDefinitions,
  ...worktreeToolDefinitions,
  ...createMetaToolDefinitions(() => toolDefinitions),
  ...mcpToolDefinitions,
  ...extensionToolDefinitions,
  ...collaborationToolDefinitions,
  ...taskToolDefinitions,
  ...scheduleToolDefinitions,
  ...memoryToolDefinitions,
  ...planningToolDefinitions,
  ...sessionContextToolDefinitions,
  ...permissionToolDefinitions,
  ...hookToolDefinitions,
  ...structuredToolDefinitions,
  ...configToolDefinitions,
  ...userInteractionToolDefinitions,
  ...commandToolDefinitions,
  ...promptToolDefinitions,
  ...workflowToolDefinitions
];

