from time import sleep
from typing import Any, List, TypedDict, Union

from langchain.chat_models import init_chat_model
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, START, StateGraph
import pandas as pd
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from .utils.datalake_info_retrieval import DatasetSelectionRAG
from data_model.datalake import Datalake

from utils import invoke


class SQLQueryGeneration(BaseModel):
    """Schema for SQL query generation."""

    thinking: str = Field(
        description="Block of reasoning and thinking",
        default="",
    )
    sql_request: str = Field(description="Final sql request", default="")


class RetrievingDatalakeDataState(TypedDict):
    """Data retrieving from datalake state"""

    users_task: str = Field(description="New input user's task", default="")
    dataset_source_name: Union[str, None] = Field(
        description="RAG context with external libraries", default=None
    )
    iterations: int = Field(description="code generation iterations", default=0)
    sql_generation: Union[str, None] = Field(
        description="Last SQL generation", default=None
    )
    messages: List[Any] = Field(
        description="inner messages loop for performing sql generation"
    )

    data_retrieving_result: Union[pd.DataFrame, None] = Field(
        description="final agent result of extraction data from datalake", default=None
    )

    was_error: bool = Field(
        description="The boolean flag about retrieving ata status: True - if error, False - if no error",
        default=False,
    )
    error_log: str = Field(
        description="Exception description during data retrieval", default=""
    )


class DataRetrievingFlow:
    def __init__(
        self,
        system_prompt: str,
        datalake: Datalake,
        model: str = "mistral-large-latest",
        provider: str = "mistralai",
        temperature: float = 0.30,
        max_iterations: int = 5,
    ):
        # defining chat template and model
        _retrieving_chat = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    system_prompt,
                ),
                ("placeholder", "{messages}"),
            ]
        )

        _llm = init_chat_model(model, model_provider=provider, temperature=temperature)

        self._llm_sql_generator = _retrieving_chat | _llm.with_structured_output(
            SQLQueryGeneration
        )

        # defining generation and execution params
        self._max_iterations = max_iterations

        # working with datalake elements
        self.__dataset_selection_rag = DatasetSelectionRAG(
            datalake.get_datalake_info(), model, provider, temperature
        )

        self.__datalake_inst = datalake

        # building workflow
        self._workflow = self._build_workflow()

        return

    def _build_workflow(self):
        # init state graph
        workflow = StateGraph(RetrievingDatalakeDataState)

        # define the nodes
        workflow.add_node("init_state", self.__init_state)  # init state
        workflow.add_node("get_dataset", self.__get_dataset)  # get dataset source
        workflow.add_node("generate_sql", self.__generate_sql)  # generate sql with LLM
        workflow.add_node("extract", self.__extract)

        # Build graph
        workflow.add_edge(START, "init_state")
        workflow.add_edge("init_state", "get_dataset")

        workflow.add_conditional_edges(
            "get_dataset",
            lambda state: (
                "END" if state["dataset_source_name"] == None else "reasoning"
            ),
            {"END": END, "reasoning": "generate_sql"},
        )

        workflow.add_edge("generate_sql", "extract")
        workflow.add_conditional_edges(
            "extract",
            self.__is_need_to_regen,
            {True: "generate_sql", False: END},
        )

        return workflow

    def get_workflow(self):
        return self._workflow

    def __init_state(
        self, state: RetrievingDatalakeDataState
    ) -> RetrievingDatalakeDataState:
        # clearing all variables for generating code for new task
        state["dataset_source_name"] = None
        state["messages"] = []
        state["iterations"] = 0
        state["sql_generation"] = None
        state["data_retrieving_result"] = None
        state["was_error"] = False
        state["error_log"] = ""
        return state

    def __get_dataset(
        self, state: RetrievingDatalakeDataState
    ) -> RetrievingDatalakeDataState:
        dataset_name = self.__dataset_selection_rag.retrieve(state["users_task"])
        state["dataset_source_name"] = dataset_name

        if dataset_name != None:
            meta_schema = self.__datalake_inst.get_dataset_md(dataset_name)

            state["messages"] += [
                (
                    "user",
                    state["users_task"]
                    + "\n\n"
                    + "Here what metadata fields you must use for sql query generation:"
                    + "".join(
                        [
                            f'\n - "{k}": {item};' for k, item in meta_schema.items()
                        ]
                    ),
                )
            ]

        return state

    def __generate_sql(
        self, state: RetrievingDatalakeDataState
    ) -> RetrievingDatalakeDataState:
        # generate user's input for new code generation

        messages = state["messages"]

        if state["was_error"] == True:
            messages += [
                (
                    "user",
                    "Your last SQL request for data retrieving finished with next exception:\n\n```"
                    + state["error_log"]
                    + "```\n\nSo correct an error and regenerate it!",
                )
            ]
            state["was_error"] = False
            state["error_log"] = ""

        # generate code solution
        llm_output = invoke(self._llm_sql_generator, {"messages": messages})

        messages += [
            (
                "assistant",
                "# Thinking block\n"
                + f"{llm_output.thinking}\n\n"
                + "# Final SQL request"
                + f"{llm_output.sql_request}\n\n",
            )
        ]

        # update state
        state_update = state
        state_update["messages"] = messages
        state_update["iterations"] += 1
        state_update["sql_generation"] = llm_output.sql_request

        return state_update

    def __extract(
        self, state: RetrievingDatalakeDataState
    ) -> RetrievingDatalakeDataState:
        # generate user's input for new code generation

        dataset_name = state["dataset_source_name"]
        sql_request = state["sql_generation"]

        try:
            res_df = self.__datalake_inst.get_data_table_sql(dataset_name, sql_request)
            state["data_retrieving_result"] = res_df.to_dict()
            state["messages"] += [
                (
                    "assistant",
                    "Extracted data: \n\n" + str(state["data_retrieving_result"]),
                )
            ]

            return state
        except Exception as exp:
            state["was_error"] = True
            state["error_log"] = str(exp)
            return state

    def __is_need_to_regen(self, state: RetrievingDatalakeDataState):
        was_err = state["was_error"]
        iters = state["iterations"]
        if iters >= self._max_iterations or was_err == False:
            return False
        else:
            return True
