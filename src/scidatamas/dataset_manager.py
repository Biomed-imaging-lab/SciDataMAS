from time import sleep
from typing import Any, List

from langchain_core.prompts import ChatPromptTemplate
from langchain.chat_models import init_chat_model
from langchain.tools import StructuredTool
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from typing_extensions import TypedDict

from utils import invoke


class OrchestratorState(TypedDict):
    messages: List[Any]
    result: str


class DatalakeManagerAgent:
    def __init__(
        self,
        system_prompt: str,
        workflows_tools: List[StructuredTool],
        model: str = "mistral-large-latest",
        provider: str = "mistralai",
        temperature: float = 0.30,
    ):
        # init tools agents
        self.__tools = workflows_tools
        self._tool_node = ToolNode(self.__tools)

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
        ).bind_tools(self.__tools)

        self.__basic_chain = orchestration_template | orch_llm

        # build workflow
        self.__build_workflow()

        return

    def get_workflow(self):
        return self._workflow

    def __build_workflow(self):
        workflow = StateGraph(OrchestratorState)

        # Define the two nodes we will cycle between
        workflow.add_node("agent", self.__call_model)
        workflow.add_node("tools", self.__tools_calling)
        workflow.add_node("finalize", self.__finalize)

        workflow.add_edge(START, "agent")
        workflow.add_conditional_edges(
            "agent", self.__should_continue, ["tools", "finalize"]
        )
        workflow.add_edge("tools", "finalize")
        workflow.add_edge("finalize", END)

        self._workflow = workflow
        return

    def __tools_calling(self, state: OrchestratorState) -> OrchestratorState:
        new_state = self._tool_node.invoke(state)
        state["messages"] += new_state["messages"]
        return state

    def __call_model(self, state: OrchestratorState):
        response = invoke(self.__basic_chain, {"messages": state["messages"]})
        state["messages"] += [response]
        return state

    def __should_continue(self, state: OrchestratorState):
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools"
        return "finalize"

    def __finalize(self, state: OrchestratorState):
        messages = state["messages"]
        llm_response = invoke(
            self.__basic_chain,
            {"messages": messages},
        )
        state["result"] = llm_response.content
        return state
