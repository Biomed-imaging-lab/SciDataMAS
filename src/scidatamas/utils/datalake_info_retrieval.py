from time import sleep

from langchain.chat_models import init_chat_model
from langchain_core.prompts import PromptTemplate
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field
from typing import TypedDict
from typing_extensions import List, Tuple

from data_management.local_datalake_management import DatasetInfo
from utils import invoke


class FinalDatasetChoosing(BaseModel):
    """Choosing the dataset for working with"""

    reflection_block: str = Field(
        description="Block for reflection and thinking", default=""
    )

    dataset_name: str = Field(
        description="Name of dataset which is relevant for a user's task.", default=""
    )


class RagState(TypedDict):
    """State of context generation"""

    task: str
    final_dataset_name: str


class DatasetSelectionRAG:
    def __init__(
        self,
        datalake_info: List[DatasetInfo],
        model: str = "mistral-large-latest",
        provider: str = "mistralai",
        temperature: float = 0.30,
    ):
        # generate llm chains for retrival docs
        self.__llm = init_chat_model(
            model=model, model_provider=provider, temperature=temperature
        )

        self.__general_dataset_choosing = PromptTemplate.from_template(
            """I need to take choose dataset, about which is talking in this task:
{task}

Here are my available datasets: 
{datalake_info}

I need to choose one of them, which is the most relevant for the passed task! 
Can you please reflect on the task and datasets list and provide the only name of the one, the most relevant dataset?

Please, strcutre your answer with two blocks: block of thinking, and block with single dataset name.
Come only with relevant dataset! If no datasets are relevant - just return an empty string!
"""
        )

        self.__dataset_choosing_chain = (
            self.__general_dataset_choosing
            | self.__llm.with_structured_output(FinalDatasetChoosing)
        )

        # get coarse and fine tools description
        self.__datalake_info = datalake_info

        # build retrieve graph
        self.__build_workflow()
        return

    def __build_workflow(self):
        workflow = StateGraph(RagState)

        workflow.add_node("dataset_choosing", self.__get_relevant_dataset)

        workflow.add_edge(START, "dataset_choosing")
        workflow.add_edge("dataset_choosing", END)

        self._app = workflow.compile()
        return

    def __get_relevant_dataset(self, state: RagState):
        datalake_info = ""
        for i, doc in enumerate(self.__datalake_info):
            datalake_info += f"{i+1}) {doc.full_description}\n"

        response = invoke(
            self.__dataset_choosing_chain,
            {"task": state["task"], "datalake_info": datalake_info},
        )

        state["final_dataset_name"] = response.dataset_name
        return state

    def retrieve(self, query: str) -> str:
        state = RagState()
        state["task"] = query
        state = self._app.invoke(state)
        final_context = state["final_dataset_name"]
        return final_context
