"""Registration wiring for src-origin core coding tool aliases."""

from __future__ import annotations

from agents.kernel.capabilities.sandbox.text import DEFAULT_TEXT_READ_MAX_BYTES
from agents.kernel.capabilities.tools.builtin.filesystem import format_read_file_result, read_file, write_file
from agents.kernel.capabilities.tools.builtin.lsp import LSP_QUERY_SCHEMA, format_lsp_result, lsp_query
from agents.kernel.capabilities.tools.builtin.notebook import (
    NOTEBOOK_EDIT_SCHEMA,
    format_notebook_edit_result,
    notebook_edit,
)
from agents.kernel.capabilities.tools.builtin.patch import (
    apply_src_origin_edit,
    apply_src_origin_multi_edit,
    format_src_origin_edit_result,
    format_src_origin_multi_edit_result,
)
from agents.kernel.capabilities.tools.builtin.planning import (
    TODO_WRITE_SCHEMA,
    format_todo_write_result,
    todo_write,
)
from agents.kernel.capabilities.tools.builtin.registration_helpers import register_builtin_tool as _register_builtin_tool
from agents.kernel.capabilities.tools.builtin.search import (
    GLOB_SCHEMA,
    GREP_SCHEMA,
    format_glob_result,
    format_grep_result,
    glob,
    grep,
)
from agents.kernel.capabilities.tools.builtin.shell import RUN_COMMAND_SCHEMA, run_command
from agents.kernel.capabilities.tools.builtin.sleep import SLEEP_WAIT_SCHEMA, sleep_wait
from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.capabilities.tools.registry import ToolRegistry


SRC_ORIGIN_READ_SCHEMA = {
    "type": "object",
    "properties": {
        "file_path": {"type": "string", "description": "Path to the file to read."},
        "offset": {"type": "integer", "minimum": 0},
        "limit": {"type": "integer", "minimum": 1},
        "pages": {"type": "string", "description": "Page range for PDF files."},
        "max_bytes": {"type": "integer", "minimum": 1, "maximum": DEFAULT_TEXT_READ_MAX_BYTES},
    },
    "required": ["file_path"],
}

SRC_ORIGIN_WRITE_SCHEMA = {
    "type": "object",
    "properties": {
        "file_path": {"type": "string", "description": "Path to the file to write."},
        "content": {"type": "string", "description": "The content to write to the file."},
    },
    "required": ["file_path", "content"],
}

SRC_ORIGIN_EDIT_SCHEMA = {
    "type": "object",
    "properties": {
        "file_path": {"type": "string", "description": "Path to the file to edit."},
        "old_string": {"type": "string", "description": "Text to replace."},
        "new_string": {"type": "string", "description": "Replacement text."},
        "replace_all": {"type": "boolean", "description": "Replace all occurrences."},
    },
    "required": ["file_path", "old_string", "new_string"],
}

SRC_ORIGIN_MULTI_EDIT_SCHEMA = {
    "type": "object",
    "properties": {
        "file_path": {"type": "string", "description": "Path to the file to edit."},
        "edits": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "old_string": {"type": "string", "description": "Text to replace."},
                    "new_string": {"type": "string", "description": "Replacement text."},
                    "replace_all": {"type": "boolean", "description": "Replace all occurrences."},
                },
                "required": ["old_string", "new_string"],
            },
        },
    },
    "required": ["file_path", "edits"],
}


