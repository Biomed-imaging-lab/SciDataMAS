from typing import Any, List

from langchain.chat_models import init_chat_model
from langchain_core.prompts import ChatPromptTemplate

from utils import invoke


class FinalizeChain:
    def __init__(self, model: str, provider: str, temperature: float = 0.30):
        chat_template = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are task finilizing agent. Your main task is to finalize the solution "
                    "to the problem based on the user's communication history with the agent.\n\n"
                    ""
                    "It's important to keep in mind that the user's messages are addressed not to you, but to an agent. "
                    "Therefore, simply compile a task summary.",
                ),
                ("placeholder", "{messages}"),
            ]
        )

        _llm = init_chat_model(
            model=model, model_provider=provider, temperature=temperature
        )

        self.__basic_chain = chat_template | _llm
        return

    def call(self, messages: List[Any]) -> str:
        messages += [("user", "Now, finalize results.")]
        response = invoke(self.__basic_chain, {"messages": messages})
        return response.content
