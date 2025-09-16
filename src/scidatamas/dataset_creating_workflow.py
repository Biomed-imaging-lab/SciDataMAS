from time import sleep
from typing import Any, Dict, List, Optional, TypedDict, Tuple

from langchain.chat_models import init_chat_model
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from pydantic import BaseModel, Field
from typing_extensions import TypedDict


class MetadataStructure(BaseModel):
    """Generated metadata structure"""

    short_name: str = Field(
        description="Short name of metadata without any spaces. Must describes specific and be shoty, like 'lighsheet_microscopy_3d'",
        default="",
    )

    description: str = Field(
        description="A descripion of dataset (metadata), for which was built schema.",
        default="",
    )

    schema: Dict[str, Dict[str, str]] = Field(
        description='Dictionary of metadata scheme, describing all with next strucutre {"field_name": {"descr": "A clear, interpretive description.  Include units, examples, or acceptable values where crucial for understanding.", "type": "data_type"}}',
        default={},
    )


class MetadataGenerationAnswer(BaseModel):
    """Tools' methods names list"""

    reflection_block: str = Field(
        description="LLM reflections what kind of metadata would be useful"
    )
    metadata_structure: MetadataStructure = Field(
        description="Final generation of metadata structure"
    )


class MDGenerationState(TypedDict):
    """State of metadata generation"""

    users_task: str = Field(description="New input query task", default="")

    messages: List[Any] = Field(
        description="inner messages loop for performing fine-grained generation"
    )

    generation_user_feedback: str = Field(
        description="User's feedback on generated metadata schema", default=""
    )

    generation: MetadataStructure = Field(
        description="coder's code generation result", default=MetadataStructure()
    )


class IsNeedToReflex(BaseModel):
    """Regenerating LLM classifier output"""

    need_regenerate: bool = Field(
        description="Is need to reflex and fix something boolean flag. True - if need to some reflexion and changing, False - if don't."
    )


class MDGenerationFlow:
    def __init__(
        self,
        system_prompt: str,
        model: str = "mistral-large-latest",
        provider: str = "mistralai",
        temperature: float = 0.30,
        is_auto: bool = True,
        additional_examples: Optional[List[Tuple[str, str]]] = None,
        relevant_docs_with_instructions: Optional[List[str]] = None,
    ):
        # making more informative system prompt
        system_prompt = self.__riching_sp(
            system_prompt, additional_examples, relevant_docs_with_instructions
        )

        # defining chat template and model
        _md_gen_chat = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    system_prompt,
                ),
                ("placeholder", "{messages}"),
            ]
        )

        _llm = init_chat_model(model, model_provider=provider, temperature=temperature)

        # regenerating llm chooser
        _is_need_to_replan_template = PromptTemplate.from_template(
            """Here is user's feedback based on your answer and generation:
{user_feedback}. 
Based on that, please classify: does user want some changes or does he like generation result? \
Answer 'True', if user wants changings and reflexions. Answer 'False' - if metadata regenerating is no needful."""
        )
        self._decide_regenerate = (
            _is_need_to_replan_template | _llm.with_structured_output(IsNeedToReflex)
        )

        # defining chains for code generation and reflecting and reporting
        self._llm_chain = _md_gen_chat | _llm
        self._chain_with_parsing = _md_gen_chat | _llm.with_structured_output(
            MetadataStructure
        )

        # defining auto mode
        self._is_auto = is_auto

        # building workflow
        self._workflow = self._build_workflow()

        return

    def __riching_sp(
        self,
        system_prompt: str,
        additional_examples: Optional[List[Tuple[str, str]]] = None,
        relevant_docs_with_instructions: Optional[List[str]] = None,
    ):
        if additional_examples != None:
            system_prompt += """
# ADDITIONAL EXAMPLES

For you, there are some examples of user's tasks about creating rich metadata for some experiments and generated usefut metadatas:"""
            for i, exmpl in enumerate(additional_examples):
                system_prompt += f"\n{i}) User's task:\n"
                system_prompt += f'"{exmpl[0]}"\n'

                system_prompt += f"Useful generated meta:\n"
                system_prompt += f"```\n{exmpl[1]}\n```\n"

        if relevant_docs_with_instructions != None:
            system_prompt += """
# RELEVANT DOCS WITH INSTRUCTIONS

Also there are important docs for your current generation. They contains different instructions about experiments, which should be possible useful. Here are they"""
            system_prompt += (
                "\n```\n" + "\n".join(relevant_docs_with_instructions) + "\n```\n"
            )

        return system_prompt

    def _build_workflow(self):
        # init state graph
        workflow = StateGraph(MDGenerationState)

        # define the nodes
        workflow.add_node(
            "starting", self._starting
        )  # init short-term state for metadata generation

        workflow.add_node(
            "generate", self._generate
        )  # generate make generation & reflextions

        workflow.add_node(
            "human_validation", self._human_validation
        )  # reflect on user feedback

        workflow.add_node(
            "create_dataset", self._create_dataset
        )  # create new dataset with new metadata schema

        # Build graph
        workflow.add_edge(START, "starting")
        workflow.add_edge("starting", "generate")
        workflow.add_edge("generate", "human_validation")
        workflow.add_conditional_edges(
            "human_validation",
            self._decide_to_regenerate,
            {"create_dataset": "create_dataset", "generate": "generate"},
        )
        return workflow

    def get_workflow(self):
        return self._workflow

    def _starting(self, state: MDGenerationState) -> MDGenerationState:
        # clearing all variables for generating code for new task
        state["messages"] = []
        state["generation_user_feedback"] = ""
        state["generation"] = None
        return state

    def _generate(self, state: MDGenerationState) -> MDGenerationState:
        # generate user's input for new code generation
        messages = state["messages"]

        # if not first generation try
        if state["generation_user_feedback"] != "":
            messages += [
                (
                    "user",
                    state["generation_user_feedback"]
                    + "\nSo please regenerate the metadata schema according to the given feedback.",
                )
            ]
            state["generation_user_feedback"] = ""
        # if first generation try
        else:
            messages += [("user", state["users_task"])]

        # generate code solution
        llm_output = self._llm_chain.invoke({"messages": messages}).content
        messages += [("assistant", llm_output)]

        # update state
        state_update = state
        state_update["messages"] = messages

        return state_update

    def _human_validation(self, state: MDGenerationState) -> MDGenerationState:
        # just continue execution
        if self._is_auto == True:
            return state

        feedback = interrupt("Please provide feedback:")
        state["generation_user_feedback"] = feedback
        return state

    def _decide_to_regenerate(self, state: MDGenerationState) -> str:
        sleep(1)
        if self._is_auto == True:
            return "create_dataset"

        llm_response = self._decide_regenerate.invoke(
            {"user_feedback": state["generation_user_feedback"]}
        )

        if llm_response.need_regenerate:
            return "generate"
        else:
            return "create_dataset"

    def _create_dataset(self, state: MDGenerationState) -> MDGenerationState:
        messages = state["messages"]

        messages += [
            (
                "user",
                "Good, now, can you structure the answer in the following format:"
                "\n - short name of metadata schema (without spaces, with underlines '_');"
                "\n - description of schema (for which experiment and so on);"
                '\n - metadata schema like a dict with specific format {"field_name": {"descr": "Description of field (with values)", "type": "data_type"}}?',
            )
        ]

        full_generated_schema = self._chain_with_parsing.invoke({"messages": messages})
        state["generation"] = full_generated_schema
        return state
