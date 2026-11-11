from typing import Dict, List, TypedDict, Optional, Tuple

from langchain.chat_models import init_chat_model
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, START, StateGraph
from pydantic import Field, BaseModel
from typing_extensions import TypedDict

from .dag_graph import DAG


# classes for MD generation
class FieldData(BaseModel):
    field_id: str = Field(description="Unique snake_case identifier for this field")
    descr: str = Field(description="Operational description with units and examples")
    type: str = Field(description="string | int | float | date | bool | categorical")
    allowed_values: List[str] = Field(
        description="Allowed values for categorical fields, empty list if not applicable"
    )


class MDGeneration(BaseModel):
    reasoning: str = Field(description="Which metadata fields you included and why")
    md_schema: List[FieldData] = Field(description="Flat metadata fields for this node")


# Generation state
class MDGenerationState(TypedDict):
    """State of metadata generation"""

    users_task: str
    md_name: str
    md_description: str
    dag: DAG

    steps_queue: List[str]
    conversation: List[Tuple[str, str]]
    cur_dag_node: str
    cur_attempts_cnt: int
    cur_gen: MDGeneration
    cur_issues: List[str]
    existed_fields: Dict[str, str]

    md_gen_failed: bool
    fields_per_node: Dict[str, MDGeneration]

    total_issues: Dict[int, List[str]]
    total_reworks_cnt: int


