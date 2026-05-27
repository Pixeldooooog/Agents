from __future__ import annotations

from agents.kernel.capabilities.tools.builtin.filesystem import (
    DELETE_PATH_SCHEMA,
    LIST_DIR_SCHEMA,
    MOVE_PATH_SCHEMA,
    READ_FILE_SCHEMA,
    WRITE_FILE_SCHEMA,
    delete_path,
    format_read_file_result,
    list_dir,
    move_path,
    read_file,
    write_file,
)
from agents.kernel.capabilities.tools.builtin.lsp import LSP_QUERY_SCHEMA, format_lsp_result, lsp_query
from agents.kernel.capabilities.tools.builtin.notebook import (
    NOTEBOOK_EDIT_SCHEMA,
    format_notebook_edit_result,
    notebook_edit,
)
from agents.kernel.capabilities.tools.builtin.patch import PATCH_APPLY_SCHEMA, apply_patch
from agents.kernel.capabilities.tools.builtin.registration_helpers import register_builtin_tool as _register_builtin_tool
from agents.kernel.capabilities.tools.builtin.search import GLOB_SCHEMA, GREP_SCHEMA, format_glob_result, format_grep_result, glob, grep
from agents.kernel.capabilities.tools.builtin.worktree import (
    WORKTREE_ENTER_SCHEMA,
    WORKTREE_EXIT_SCHEMA,
    enter_worktree,
    exit_worktree,
    format_worktree_result,
)
from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.capabilities.tools.registry import ToolRegistry


