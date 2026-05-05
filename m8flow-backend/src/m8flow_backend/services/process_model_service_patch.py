from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any

from flask import g, has_request_context

from m8flow_backend.tenancy import reset_context_tenant_id, set_context_tenant_id
from m8flow_backend.tenancy import is_super_admin_request

_PATCHED = False


def _tenant_roots(base_dir: str) -> list[str]:
    if not os.path.isdir(base_dir):
        return []
    roots: list[str] = []
    with os.scandir(base_dir) as entries:
        for entry in entries:
            if not entry.is_dir():
                continue
            name = entry.name.strip()
            if not name or name.startswith('.'):
                continue
            roots.append(name)
    roots.sort()
    return roots


@contextmanager
def _temporary_tenant_context(tenant_id: str):
    prev_request_tenant = getattr(g, "m8flow_tenant_id", None) if has_request_context() else None
    token = set_context_tenant_id(tenant_id)
    try:
        if has_request_context():
            g.m8flow_tenant_id = tenant_id
        yield
    finally:
        reset_context_tenant_id(token)
        if has_request_context():
            if prev_request_tenant is None:
                if hasattr(g, "m8flow_tenant_id"):
                    delattr(g, "m8flow_tenant_id")
            else:
                g.m8flow_tenant_id = prev_request_tenant


def apply() -> None:
    global _PATCHED
    if _PATCHED:
        return

    from flask import current_app
    from spiffworkflow_backend.services.process_model_service import ProcessModelService

    original_get_process_groups_for_api = ProcessModelService.get_process_groups_for_api.__func__
    original_get_process_models_for_api = ProcessModelService.get_process_models_for_api.__func__

    @classmethod
    def patched_get_process_groups_for_api(
        cls,
        process_group_id: str | None = None,
        user: Any | None = None,
    ):
        if not is_super_admin_request():
            return original_get_process_groups_for_api(cls, process_group_id=process_group_id, user=user)

        base_dir = current_app.config["SPIFFWORKFLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR"]
        tenant_ids = _tenant_roots(base_dir)
        merged: list[Any] = []
        seen: set[str] = set()

        for tenant_id in tenant_ids:
            with _temporary_tenant_context(tenant_id):
                groups = original_get_process_groups_for_api(cls, process_group_id=process_group_id, user=user)
                for group in groups:
                    group_id = getattr(group, "id", None)
                    if isinstance(group_id, str) and group_id in seen:
                        continue
                    if isinstance(group_id, str):
                        seen.add(group_id)
                    merged.append(group)

        return merged

    @classmethod
    def patched_get_process_models_for_api(
        cls,
        user: Any,
        process_group_id: str | None = None,
        recursive: bool | None = False,
        filter_runnable_by_user: bool | None = False,
        filter_runnable_as_extension: bool | None = False,
        include_files: bool | None = False,
    ):
        if not is_super_admin_request():
            return original_get_process_models_for_api(
                cls,
                user=user,
                process_group_id=process_group_id,
                recursive=recursive,
                filter_runnable_by_user=filter_runnable_by_user,
                filter_runnable_as_extension=filter_runnable_as_extension,
                include_files=include_files,
            )

        base_dir = current_app.config["SPIFFWORKFLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR"]
        tenant_ids = _tenant_roots(base_dir)
        merged: list[Any] = []
        seen: set[str] = set()

        for tenant_id in tenant_ids:
            with _temporary_tenant_context(tenant_id):
                process_models = original_get_process_models_for_api(
                    cls,
                    user=user,
                    process_group_id=process_group_id,
                    recursive=recursive,
                    filter_runnable_by_user=filter_runnable_by_user,
                    filter_runnable_as_extension=filter_runnable_as_extension,
                    include_files=include_files,
                )
                for process_model in process_models:
                    process_model_id = getattr(process_model, "id", None)
                    if isinstance(process_model_id, str) and process_model_id in seen:
                        continue
                    if isinstance(process_model_id, str):
                        seen.add(process_model_id)
                    merged.append(process_model)

        return merged

    ProcessModelService.get_process_groups_for_api = patched_get_process_groups_for_api
    ProcessModelService.get_process_models_for_api = patched_get_process_models_for_api

    _PATCHED = True