class MDGenerationFlow:
    def __init__(
        self,
        fields_generation_sp: str,
        model: str,
        provider: str,
        temperature: float,
        max_gen_attempt_per_step: int = 3,
    ):
        llm = init_chat_model(model, model_provider=provider, temperature=temperature)
        self.max_gen_attempt_per_step = max_gen_attempt_per_step

        # defining chat template and model
        md_gen_chat = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    fields_generation_sp,
                ),
                ("placeholder", "{messages}"),
            ],
            "f-string",
        )

        # defining chains for code generation and reflecting and reporting
        self.md_gen_chain = md_gen_chat | llm.with_structured_output(
            MDGeneration, method="json_schema", strict=False
        )

        # building workflow
        self.workflow = self.__build_workflow()

        return

    def __build_workflow(self):
        # init state graph
        workflow = StateGraph(MDGenerationState)

        # define the nodes
        workflow.add_node("starting", self._starting)
        workflow.add_node("bfs_new_step_gen", self._bfs_new_step_gen)
        workflow.add_node("validate", self._validate)
        workflow.add_node("rework", self._rework)
        workflow.add_node("fail_end", self._fail_end)

        # Build graph
        workflow.add_edge(START, "starting")
        workflow.add_edge("starting", "bfs_new_step_gen")
        workflow.add_edge("bfs_new_step_gen", "validate")
        workflow.add_conditional_edges(
            "validate",
            self._route_after_validate,
            {
                "bfs_new_step_gen": "bfs_new_step_gen",
                "rework": "rework",
                "fail_end": "fail_end",
                "complete": END,
            },
        )
        workflow.add_edge("rework", "validate")
        workflow.add_edge("fail_end", END)

        return workflow.compile()

    def _starting(self, state: MDGenerationState) -> MDGenerationState:
        # clearing all variables for generating code for new task
        state["md_gen_failed"] = False
        state["fields_per_node"] = {}

        state["cur_issues"] = []
        state["cur_gen"] = None
        state["cur_attempts_cnt"] = 0
        state["cur_dag_node"] = None
        state["conversation"] = []
        state["steps_queue"] = list(state["dag"].nodes.keys())
        state["existed_fields"] = {}

        state["total_issues"] = []
        state["total_reworks_cnt"] = 0

        return state

    def _bfs_new_step_gen(self, state: MDGenerationState) -> MDGenerationState:
        state["cur_dag_node"] = state["steps_queue"].pop(0)
        state["cur_attempts_cnt"] = 0

        new_msg_str_pref = ""
        if len(state["fields_per_node"].keys()) == 0:
            new_msg_str_pref = "Here we begin our session for generating metadata fields for differents steps of data-workflow RAG.\n"
            new_msg_str_pref += f"Here is the query, for which DAG was generated: \"{state['users_task']}\".\n\n"
            new_msg_str_pref += f"Here is the DAG's name - \"{state['md_name']}\". And there is the description: {state['md_description']}\n\n"
            new_msg_str_pref += (
                f"And here is overall DAG:\n{state['dag'].model_dump_json()}\n\n"
            )

        cur_dag_name = state["cur_dag_node"]
        cur_dag_descr = state["dag"].nodes[cur_dag_name].description
        new_msg = f"Now, reason which metadata fields should contain the \"{state['cur_dag_node']}\" step ({cur_dag_descr})."
        new_msg = new_msg_str_pref + new_msg

        # if len(state["existed_fields"]) != 0:
        #     used_fields = "\n".join(
        #         [f" - {txt}" for txt in state["existed_fields"].values()]
        #     )
        #     new_msg += (
        #         f"\n\nRemember, you must not repeat this fields' ids:\n" + used_fields
        #     )

        new_msg_el = [("user", new_msg)]
        state["conversation"] += new_msg_el

        # generate md fields
        try:
            llm_output = self.md_gen_chain.invoke({"messages": state["conversation"]})
            state["cur_gen"] = llm_output
            state["conversation"] += [("assistant", llm_output.model_dump_json())]

        except Exception as exc:
            new_issue = [f"[Parse output Error] {str(exc)}."]
            state["cur_issues"] = new_issue
            state["cur_gen"] = None
            state["total_issues"] += new_issue

        return state

    def _validate(self, state: MDGenerationState) -> MDGenerationState:
        # if we failed during output parsing
        if state["cur_gen"] == None:
            return state

        issues = []
        cur_set = set()
        for fld in state["cur_gen"].md_schema:
            f_k = fld.field_id
            if f_k in state["existed_fields"].keys():
                issues += [
                    f"[Fields id's collision across DAG' steps] the field \"{f_k}\" already was generated for previous DAG steps"
                ]
            if f_k in cur_set:
                issues += [
                    f'[Fields id\'s collision in current DAG step] the field "{f_k}" already was generated for previous DAG steps'
                ]
            cur_set.add(f_k)

        state["cur_issues"] = issues

        if len(issues) == 0:
            cur_node_id = state["cur_dag_node"]
            state["fields_per_node"][cur_node_id] = state["cur_gen"]

            for fld in state["cur_gen"].md_schema:
                fl_name = fld.field_id
                state["existed_fields"][
                    fl_name
                ] = f'"{fl_name}" field (in "{cur_node_id}" block) - {fld.descr}'
        else:
            state["total_issues"] += issues

        return state

    def _rework(self, state: MDGenerationState) -> MDGenerationState:
        # update counter
        state["cur_attempts_cnt"] += 1
        state["total_reworks_cnt"] += 1

        # update messages
        new_messages = []
        if state["cur_gen"] != None:
            new_messages += [("assistant", state["cur_gen"].model_dump_json())]

        issues_str = "\n".join([f" - {er}" for er in state["cur_issues"]])
        new_messages += [
            (
                "user",
                "There are errors in your MetaData generation! Fix them:\n"
                + issues_str,
            )
        ]
        state["conversation"] += new_messages

        # generate md fields
        try:
            llm_output = self.md_gen_chain.invoke({"messages": state["conversation"]})
            state["cur_gen"] = llm_output

        except Exception as exc:
            new_issue = [f"[Parse output Error] {str(exc)}."]
            state["cur_issues"] = new_issue
            state["cur_gen"] = None
            state["total_issues"] += new_issue

        return state

    def _route_after_validate(self, state: MDGenerationState) -> MDGenerationState:
        if state["cur_gen"] == None:
            if state["cur_attempts_cnt"] >= self.max_gen_attempt_per_step:
                return "fail_end"
            else:
                return "rework"

        elif len(state["cur_issues"]) != 0:
            if state["cur_attempts_cnt"] >= self.max_gen_attempt_per_step:
                return "fail_end"
            else:
                return "rework"

        else:
            if len(state["steps_queue"]) == 0:
                return "complete"
            else:
                return "bfs_new_step_gen"

    def _fail_end(self, state: MDGenerationState) -> MDGenerationState:
        state["md_gen_failed"] = True
        return state