def register_workspace_file_tools(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    _register_filesystem(registry, context)
    _register_notebooks(registry, context)
    _register_lsp(registry, context)
    _register_patch_and_search(registry, context)


def register_worktree_tools(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    _register_builtin_tool(
        registry,
        name="worktree.enter",
        description="Create or resume an isolated git worktree and switch the session workspace to it.",
        parameters=WORKTREE_ENTER_SCHEMA,
        handler=lambda name="", pr_number=None, prNumber=None: enter_worktree(context, name=name, pr_number=pr_number, pr_number_alias=prNumber),
        metadata={"risk": "medium", "writes_state": True},
        writes_state=True,
        concurrency_safe=False,
        activity_kind="state",
        activity_title="Enter worktree",
        activity_target_argument="name",
        result_formatter=format_worktree_result,
    )
    _register_builtin_tool(
        registry,
        name="worktree.exit",
        description="Exit the active git worktree, either preserving it or removing it after safety checks.",
        parameters=WORKTREE_EXIT_SCHEMA,
        handler=lambda action, discard_changes=False: exit_worktree(
            context,
            action=action,
            discard_changes=discard_changes,
        ),
        metadata={"risk": "medium", "writes_state": True},
        destructive=True,
        writes_state=True,
        concurrency_safe=False,
        activity_kind="state",
        activity_title="Exit worktree",
        activity_target_argument="action",
        result_formatter=format_worktree_result,
    )


def _register_filesystem(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    _register_builtin_tool(
        registry,
        name="filesystem.read",
        description="Read a text file from the current workspace, optionally by line offset and limit.",
        parameters=READ_FILE_SCHEMA,
        handler=lambda path, max_bytes=None, offset=1, limit=None, pages=None: read_file(
            context,
            path,
            max_bytes=max_bytes,
            offset=offset,
            limit=limit,
            pages=pages,
        ),
        read_only=True,
        path_parameters=("path",),
        activity_kind="workspace",
        activity_title="Read file",
        activity_target_argument="path",
        result_formatter=format_read_file_result,
    )
    _register_builtin_tool(
        registry,
        name="filesystem.list",
        description="List files and directories inside the current workspace.",
        parameters=LIST_DIR_SCHEMA,
        handler=lambda path=".": list_dir(context, path=path),
        read_only=True,
        path_parameters=("path",),
        activity_kind="workspace",
        activity_title="List directory",
        activity_target_argument="path",
    )
    _register_builtin_tool(
        registry,
        name="filesystem.write",
        description="Write a UTF-8 text file inside the current workspace when the sandbox allows writes.",
        parameters=WRITE_FILE_SCHEMA,
        handler=lambda path, content: write_file(context, path, content),
        metadata={"risk": "medium", "writes_files": True},
        writes_state=True,
        concurrency_safe=False,
        path_parameters=("path",),
        activity_kind="edit",
        activity_title="Write file",
        activity_target_argument="path",
    )
    _register_builtin_tool(
        registry,
        name="filesystem.delete",
        description="Delete a file or directory inside the current workspace.",
        parameters=DELETE_PATH_SCHEMA,
        handler=lambda path, recursive=False: delete_path(context, path, recursive=recursive),
        metadata={"risk": "medium", "writes_files": True},
        destructive=True,
        writes_state=True,
        concurrency_safe=False,
        path_parameters=("path",),
        activity_kind="edit",
        activity_title="Delete path",
        activity_target_argument="path",
    )
    _register_builtin_tool(
        registry,
        name="filesystem.move",
        description="Move or rename a file or directory inside the current workspace.",
        parameters=MOVE_PATH_SCHEMA,
        handler=lambda source_path, destination_path, overwrite=False: move_path(
            context,
            source_path=source_path,
            destination_path=destination_path,
            overwrite=overwrite,
        ),
        metadata={"risk": "medium", "writes_files": True},
        writes_state=True,
        concurrency_safe=False,
        path_parameters=("source_path", "destination_path"),
        activity_kind="edit",
        activity_title="Move path",
        activity_target_argument="source_path",
    )


def _register_notebooks(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    _register_builtin_tool(
        registry,
        name="notebook.edit",
        description="Edit a specific cell in a Jupyter notebook with read-before-write stale-file safety.",
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
        metadata={"risk": "medium", "writes_files": True, "src_origin_tool": "NotebookEdit"},
        writes_state=True,
        concurrency_safe=False,
        max_result_size_chars=100000,
        path_parameters=("notebook_path",),
        activity_kind="edit",
        activity_title="Edit notebook",
        activity_target_argument="notebook_path",
        result_formatter=format_notebook_edit_result,
    )


def _register_lsp(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    _register_builtin_tool(
        registry,
        name="lsp.query",
        description="Run a read-only language-server query for a source file in the current workspace.",
        parameters=LSP_QUERY_SCHEMA,
        handler=lambda operation, filePath, line, character: lsp_query(
            context,
            operation=operation,
            filePath=filePath,
            line=line,
            character=character,
        ),
        read_only=True,
        path_parameters=("filePath",),
        activity_kind="workspace",
        activity_title="Query language server",
        activity_target_argument="filePath",
        result_formatter=format_lsp_result,
    )


def _register_patch_and_search(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    _register_builtin_tool(
        registry,
        name="patch.apply",
        description="Apply exact text edits or create text files inside the current workspace.",
        parameters=PATCH_APPLY_SCHEMA,
        handler=lambda edits=None, creates=None, dry_run=False: apply_patch(
            context,
            edits=edits,
            creates=creates,
            dry_run=dry_run,
        ),
        metadata={"risk": "medium", "writes_files": True},
        writes_state=True,
        concurrency_safe=False,
        activity_kind="edit",
        activity_title="Apply patch",
    )
    _register_builtin_tool(
        registry,
        name="search.grep",
        description="Search text files inside the current workspace with a regular expression.",
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
        read_only=True,
        path_parameters=("path",),
        activity_kind="workspace",
        activity_title="Search files",
        activity_target_argument="path",
        result_formatter=format_grep_result,
    )
    _register_builtin_tool(
        registry,
        name="search.glob",
        description="Find workspace files by glob pattern.",
        parameters=GLOB_SCHEMA,
        handler=lambda pattern, path=".", max_results=100: glob(
            context,
            pattern,
            path=path,
            max_results=max_results,
        ),
        read_only=True,
        path_parameters=("path",),
        activity_kind="workspace",
        activity_title="Find files",
        activity_target_argument="pattern",
        result_formatter=format_glob_result,
    )
