import asyncio
import functools
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Union


@dataclass
class EvalTarget:
    name: str
    fn: Callable
    datasets: List[str]
    criteria: List[Dict[str, str]] = field(default_factory=list)
    scorers: List[str] = field(default_factory=list)
    threshold: float = 0.7
    project_id: Optional[str] = None
    judge_model: Optional[str] = None
    is_async: bool = False


_registry: Dict[str, EvalTarget] = {}


def evaluator(
    *,
    dataset: Union[str, List[str]],
    name: Optional[str] = None,
    criteria: Optional[List[Dict[str, str]]] = None,
    scorers: Optional[List[str]] = None,
    threshold: float = 0.7,
    project_id: Optional[str] = None,
    judge_model: Optional[str] = None,
):
    datasets = [dataset] if isinstance(dataset, str) else list(dataset)

    def decorator(fn: Callable):
        target_name = name or fn.__name__
        _registry[target_name] = EvalTarget(
            name=target_name,
            fn=fn,
            datasets=datasets,
            criteria=criteria or [],
            scorers=scorers or [],
            threshold=threshold,
            project_id=project_id,
            judge_model=judge_model,
            is_async=asyncio.iscoroutinefunction(fn),
        )

        if asyncio.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any):
                return await fn(*args, **kwargs)
            return async_wrapper

        @functools.wraps(fn)
        def sync_wrapper(*args: Any, **kwargs: Any):
            return fn(*args, **kwargs)
        return sync_wrapper

    return decorator


def get_target(name: str) -> Optional[EvalTarget]:
    return _registry.get(name)


def list_targets() -> List[str]:
    return list(_registry.keys())


def clear_registry() -> None:
    _registry.clear()
