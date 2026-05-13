# !/usr/bin/env python
# -*- coding: utf-8 -*-

from pathlib import Path


FRONTEND_SRC = Path("apps/web/src")


def test_frontend_is_split_into_focused_modules():
    expected_modules = {
        "App.tsx",
        "components/ActionTimeline.tsx",
        "components/ChatThread.tsx",
        "components/RunInspector.tsx",
        "components/SettingsDrawer.tsx",
        "components/OperationStage.tsx",
        "components/OperationStageScenes.tsx",
        "runtime/agentSession.ts",
        "runtime/config.ts",
        "runtime/operationFrames.ts",
        "runtime/operationProjector.ts",
        "runtime/operationPlayback.ts",
        "runtime/operationStageScript.ts",
        "runtime/operationTrace.ts",
        "types.ts",
    }

    for module in expected_modules:
        assert (FRONTEND_SRC / module).is_file(), module


def test_frontend_source_files_stay_small():
    oversized = []
    for path in FRONTEND_SRC.rglob("*"):
        if path.suffix not in {".ts", ".tsx", ".css"}:
            continue
        line_count = len(path.read_text(encoding="utf-8").splitlines())
        if line_count > 260:
            oversized.append(f"{path}: {line_count}")

    assert oversized == []


def test_action_timeline_language_is_product_visible():
    timeline = (FRONTEND_SRC / "components/ActionTimeline.tsx").read_text(encoding="utf-8")

    assert "Agent activity" in timeline
    assert "Tool call" in timeline
    assert "Code execution" in timeline
    assert "Web search" in timeline


def test_run_inspector_exposes_trace_and_artifacts():
    inspector = (FRONTEND_SRC / "components/RunInspector.tsx").read_text(encoding="utf-8")

    assert "/api/v1/agent/runs/" in inspector
    assert "Artifacts" in inspector
    assert "Timeline" in inspector


def test_tool_approval_panel_exposes_scoped_decisions():
    panel = (FRONTEND_SRC / "components/ToolApprovalPanel.tsx").read_text(encoding="utf-8")

    assert "allow_once" in panel
    assert "allow_for_run" in panel
    assert "Allow once" in panel
    assert "Allow for run" in panel


def test_operation_stage_uses_normalized_operation_events():
    types = (FRONTEND_SRC / "types.ts").read_text(encoding="utf-8")
    app = (FRONTEND_SRC / "App.tsx").read_text(encoding="utf-8")
    session = (FRONTEND_SRC / "runtime/agentSession.ts").read_text(encoding="utf-8")
    projector = (FRONTEND_SRC / "runtime/operationProjector.ts").read_text(encoding="utf-8")
    frames = (FRONTEND_SRC / "runtime/operationFrames.ts").read_text(encoding="utf-8")
    playback = (FRONTEND_SRC / "runtime/operationPlayback.ts").read_text(encoding="utf-8")
    script = (FRONTEND_SRC / "runtime/operationStageScript.ts").read_text(encoding="utf-8")
    trace = (FRONTEND_SRC / "runtime/operationTrace.ts").read_text(encoding="utf-8")
    stage = (FRONTEND_SRC / "components/OperationStage.tsx").read_text(encoding="utf-8")
    scenes = (FRONTEND_SRC / "components/OperationStageScenes.tsx").read_text(encoding="utf-8")

    assert "type OperationEvent" in types
    assert "OperationSource" in types
    assert "OperationFile" in types
    assert "projectRuntimeEvent" in projector
    assert "projectRunTrace" in projector
    assert "operation_frames" in types
    assert "sandbox_trace" in frames
    assert "operationFromFrame" in projector
    assert "sceneForTool" in projector
    assert "playbackFrames" in playback
    assert "scriptForOperation" in script
    assert "StageStep" in script
    assert "loadOperationTrace" in trace
    assert "OperationStage" in app
    assert "operations={session.operations}" in app
    assert "slice(-80)" in session
    assert "slice(-6)" in stage
    assert "DesktopBackdrop" in scenes
    assert "ProcessStrip" in scenes
