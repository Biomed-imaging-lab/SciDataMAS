from typing import Any, List

from langchain_core.prompts import ChatPromptTemplate
from langchain.chat_models import init_chat_model
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict
from pydantic import BaseModel, Field

from utils import invoke


class OrchestratorState(TypedDict):
    messages: List[Any]
    choosen_wf: str


class OchestratorChoosingOutput(BaseModel):
    """Schema for choosing workflow"""

    thinking: str = Field(
        description="Block of reasoning and thinking",
        default="",
    )
    final_choose: str = Field(description="Final choosen workflow", default="")


class OrchestratorAgent:
    def __init__(
        self,
        system_prompt: str,
        model: str = "mistral-large-latest",
        provider: str = "mistralai",
        temperature: float = 0.30,
    ):
        # define orchestrator chains
        orchestration_template = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    system_prompt,
                ),
                ("placeholder", "{messages}"),
            ]
        )

        orch_llm = init_chat_model(
            model=model, model_provider=provider, temperature=temperature
        )

        self.__basic_chain = orchestration_template | orch_llm.with_structured_output(
            OchestratorChoosingOutput
        )

        # build workflow
        self.__build_workflow()

        return

    def get_workflow(self):
        return self._workflow

    def __build_workflow(self):
        workflow = StateGraph(OrchestratorState)

        # Define the two nodes we will cycle between
        workflow.add_node("agent", self.__call_model)

        workflow.add_edge(START, "agent")
        workflow.add_edge("agent", END)

        self._workflow = workflow
        return

    def __call_model(self, state: OrchestratorState):
        response = invoke(self.__basic_chain, {"messages": state["messages"]})
        state["messages"] += [
            response.thinking + f"\nFinal choose: '{response.final_choose}'"
        ]
        state["choosen_wf"] = response.final_choose
        return state
