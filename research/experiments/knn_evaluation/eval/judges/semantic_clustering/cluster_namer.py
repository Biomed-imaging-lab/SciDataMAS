from typing import Any, List, TypedDict

from langchain.chat_models import init_chat_model
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field
from typing_extensions import TypedDict


class ClusterStructure(BaseModel):
    """Single cluster description structure"""

    short_name: str = Field(
        description="Short few words cluster name",
        default="",
    )

    description: str = Field(
        description="Cluster description",
        default="",
    )

    breadth: str = Field(
        description='The breadth of fields\' semantics. Can be "narrow" or "broad"',
        default="",
    )
    confidence: int = Field(description="Your confidence in such evaluating", default=1)


# class MetadataGenerationAnswer(BaseModel):
#    """Tools' methods names list"""

#    reflection_block: str = Field(
#        description="LLM reflections what kind of metadata would be useful"
#    )
#    cluster_description: ClusterStructure = Field(
#        description="Final cluster description"
#    )


class ClusterDescState(TypedDict):
    """State of cluster dscription"""

    clusters_fields: List[str] = Field(description="New input task", default="")

    messages: List[Any] = Field(
        description="inner messages loop for performing fine-grained generation"
    )

    generation: ClusterStructure = Field(
        description="Cluster's description", default=ClusterStructure()
    )


class ClusterNamerWF:
    def __init__(
        self,
        system_prompt: str,
        model: str,
        provider: str,
        temperature: float = 0.30,
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
            "mustache",
        )

        llm = init_chat_model(model, model_provider=provider, temperature=temperature)

        # defining chains for code generation and reflecting and reporting
        self.namer_chain = md_gen_chat | llm.with_structured_output(
            ClusterStructure, method="json_schema", strict=False
        )

        # building workflow
        self.workflow = self._build_workflow()

        return

    def _build_workflow(self):
        # init state graph
        workflow = StateGraph(ClusterDescState)

        # define the nodes
        workflow.add_node("init_state", self._init_state)
        workflow.add_node("describe_cluster", self._describe_cluster)

        # Build graph
        workflow.add_edge(START, "init_state")
        workflow.add_edge("init_state", "describe_cluster")
        workflow.add_edge("describe_cluster", END)

        return workflow.compile()

    def _init_state(self, state: ClusterDescState) -> ClusterDescState:
        # clearing all variables for generating code for new task
        state["messages"] = []
        state["generation"] = None
        return state

    def _describe_cluster(self, state: ClusterDescState) -> ClusterDescState:
        # generate user's input for new code generation
        input_msg = "\n".join(state["clusters_fields"])
        messages = state["messages"] + [("user", input_msg)]
        llm_output = self.namer_chain.invoke({"messages": messages})
        state["generation"] = llm_output
        return state
