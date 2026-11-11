from typing import Dict, List, TypedDict, Optional, Tuple

from langchain.chat_models import init_chat_model
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, START, StateGraph
from pydantic import Field, BaseModel
from typing_extensions import TypedDict

import os
from langchain_openai import ChatOpenAI


from .dag_graph import DAGEdge, DAGNode, DAG, Validator, convert_to_DAG
from .grammar import NODE_TYPES, VALID_EDGES


# Class for dag generation
class DAGGeneration(BaseModel):
    reasoning: str = Field(
        description="Step-by-step reasoning: what phases the experiment has, what modalities it produces, why the nodes are ordered this way.",
        default="",
    )
    md_name: str = Field(
        description="The name of overall data-workflow's DAG.", default=""
    )
    md_descr: str = Field(
        description="The description of data-workflow's DAG in few sentences: for what purposes, with what real objects it's works, which processes underlies here, what data its accumulates and analyse.",
        default="",
    )
    nodes: List[DAGNode] = Field(description="All nodes in the DAG", default=[])
    edges: List[DAGEdge] = Field(
        description="All directed edges in the DAG", default=[]
    )


# Generation state
class DAGGenerationState(TypedDict):
    """State of metadata generation"""

    users_task: str

    dag_conversation: List[Tuple[str, str]]
    cur_dag_errors: List[str]
    all_dag_errors: Dict[int, List[str]]
    rework_attempts: int

    raw_dag: DAGGeneration
    dag: DAG

    generation_failed: bool


class DAGGenerationFlow:
    def __init__(
        self,
        dag_generation_sp: str,
        model: str,
        provider: str,
        temperature: float,
        dag_gen_max_reworks: int = 3,
    ):
        if provider != "yandex":
            llm = init_chat_model(
                model, model_provider=provider, temperature=temperature
            )
        else:
            llm = ChatOpenAI(
                model=f"gpt://{os.environ['YC_FOLDER_ID']}/{model}",
                api_key=os.environ["YC_API_KEY"],
                base_url="https://ai.api.cloud.yandex.net/v1",
                default_headers={"x-folder-id": os.environ["YC_FOLDER_ID"]},
            )
        # defining dag gen params
        self.dag_gen_tries = dag_gen_max_reworks
        dag_gen_chat = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    dag_generation_sp,
                ),
                ("placeholder", "{messages}"),
            ],
            "f-string",
        )
        # defining chains for code generation and reflecting and reporting
        self.dag_gen_chain = dag_gen_chat | llm.with_structured_output(
            DAGGeneration, method="json_schema", strict=False
        )

        # building workflow
        self.workflow = self.__build_workflow()

        return

    def __build_workflow(self):
        # init state graph
        workflow = StateGraph(DAGGenerationState)

        # define the nodes
        workflow.add_node("starting", self._starting)
        workflow.add_node("generate_dag", self._generate_dag)
        workflow.add_node("validate", self._validate)
        workflow.add_node("rework", self._rework)
        workflow.add_node("fail_end", self._fail_end)

        # Build graph
        workflow.add_edge(START, "starting")
        workflow.add_edge("starting", "generate_dag")
        workflow.add_edge("generate_dag", "validate")
        workflow.add_conditional_edges(
            "validate",
            self._route_after_validate,
            {
                "complete": END,
                "rework": "rework",
                "fail_end": "fail_end",
            },
        )
        workflow.add_edge("rework", "validate")
        workflow.add_edge("fail_end", END)

        return workflow.compile()

    def _starting(self, state: DAGGenerationState) -> DAGGenerationState:
        # clearing all variables for generating code for new task
        state["dag_conversation"] = []
        state["cur_dag_errors"] = []
        state["all_dag_errors"] = {}
        state["rework_attempts"] = 0
        state["generation_failed"] = False

        state["raw_dag"] = None
        state["dag"] = None
        return state

    def _generate_dag(self, state: DAGGenerationState) -> DAGGenerationState:
        new_msg = [("user", state["users_task"])]
        state["dag_conversation"] += new_msg

        # generate dag solution
        try:
            llm_output = self.dag_gen_chain.invoke(
                {"messages": state["dag_conversation"]}
            )
            state["raw_dag"] = llm_output

        except Exception as exc:
            if "400" in str(exc) or "429" in str(exc):
                new_issue = [f"[Network error] {str(exc)}. Just remake generation."]
            else:
                new_issue = [f"[Parse output Error] {str(exc)}."]
            state["cur_dag_errors"] = new_issue
            state["all_dag_errors"][state["rework_attempts"]] = new_issue
            state["raw_dag"] = None

        return state

    def _validate(self, state: DAGGenerationState) -> DAGGenerationState:
        # if we failed during output parsing
        if state["raw_dag"] == None:
            return state

        validator = Validator()
        issues = validator(state["raw_dag"].nodes, state["raw_dag"].edges)
        state["all_dag_errors"][state["rework_attempts"]] = issues
        state["cur_dag_errors"] = issues
        if len(issues) == 0:
            state["dag"] = convert_to_DAG(
                state["raw_dag"].nodes, state["raw_dag"].edges
            )

        return state

    def _rework(self, state: DAGGenerationState) -> DAGGenerationState:
        # update counter
        state["rework_attempts"] += 1

        # update messages
        new_messages = []
        if state["raw_dag"] != None:
            new_messages += [("assistant", state["raw_dag"].model_dump_json())]
        issues_str = "\n".join([f" - {er}" for er in state["cur_dag_errors"]])
        new_messages += [
            (
                "user",
                "There are errors in your DAG generation! Fix them:\n" + issues_str,
            )
        ]
        state["dag_conversation"] += new_messages

        # generate dag solution
        try:
            llm_output = self.dag_gen_chain.invoke(
                {"messages": state["dag_conversation"]}
            )
            state["raw_dag"] = llm_output

        except Exception as exc:
            if "400" in str(exc) or "429" in str(exc):
                new_issue = [f"[Network error] {str(exc)}. Just remake generation."]
            else:
                new_issue = [f"[Parse output Error] {str(exc)}."]
            state["cur_dag_errors"] = new_issue
            state["all_dag_errors"][state["rework_attempts"]] = new_issue
            state["raw_dag"] = None

        return state

    def _route_after_validate(self, state: DAGGenerationState) -> DAGGenerationState:
        if state["raw_dag"] == None:
            if state["rework_attempts"] >= self.dag_gen_tries:
                return "fail_end"
            else:
                return "rework"

        elif len(state["cur_dag_errors"]) != 0:
            if state["rework_attempts"] >= self.dag_gen_tries:
                return "fail_end"
            else:
                return "rework"

        else:
            return "complete"

    def _fail_end(self, state: DAGGenerationState) -> DAGGenerationState:
        state["generation_failed"] = True
        return state