def register_src_origin_core_aliases(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    _register_builtin_tool(
        registry,
        name="Read",
        description="Read a file from the current workspace. src-origin alias for filesystem.read.",
        parameters=SRC_ORIGIN_READ_SCHEMA,
        handler=lambda file_path, offset=1, limit=None, pages=None, max_bytes=None: read_file(
            context,
            file_path,
            max_bytes=max_bytes,
            offset=offset,
            limit=limit,
            pages=pages,
        ),
        metadata={"alias_of": "filesystem.read", "src_origin_tool": "Read"},
        read_only=True,
        path_parameters=("file_path",),
        activity_kind="workspace",
        activity_title="Read file",
        activity_target_argument="file_path",
        result_formatter=format_read_file_result,
    )
    _register_builtin_tool(
        registry,
        name="Write",
        description="Create or overwrite a file in the current workspace. src-origin alias for filesystem.write.",
        parameters=SRC_ORIGIN_WRITE_SCHEMA,
        handler=lambda file_path, content: write_file(context, file_path, content),
        metadata={"risk": "medium", "writes_files": True, "alias_of": "filesystem.write", "src_origin_tool": "Write"},
        writes_state=True,
        concurrency_safe=False,
        max_result_size_chars=100000,
        path_parameters=("file_path",),
        activity_kind="edit",
        activity_title="Write file",
        activity_target_argument="file_path",
    )
    _register_builtin_tool(
        registry,
        name="Edit",
        description="Replace text in a file. src-origin alias for patch.apply single-file edit.",
        parameters=SRC_ORIGIN_EDIT_SCHEMA,
        handler=lambda file_path, old_string, new_string, replace_all=False: apply_src_origin_edit(
            context,
            file_path=file_path,
            old_string=old_string,
            new_string=new_string,
            replace_all=replace_all,
        ),
        metadata={"risk": "medium", "writes_files": True, "alias_of": "patch.apply", "src_origin_tool": "Edit"},
        writes_state=True,
        concurrency_safe=False,
        max_result_size_chars=100000,
        path_parameters=("file_path",),
        activity_kind="edit",
        activity_title="Edit file",
        activity_target_argument="file_path",
        result_formatter=format_src_origin_edit_result,
    )
    _register_builtin_tool(
        registry,
        name="MultiEdit",
        description="Apply multiple text replacements to one file. src-origin alias for patch.apply.",
        parameters=SRC_ORIGIN_MULTI_EDIT_SCHEMA,
        handler=lambda file_path, edits: apply_src_origin_multi_edit(context, file_path=file_path, edits=edits),
        metadata={"risk": "medium", "writes_files": True, "alias_of": "patch.apply", "src_origin_tool": "MultiEdit"},
        writes_state=True,
        concurrency_safe=False,
        max_result_size_chars=100000,
        path_parameters=("file_path",),
        activity_kind="edit",
        activity_title="Edit file",
        activity_target_argument="file_path",
        result_formatter=format_src_origin_multi_edit_result,
    )
    _register_builtin_tool(
        registry,
        name="LSP",
        description="Run a src-origin style language-server query for a workspace source file.",
        parameters=LSP_QUERY_SCHEMA,
        handler=lambda operation, filePath, line, character: lsp_query(
            context,
            operation=operation,
            filePath=filePath,
            line=line,
            character=character,
        ),
        metadata={"alias_of": "lsp.query", "src_origin_tool": "LSP"},
        read_only=True,
        path_parameters=("filePath",),
        activity_kind="workspace",
        activity_title="Query language server",
        activity_target_argument="filePath",
        result_formatter=format_lsp_result,
    )
    _register_builtin_tool(
        registry,
        name="Bash",
        description="Run a shell command. src-origin alias for shell.run.",
        parameters=RUN_COMMAND_SCHEMA,
        handler=lambda command,
        timeout_seconds=20.0,
        timeout=None,
        description="",
        run_in_background=False,
        dangerouslyDisableSandbox=False: run_command(
            context,
            command=command,
            timeout_seconds=timeout_seconds,
            timeout=timeout,
            description=description,
            run_in_background=run_in_background,
            dangerouslyDisableSandbox=dangerouslyDisableSandbox,
        ),
        metadata={"risk": "high", "requires_process": True, "alias_of": "shell.run", "src_origin_tool": "Bash"},
        concurrency_safe=False,
        interrupt_behavior="cancel",
        cancels_siblings_on_error=True,
        activity_kind="terminal",
        activity_title="Run shell command",
        activity_target_argument="command",
    )
    _register_builtin_tool(
        registry,
        name="Glob",
        description="Find workspace files by glob pattern. src-origin alias for search.glob.",
        parameters=GLOB_SCHEMA,
        handler=lambda pattern, path=".", max_results=100: glob(context, pattern, path=path, max_results=max_results),
        metadata={"alias_of": "search.glob", "src_origin_tool": "Glob"},
        read_only=True,
        path_parameters=("path",),
        activity_kind="workspace",
        activity_title="Find files",
        activity_target_argument="pattern",
        result_formatter=format_glob_result,
    )
    _register_builtin_tool(
        registry,
        name="Grep",
        description="Search workspace files by regex. src-origin alias for search.grep.",
        parameters=GREP_SCHEMA,
        handler=lambda pattern, path=".", glob="", max_results=1000, case_sensitive=True, output_mode="files_with_matches", head_limit=None, offset=0, **options: grep(
            context,
            pattern,
            path=path,
            glob=glob,
            max_results=max_results,
            case_sensitive=case_sensitive,
            output_mode=output_mode,
            head_limit=head_limit,
            offset=offset,
            **options,
        ),
        metadata={"alias_of": "search.grep", "src_origin_tool": "Grep"},
        read_only=True,
        path_parameters=("path",),
        activity_kind="workspace",
        activity_title="Search files",
        activity_target_argument="path",
        result_formatter=format_grep_result,
    )
    _register_builtin_tool(
        registry,
        name="TodoWrite",
        description="Update the structured todo list for the current session. src-origin alias for todo.write.",
        parameters=TODO_WRITE_SCHEMA,
        handler=lambda todos: todo_write(context, todos=todos),
        metadata={"risk": "low", "writes_state": True, "defer": True, "alias_of": "todo.write", "src_origin_tool": "TodoWrite"},
        writes_state=True,
        concurrency_safe=False,
        max_result_size_chars=100000,
        activity_kind="state",
        activity_title="Update todos",
        result_formatter=format_todo_write_result,
    )
    _register_builtin_tool(
        registry,
        name="NotebookEdit",
        description="Edit a specific Jupyter notebook cell. src-origin alias for notebook.edit.",
        parameters=NOTEBOOK_EDIT_SCHEMA,
        handler=lambda notebook_path,
        new_source,
        cell_id=None,
        cell_type=None,
        edit_mode="replace": notebook_edit(
            context,
            notebook_path=notebook_path,
            new_source=new_source,
            cell_id=cell_id,
            cell_type=cell_type,
            edit_mode=edit_mode,
        ),
        metadata={"risk": "medium", "writes_files": True, "alias_of": "notebook.edit", "src_origin_tool": "NotebookEdit"},
        writes_state=True,
        concurrency_safe=False,
        max_result_size_chars=100000,
        path_parameters=("notebook_path",),
        activity_kind="edit",
        activity_title="Edit notebook",
        activity_target_argument="notebook_path",
        result_formatter=format_notebook_edit_result,
    )
    _register_builtin_tool(
        registry,
        name="Sleep",
        description="Wait for a specified duration. src-origin alias for sleep.wait.",
        parameters=SLEEP_WAIT_SCHEMA,
        handler=lambda duration_seconds, reason="": sleep_wait(context, duration_seconds=duration_seconds, reason=reason),
        metadata={"risk": "low", "alias_of": "sleep.wait", "src_origin_tool": "Sleep"},
        read_only=True,
        interrupt_behavior="cancel",
        activity_kind="wait",
        activity_title="Wait",
        activity_target_argument="duration_seconds",
    )
