from agents.kernel.context.builder import ContextBuilder
from agents.kernel.context.compaction import ConversationCompaction, ContextCompactor, HeuristicContextCompactor
from agents.kernel.context.compaction_model import ModelContextCompactor
from agents.kernel.context.memory import MemoryContextRetriever, MemoryRetrievalScope
from agents.kernel.context.pack import (
    CompiledContext,
    ContextFragment,
    ContextLayer,
    ContextPack,
    ContextScope,
    ContextTraceItem,
)
from agents.kernel.context.sources import build_context_pack
from agents.kernel.context.workspace import WorkspaceContext

__all__ = [
    "CompiledContext",
    "ContextCompactor",
    "ContextBuilder",
    "ContextFragment",
    "ContextLayer",
    "ContextPack",
    "ContextScope",
    "ContextTraceItem",
    "ConversationCompaction",
    "HeuristicContextCompactor",
    "MemoryContextRetriever",
    "MemoryRetrievalScope",
    "ModelContextCompactor",
    "ModelRequestCompiler",
    "WorkspaceContext",
    "build_context_pack",
]


def __getattr__(name):
    if name == "ModelRequestCompiler":
        from agents.kernel.context.compiler import ModelRequestCompiler

        return ModelRequestCompiler
    raise AttributeError(name)
