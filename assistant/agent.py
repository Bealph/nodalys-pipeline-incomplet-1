"""Assistant Nodalys — agent LangChain branché sur le LLM Kimi-K2.6 (Azure AI).

L'agent dispose des outils :
- ``query_db``        : exécute une requête SQL prédéfinie
- ``query_feedbacks`` : récupère des feedbacks de stagiaires
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_azure_ai.chat_models import AzureAIChatCompletionsModel

from assistant.tools import query_db, query_feedbacks

load_dotenv()


SYSTEM_PROMPT = """Tu es l'assistant interne de Nodalys, SaaS B2B de gestion
d'organismes de formation. Tu réponds à partir des outils mis à ta disposition
pour interroger la base. Réponds en français, de manière sourcée
(cite la requête ou la table utilisée).
"""


def _build_llm():
    return AzureAIChatCompletionsModel(
        endpoint=os.environ["AZURE_AI_INFERENCE_ENDPOINT"],
        credential=os.environ["AZURE_AI_INFERENCE_API_KEY"],
        model=os.environ.get("AZURE_AI_INFERENCE_MODEL", "Kimi-K2.6"),
    )


def build_agent():
    llm = _build_llm()
    tools = [query_db, query_feedbacks]
    return create_agent(llm, tools=tools, system_prompt=SYSTEM_PROMPT)


def ask(question: str) -> str:
    agent = build_agent()
    result = agent.invoke({"messages": [{"role": "user", "content": question}]})
    return result["messages"][-1].content


if __name__ == "__main__":
    print(ask("Quelles sont les 5 sessions Q3 avec le plus de stagiaires ?"))
