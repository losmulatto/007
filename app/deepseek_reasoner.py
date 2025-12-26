"""
Custom DeepSeek Reasoner Client for ADK

This module provides a custom LLM implementation that properly handles
DeepSeek's thinking mode (deepseek-reasoner) with tool calls.

The key feature is preserving and passing back the `reasoning_content` field
in multi-turn conversations as required by DeepSeek's API.
"""

import os
import json
from typing import AsyncIterator, Optional, Any, Dict, List
from dataclasses import dataclass, field
from openai import AsyncOpenAI

from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types as genai_types
from pydantic import ConfigDict



@dataclass
class DeepSeekMessage:
    """Represents a message in DeepSeek conversation with reasoning support."""
    role: str
    content: Optional[str] = None
    reasoning_content: Optional[str] = None
    tool_calls: Optional[List[Dict]] = None
    tool_call_id: Optional[str] = None


class DeepSeekReasonerLlm(BaseLlm):
    """
    Handles the `reasoning_content` field properly for multi-turn
    tool call conversations.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    @classmethod
    def __get_pydantic_json_schema__(cls, _core_schema: Any, handler: Any) -> Dict[str, Any]:
        """Make the LLM instance opaque for JSON schema (OpenAPI) generation."""
        return {"type": "object", "title": cls.__name__}
    
    def __init__(
        self,
        model: str = "deepseek-reasoner",
        api_key: Optional[str] = None,
        api_base: str = "https://api.deepseek.com",
        max_tokens: int = 8192,
        enable_thinking: bool = True,
    ):
        super().__init__()
        self._model = model
        self._api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        self._api_base = api_base
        self._max_tokens = max_tokens
        self._enable_thinking = enable_thinking
        
        if not self._api_key:
            raise ValueError("DEEPSEEK_API_KEY is required")
        
        self._client = AsyncOpenAI(
            api_key=self._api_key,
            base_url=self._api_base,
        )
        
        # Store reasoning_content for each conversation turn
        self._reasoning_cache: Dict[str, str] = {}
    
    @property
    def model(self) -> str:
        return self._model
    
    def _convert_contents_to_messages(
        self,
        contents: List[genai_types.Content],
        session_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Convert ADK Content objects to DeepSeek message format."""
        messages = []
        
        for content in contents:
            role = content.role if content.role != "model" else "assistant"
            
            # Handle parts
            text_parts = []
            tool_calls_list = []
            tool_result = None
            tool_call_id = None
            
            for part in content.parts or []:
                if hasattr(part, "text") and part.text:
                    text_parts.append(part.text)
                elif hasattr(part, "function_call") and part.function_call:
                    fc = part.function_call
                    tool_calls_list.append({
                        "id": getattr(fc, "id", f"call_{len(tool_calls_list)}"),
                        "type": "function",
                        "function": {
                            "name": fc.name,
                            "arguments": json.dumps(fc.args) if isinstance(fc.args, dict) else str(fc.args),
                        }
                    })
                elif hasattr(part, "function_response") and part.function_response:
                    fr = part.function_response
                    tool_result = json.dumps(fr.response) if isinstance(fr.response, dict) else str(fr.response)
                    tool_call_id = getattr(fr, "id", None) or getattr(fr, "name", "unknown")
            
            # Build message
            message: Dict[str, Any] = {"role": role}
            
            if tool_result and tool_call_id:
                # This is a tool response
                message["role"] = "tool"
                message["content"] = tool_result
                message["tool_call_id"] = tool_call_id
            elif tool_calls_list:
                # Assistant message with tool calls
                message["content"] = "\n".join(text_parts) if text_parts else None
                message["tool_calls"] = tool_calls_list
                
                # Add reasoning_content if cached
                cache_key = self._get_cache_key(session_id, len(messages))
                if cache_key in self._reasoning_cache:
                    message["reasoning_content"] = self._reasoning_cache[cache_key]
            else:
                message["content"] = "\n".join(text_parts) if text_parts else ""
            
            messages.append(message)
        
        return messages
    
    def _get_cache_key(self, session_id: Optional[str], message_index: int) -> str:
        """Generate cache key for reasoning content."""
        return f"{session_id or 'default'}_{message_index}"
    
    def _convert_tools_dict_to_deepseek(
        self,
        tools_dict: Optional[Dict[str, Any]] = None,
    ) -> Optional[List[Dict[str, Any]]]:
        """Convert ADK tools_dict to DeepSeek/OpenAI format."""
        if not tools_dict:
            return None
        
        deepseek_tools = []
        for tool_name, tool in tools_dict.items():
            # Get function declaration from the tool
            if hasattr(tool, "get_declaration"):
                declaration = tool.get_declaration()
                if declaration:
                    deepseek_tools.append({
                        "type": "function",
                        "function": {
                            "name": declaration.name if hasattr(declaration, "name") else tool_name,
                            "description": declaration.description if hasattr(declaration, "description") else "",
                            "parameters": declaration.parameters if hasattr(declaration, "parameters") else {"type": "object", "properties": {}},
                        }
                    })
            elif hasattr(tool, "name"):
                # Fallback for simpler tools
                deepseek_tools.append({
                    "type": "function",
                    "function": {
                        "name": tool.name if hasattr(tool, "name") else tool_name,
                        "description": getattr(tool, "description", ""),
                        "parameters": getattr(tool, "parameters", {"type": "object", "properties": {}}),
                    }
                })
        
        return deepseek_tools if deepseek_tools else None
    
    async def generate_content_async(
        self,
        llm_request: LlmRequest,
        stream: bool = True,
    ) -> AsyncIterator[LlmResponse]:
        """Generate content using DeepSeek Reasoner with thinking mode."""
        
        # Get session ID for caching
        session_id = getattr(llm_request, "session_id", None)
        
        # Convert contents to messages
        messages = self._convert_contents_to_messages(
            llm_request.contents or [],
            session_id=session_id,
        )
        
        # Convert tools from tools_dict
        tools = self._convert_tools_dict_to_deepseek(llm_request.tools_dict)
        
        # DEBUG: Log tools being sent
        print(f"[DeepSeek Reasoner] tools_dict keys: {list(llm_request.tools_dict.keys()) if llm_request.tools_dict else 'None'}")
        print(f"[DeepSeek Reasoner] Converted tools count: {len(tools) if tools else 0}")
        if tools:
            print(f"[DeepSeek Reasoner] Tool names: {[t['function']['name'] for t in tools]}")
        
        # Build request
        request_kwargs: Dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "max_tokens": self._max_tokens,
            "stream": stream,
        }
        
        if tools:
            request_kwargs["tools"] = tools
        
        # Enable thinking mode
        if self._enable_thinking:
            request_kwargs["extra_body"] = {
                "thinking": {"type": "enabled"}
            }

        
        try:
            if stream:
                async for response in self._stream_response(request_kwargs, session_id, len(messages)):
                    yield response
            else:
                response = await self._non_stream_response(request_kwargs, session_id, len(messages))
                yield response
                
        except Exception as e:
            # Return error as response
            error_content = genai_types.Content(
                role="model",
                parts=[genai_types.Part(text=f"DeepSeek API Error: {str(e)}")],
            )
            yield LlmResponse(content=error_content, error=str(e))
    
    async def _stream_response(
        self,
        request_kwargs: Dict[str, Any],
        session_id: Optional[str],
        message_count: int,
    ) -> AsyncIterator[LlmResponse]:
        """Handle streaming response from DeepSeek."""
        
        stream = await self._client.chat.completions.create(**request_kwargs)
        
        accumulated_content = ""
        accumulated_reasoning = ""
        tool_calls_accumulated: Dict[int, Dict[str, Any]] = {}
        
        async for chunk in stream:
            if not chunk.choices:
                continue
            
            choice = chunk.choices[0]
            delta = choice.delta
            
            # Accumulate reasoning content
            if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                accumulated_reasoning += delta.reasoning_content
            
            # Accumulate content
            if delta.content:
                accumulated_content += delta.content
                
                # Yield partial content
                yield LlmResponse(
                    content=genai_types.Content(
                        role="model",
                        parts=[genai_types.Part(text=accumulated_content)],
                    ),
                    partial=True,
                )
            
            # Accumulate tool calls
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in tool_calls_accumulated:
                        tool_calls_accumulated[idx] = {
                            "id": tc.id or f"call_{idx}",
                            "name": "",
                            "arguments": "",
                        }
                    if tc.function:
                        if tc.function.name:
                            tool_calls_accumulated[idx]["name"] = tc.function.name
                        if tc.function.arguments:
                            tool_calls_accumulated[idx]["arguments"] += tc.function.arguments
        
        # Cache reasoning content for next turn
        if accumulated_reasoning:
            cache_key = self._get_cache_key(session_id, message_count)
            self._reasoning_cache[cache_key] = accumulated_reasoning
        
        # Build final response
        parts = []
        
        if accumulated_content:
            parts.append(genai_types.Part(text=accumulated_content))
        
        # Add tool calls as function_call parts
        for idx in sorted(tool_calls_accumulated.keys()):
            tc = tool_calls_accumulated[idx]
            try:
                args = json.loads(tc["arguments"]) if tc["arguments"] else {}
            except json.JSONDecodeError:
                args = {"raw": tc["arguments"]}
            
            parts.append(genai_types.Part(
                function_call=genai_types.FunctionCall(
                    id=tc["id"],
                    name=tc["name"],
                    args=args,
                )
            ))
        
        if parts:
            yield LlmResponse(
                content=genai_types.Content(role="model", parts=parts),
                partial=False,
            )
    
    async def _non_stream_response(
        self,
        request_kwargs: Dict[str, Any],
        session_id: Optional[str],
        message_count: int,
    ) -> LlmResponse:
        """Handle non-streaming response from DeepSeek."""
        
        request_kwargs["stream"] = False
        response = await self._client.chat.completions.create(**request_kwargs)
        
        if not response.choices:
            return LlmResponse(
                content=genai_types.Content(role="model", parts=[]),
                error="No response from DeepSeek",
            )
        
        choice = response.choices[0]
        message = choice.message
        
        # Cache reasoning content
        if hasattr(message, "reasoning_content") and message.reasoning_content:
            cache_key = self._get_cache_key(session_id, message_count)
            self._reasoning_cache[cache_key] = message.reasoning_content
        
        # Build parts
        parts = []
        
        if message.content:
            parts.append(genai_types.Part(text=message.content))
        
        if message.tool_calls:
            for tc in message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                except json.JSONDecodeError:
                    args = {"raw": tc.function.arguments}
                
                parts.append(genai_types.Part(
                    function_call=genai_types.FunctionCall(
                        id=tc.id,
                        name=tc.function.name,
                        args=args,
                    )
                ))
        
        return LlmResponse(
            content=genai_types.Content(role="model", parts=parts),
            partial=False,
        )
    
    def clear_reasoning_cache(self, session_id: Optional[str] = None):
        """Clear reasoning cache for a session or all sessions."""
        if session_id:
            keys_to_remove = [k for k in self._reasoning_cache if k.startswith(f"{session_id}_")]
            for k in keys_to_remove:
                del self._reasoning_cache[k]
        else:
            self._reasoning_cache.clear()


def get_deepseek_reasoner(
    api_key: Optional[str] = None,
    enable_thinking: bool = True,
) -> DeepSeekReasonerLlm:
    """Factory function to create DeepSeek Reasoner LLM instance."""
    return DeepSeekReasonerLlm(
        model="deepseek-reasoner",
        api_key=api_key,
        enable_thinking=enable_thinking,
    )
