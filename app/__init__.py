# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# -----------------------------------------------------------------------------
# PYDANTIC JSON SCHEMA FIX (Monkeypatch for FastAPI/OpenAPI)
# -----------------------------------------------------------------------------
# FastAPI/Pydantic v2 tries to generate schemas for everything in routes.
# ADK classes like Agent and BaseLlm containing httpx.Client fail.
# We monkeypatch them here at the package entry point to ensure it's applied 
# BEFORE any models are introspected by FastAPI.
def _make_opaque_for_pydantic_schema():
    from typing import Any, Dict
    from google.adk.models.base_llm import BaseLlm
    from google.adk import agents as adk_agents

    def __get_pydantic_json_schema__(cls, _core_schema: Any, handler: Any) -> Dict[str, Any]:
        return {"type": "object", "title": cls.__name__}
    
    # Classes to fix
    classes_to_fix = [BaseLlm]
    # Dynamically find Agent/LlmAgent if they exist
    for attr in ["Agent", "LlmAgent", "BaseAgent"]:
        if hasattr(adk_agents, attr):
            classes_to_fix.append(getattr(adk_agents, attr))

    for cls in classes_to_fix:
        if not hasattr(cls, "__get_pydantic_json_schema__"):
            cls.__get_pydantic_json_schema__ = classmethod(__get_pydantic_json_schema__)

try:
    _make_opaque_for_pydantic_schema()
except Exception as e:
    print(f"Warning: Failed to apply Pydantic schema monkeypatch: {e}")

from .agent import app

__all__ = ["app"]
