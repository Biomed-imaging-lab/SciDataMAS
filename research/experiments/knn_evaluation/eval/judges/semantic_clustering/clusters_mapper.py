from typing import Any, List, TypedDict

from langchain.chat_models import init_chat_model
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field
from typing_extensions import TypedDict


class PairedInfo(TypedDict):
    """Information about paired clusters from two schemas"""

    a_id: str = Field(description="Cluster's name from 1st schema", default="")
    b_id: str = Field(description="Cluster's name from 2nd schema", default="")
    similarity: str = Field(
        description="Level of similarity: can be 'high' or 'moderate'",
        default="moderate",
    )
    note: str = Field(
        description="The one-sentence note about why clusters matching", default=""
    )


class UnpairedInfoA(TypedDict):
    """Information about unpaired cluster"""

    a_id: str = Field(description="Name of unpaired cluster in schema A", default="")
    reason: str = Field(
        description="One sentence on why no counterpart exists in Schema B", default=""
    )


class UnpairedInfoB(TypedDict):
    """Information about unpaired cluster"""

    b_id: str = Field(description="Name of unpaired cluster in schema B", default="")
    reason: str = Field(
        description="One sentence on why no counterpart exists in Schema A", default=""
    )


class MappingResult(BaseModel):
    """Structured result of clusters mapping"""

    pairs: List[PairedInfo] = Field(
        description="Pairs of semantic nearly clusters", default=[]
    )

    unpaired_a: List[UnpairedInfoA] = Field(
        description="List of unpaired clusters from schema A",
        default=[],
    )

    unpaired_b: List[UnpairedInfoB] = Field(
        description="List of unpaired clusters from schema B", default=[]
    )

    summary: str = Field(
        description="2-3 sentences on the overall structural overlap between the two schemas",
        default="",
    )


class MappingState(TypedDict):
    """State of cluster dscription"""

    a_clusters: List[Any] = Field(
        description="Clusters from A (1st) schema", default=[]
    )
    b_clusters: List[Any] = Field(
        description="Clusters from B (2nd) schema", default=[]
    )
    generation: MappingResult = Field(
        description="Result of mapping", default=MappingResult()
    )


class ClusterMapperWF:
    def __init__(
        self,
        system_prompt: str,
        model: str,
        provider: str,
        temperature: float = 0.30,
    ):
        # defining chat template and model
        gen_chat = ChatPromptTemplate.from_messages(
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
        self.mapper_chain = gen_chat | llm.with_structured_output(
            MappingResult, method="json_schema", strict=False
        )

        # building workflow
        self.workflow = self._build_workflow()

        return

    def _build_workflow(self):
        # init state graph
        workflow = StateGraph(MappingState)

        # define the nodes
        workflow.add_node("init_state", self._init_state)
        workflow.add_node("map_clusters", self._map_clusters)

        # Build graph
        workflow.add_edge(START, "init_state")
        workflow.add_edge("init_state", "map_clusters")
        workflow.add_edge("map_clusters", END)

        return workflow.compile()

    def get_workflow(self):
        return self._workflow

    def _init_state(self, state: MappingState) -> MappingState:
        # clearing all variables for generating code for new task
        state["generation"] = None
        return state

    def _map_clusters(self, state: MappingState) -> MappingState:
        # generate user's input for new code generation
        cluster_a = state["a_clusters"]
        cluster_b = state["b_clusters"]

        clusters_a_str = "SCHEMA_A:\n\t" + "\n\t".join(
            cl.short_name + ": " + cl.description for cl in cluster_a
        )
        clusters_b_str = "SCHEMA_B:\n\t" + "\n\t".join(
            cl.short_name + ": " + cl.description for cl in cluster_b
        )

        inp_str = clusters_a_str + "\n\n" + clusters_b_str

        messages = [("user", inp_str)]
        llm_output = self.mapper_chain.invoke({"messages": messages})
        state["generation"] = llm_output
        return state
