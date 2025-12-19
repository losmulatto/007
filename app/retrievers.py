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
# ruff: noqa
# mypy: disable-error-code="no-untyped-def"

import os

from unittest.mock import MagicMock
from langchain_google_community.vertex_rank import VertexAIRank
from langchain_google_vertexai import VertexAIEmbeddings
from langchain_google_community import VertexAISearchRetriever


def get_retriever(
    project_id: str,
    data_store_id: str,
    data_store_region: str,
    embedding: VertexAIEmbeddings,
    embedding_column: str = "embedding",
    max_documents: int = 10,
    custom_embedding_ratio: float = 0.5,
) -> VertexAISearchRetriever:
    """
    Creates and returns an instance of the retriever service.

    Uses mock service if the INTEGRATION_TEST environment variable is set to "TRUE",
    otherwise initializes real Vertex AI retriever.
    """
    try:
        from google.cloud import discoveryengine_v1 as discoveryengine
        from langchain_core.retrievers import BaseRetriever
        from langchain_core.callbacks import CallbackManagerForRetrieverRun
        from langchain_core.documents import Document
        from typing import List
        
        class CustomVertexAISearchRetriever(BaseRetriever):
            project_id: str
            location_id: str
            data_store_id: str
            max_documents: int = 10
            
            def _get_relevant_documents(
                self, query: str, *, run_manager: CallbackManagerForRetrieverRun
            ) -> List[Document]:
                client = discoveryengine.SearchServiceClient()
                
                # Construct the serving config path with 'engines' instead of 'dataStores'
                serving_config = f"projects/{self.project_id}/locations/{self.location_id}/collections/default_collection/engines/{self.data_store_id}/servingConfigs/default_search"
                
                print(f"DEBUG: CustomRetriever using serving_config: {serving_config}")
                
                request = discoveryengine.SearchRequest(
                    serving_config=serving_config,
                    query=query,
                    page_size=self.max_documents,
                    content_search_spec={
                        "extractive_content_spec": {
                            "max_extractive_answer_count": 1
                        },
                        "snippet_spec": {
                            "return_snippet": True
                        }
                    },
                    query_expansion_spec={"condition": "AUTO"},
                    spell_correction_spec={"mode": "AUTO"},
                )
                
                response = client.search(request)
                
                documents = []
                for result in response.results:
                    content = ""
                    metadata = {"id": result.document.id, "name": result.document.name}
                    
                    # Extract from derived_struct_data (unstructured documents)
                    if hasattr(result.document, "derived_struct_data") and result.document.derived_struct_data:
                        dsd = dict(result.document.derived_struct_data)
                        
                        # Get snippets
                        if "snippets" in dsd:
                            snippets = [s.get("snippet", "") for s in dsd.get("snippets", [])]
                            content = " ".join(snippets)
                        
                        # Get extractive answers if available
                        if "extractive_answers" in dsd:
                            answers = [a.get("content", "") for a in dsd.get("extractive_answers", [])]
                            if answers:
                                content = f"Answer: {' '.join(answers)}\n\nContext: {content}"
                        
                        # Get link if available
                        if "link" in dsd:
                            metadata["link"] = dsd["link"]
                    
                    if content:
                        documents.append(Document(page_content=content, metadata=metadata))
                
                print(f"DEBUG: CustomRetriever found {len(documents)} documents")
                return documents

        return CustomVertexAISearchRetriever(
            project_id=project_id,
            location_id=data_store_region,
            data_store_id=data_store_id,
            max_documents=max_documents
        )
    except Exception as e:
        print(f"DEBUG: Retriever initialization ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        retriever = MagicMock()

        def raise_exception(*args, **kwargs) -> None:
            """Function that raises an exception when the retriever is not available."""
            raise Exception(f"Retriever not available: {e}")

        retriever.invoke = raise_exception
        return retriever


def get_compressor(project_id: str, top_n: int = 5) -> VertexAIRank:
    """
    Creates and returns an instance of the compressor service.
    """
    try:
        return VertexAIRank(
            project_id=project_id,
            location_id="global",
            ranking_config="default_ranking_config",
            title_field="id",
            top_n=top_n,
        )
    except Exception:
        compressor = MagicMock()
        compressor.compress_documents = lambda x: []
        return compressor
