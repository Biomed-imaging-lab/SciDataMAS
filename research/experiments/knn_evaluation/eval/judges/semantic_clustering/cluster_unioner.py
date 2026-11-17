from typing import Any, List, Optional, TypedDict

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
        description="Unioned cluster description",
        default="",
    )


class MetadataGenerationAnswer(BaseModel):
   """LLMs structurized answer"""

   reflection_block: str = Field(
       description="LLM reflections block about clusters union", default =""
   )

   cluster_description: ClusterStructure = Field(
       description="Final union cluster description", default=ClusterStructure(),
   )


class ClusterDescState(TypedDict):
    """State of cluster dscription"""

    first_cluster_name: str = Field(description='The name of first cluster', default="")
    second_cluster_name: str = Field(description='The name of second cluster', default="")
    
    first_cluster_descr: str = Field(description='The description of first cluster', default="")
    second_cluster_descr: str = Field(description='The description of second cluster', default="")

    clusters_fields_1: Optional[List[str]] = Field(description="List of first cluster's fields", default="")
    clusters_fields_2: Optional[List[str]] = Field(description="List of second cluster's fields", default="")

    union_result: MetadataGenerationAnswer = Field(
        description="Cluster's description", default=MetadataGenerationAnswer()
    )


class ClusterUnionerWF:
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
            "mustache",
        )

        llm = init_chat_model(model, model_provider=provider, temperature=temperature)

        # defining chains for code generation and reflecting and reporting
        self.namer_chain = md_gen_chat | llm.with_structured_output(
            MetadataGenerationAnswer, method="json_schema", strict=False
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
        state["union_result"] = None
        return state

    def _describe_cluster(self, state: ClusterDescState) -> ClusterDescState:
        # generate user's input for new code generation
        cluster_msg  = f"First cluster name: \"{state['first_cluster_name']}\".\n"
        cluster_msg += f"First cluster description: \"{state['first_cluster_descr']}\".\n\n"
        cluster_msg += f"Second cluster name: \"{state['second_cluster_name']}\".\n"
        cluster_msg += f"Second cluster description: \"{state['second_cluster_descr']}\".\n"
        
        if state['clusters_fields_1'] != None and state['clusters_fields_2'] != None:
            input_msg_1 = "\n".join(state["clusters_fields_1"])
            input_msg_2 = "\n".join(state["clusters_fields_2"])

            cluster_msg += '\nFields in first cluster:\n' + input_msg_1
            cluster_msg += '\nFields in second cluster:\n' + input_msg_2

        messages = [("user", cluster_msg)]
        llm_output = self.namer_chain.invoke({"messages": messages})
        state["union_result"] = llm_output
        return state
