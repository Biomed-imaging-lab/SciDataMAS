import os
from typing import Dict, TypedDict

from langchain.chat_models import init_chat_model
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, START, StateGraph
from pydantic import Field
from typing_extensions import TypedDict
from langchain_openai import ChatOpenAI


class MetadataStructure(TypedDict):
    """Generated metadata structure"""

    short_name: str = Field(
        description="Short name of metadata without any spaces. Must describes specific and be shoty, like 'lighsheet_microscopy_3d'",
        default="",
    )

    description: str = Field(
        description="A descripion of dataset (metadata), for which was built schema.",
        default="",
    )

    md_schema: Dict[str, Dict[str, str]] = Field(
        description='Dictionary of metadata scheme, describing all with next strucutre {"field_name": {"descr": "A clear, interpretive description.  Include units, examples, or acceptable values where crucial for understanding.", "type": "data_type"}}',
        default={},
    )


class ModelAnswer(TypedDict):
    """Structure of parsed model answer"""

    reasoning: str = Field(
        description="Reasoning block",
        default="",
    )

    generated_metadata_structure: MetadataStructure = Field(
        description="The block of medata gnerated structure",
        default=MetadataStructure(),
    )


class MDGenerationState(TypedDict):
    """State of metadata generation"""

    users_task: str = Field(description="New input query task", default="")

    generation: MetadataStructure = Field(
        description="coder's code generation result", default={}
    )


class MDGenerationFlow:
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

        # defining chains for code generation and reflecting and reporting
        self.llm_chain = md_gen_chat | llm
        self.chain_with_parsing = md_gen_chat | llm.with_structured_output(
            ModelAnswer, method="json_schema", strict=False
        )

        # building workflow
        self.workflow = self.__build_workflow()

        return

    def __build_workflow(self):
        # init state graph
        workflow = StateGraph(MDGenerationState)

        # define the nodes
        workflow.add_node("starting", self._starting)
        workflow.add_node("generate", self._generate)

        # Build graph
        workflow.add_edge(START, "starting")
        workflow.add_edge("starting", "generate")
        workflow.add_edge("generate", END)

        return workflow.compile()

    def _starting(self, state: MDGenerationState) -> MDGenerationState:
        # clearing all variables for generating code for new task
        state["generation"] = None
        return state

    def _generate(self, state: MDGenerationState) -> MDGenerationState:
        messages = [("user", state["users_task"])]

        full_generated_schema = self.chain_with_parsing.invoke({"messages": messages})
        # update state
        state_update = state
        state_update["generation"] = full_generated_schema[
            "generated_metadata_structure"
        ]

        return state_update
