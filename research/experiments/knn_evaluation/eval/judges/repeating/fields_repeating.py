from typing import Any, List, Optional, TypedDict

from langchain.chat_models import init_chat_model
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field
from typing_extensions import TypedDict


class LLMJudgeResult(BaseModel):
    """LLMs structurized answer"""

    reasoning: str = Field(
        description="The reasoning block",
        default=''
    )

    same_fields_from_list: List[str] = Field(
        description="List of fields names, equivalent to target field",
        default=[],
    )


class CompareState(TypedDict):
    """State of cluster dscription"""

    md_schema_name: str = Field(description="The name of generated schema", default="")

    md_schema_descr: str = Field(
        description="The description of generated schema", default=""
    )

    main_field_str: str = Field(
        description="The field info with which we must compair others", default=""
    )

    potention_similar_fields: List[str] = Field(
        description="The description of generated schema", default=[]
    )

    result: LLMJudgeResult = Field(
        description="Cluster's description", default=LLMJudgeResult()
    )


class FieldsComparator:
    def __init__(
        self,
        system_prompt: str,
        model: str,
        provider: str,
        temperature: float,
    ):
        # defining chat template and model
        md_gen_chat = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    system_prompt,
                ),
                ("placeholder", "{messages}"),
            ],
            "f-string",
        )

        llm = init_chat_model(model, model_provider=provider, temperature=temperature)

        # defining chains for code generation and reflecting and reporting
        self.compare_chain = md_gen_chat | llm.with_structured_output(
            LLMJudgeResult, method="json_schema", strict=False
        )

        # building workflow
        self.workflow = self._build_workflow()
        return

    def _build_workflow(self):
        # init state graph
        workflow = StateGraph(CompareState)

        # define the nodes
        workflow.add_node("init_state", self._init_state)
        workflow.add_node("compare_fields", self._compare_fields)

        # Build graph
        workflow.add_edge(START, "init_state")
        workflow.add_edge("init_state", "compare_fields")
        workflow.add_edge("compare_fields", END)

        return workflow.compile()

    def _init_state(self, state: CompareState) -> CompareState:
        # clearing all variables for generating code for new task
        state["result"] = None
        return state

    def _compare_fields(self, state: CompareState) -> CompareState:
        msg = f'Here is your task on fields comparing from the next metadata table: "{state["md_schema_name"]}" - {state["md_schema_descr"]}.\n\n'
        msg += (
            "The field, with which you should compare other fields:\n"
            + f" - {state['main_field_str']}"
        )
        msg += "\n\n"
        msg += "Other fields with possible same semantic:\n"
        msg += "\n".join([f" - {s};" for s in state["potention_similar_fields"]])

        messages = [("user", msg)]
        llm_output = self.compare_chain.invoke({"messages": messages})
        state["result"] = llm_output
        return state
