from time import sleep
from typing import Any, Callable, Dict, List, TypedDict, Union
from typing_extensions import Annotated

from langchain.chat_models import init_chat_model
from langchain_core.messages import ToolMessage
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
from langchain_core.tools import InjectedToolCallId
from langgraph.graph import END, START, StateGraph
from langchain.tools import StructuredTool
from langgraph.types import interrupt, Command
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel, Field
from typing_extensions import TypedDict
from langgraph.prebuilt import InjectedState

from .utils.datalake_info_retrieval import DatasetSelectionRAG
from .utils.adding_data_tools import BASIC_TOOLS
from data_management.local_datalake_management import LocalDataLake
from utils import invoke

###
#
# BLOCK OF STRUCTURED OUTPUTS CLASSES
#
###


class AddingData(BaseModel):
    """Choosing from user's request which data is need to add"""

    thinking: str = Field(description="Field for your thinking", default="")

    data_to_add: Union[str, List[str]] = Field(
        description="Data which is needed to add: it could be a single path to a file/folder, or a list of paths (it's based on users request)",
        default="",
    )


class IsNeedToRefine(BaseModel):
    """Regenerating LLM classifier output"""

    need_regenerate: bool = Field(
        description="Is need to more reasoning boolean flag. True - if need to some reflexion and changing, False - if don't."
    )

    need_to_add: bool = Field(
        description="Is anything right and user whants to add data with current metadata? True - if wants to add, False - if doesn't."
    )


###
#
# BLOCK OF WORKFLOW STATE
#
###


class AddDataWorkflowState(TypedDict):
    """State of adding data"""

    users_task: str = Field(description="New input query task", default="")

    choosen_dataset: Union[str, None] = Field(
        description="Name of dataset where to add new data", default=None
    )

    origin_dataset_meta_schema: Dict[str, Dict[str, str]] = Field(
        description="The destination dataset's metadata schema", default={}
    )

    currently_filled_schema: Dict[str, Any] = Field(description="Currently filled data")

    data_to_add: Union[str, List[str]] = Field(
        description="Path or list of paths to add in dataser", default=""
    )

    messages: List[Any] = Field(
        description="inner messages loop for performing fine-grained generation"
    )

    generation_user_feedback: str = Field(
        description="User's feedback on generated metadata schema", default=""
    )


class AddDataToDatasetFlow:
    def __init__(
        self,
        system_prompt: str,
        datalake: LocalDataLake,
        observation_tools: List[StructuredTool] = BASIC_TOOLS,
        model: str = "mistral-large-latest",
        provider: str = "mistralai",
        temperature: float = 0.30,
        is_auto: bool = False,
    ):
        # defining chains for code generation and reflecting and reporting
        _reasoning_and_tool_calling_chat = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    system_prompt,
                ),
                ("placeholder", "{messages}"),
            ]
        )

        ask_user = StructuredTool.from_function(
            self.ask_user, name="contacting_the_user", parse_docstring=True
        )
        fill_values = StructuredTool.from_function(
            self.fill_values, name="fill_metadata_values", parse_docstring=True
        )

        if is_auto == False:
            self.__tools = observation_tools + [ask_user, fill_values]
        else:
            self.__tools = observation_tools + [fill_values]
        self.__tools_names = [tool.name for tool in self.__tools]
        self.__tool_node = ToolNode(self.__tools)

        _reason_llm = init_chat_model(
            model, model_provider=provider, temperature=temperature
        ).bind_tools(self.__tools)

        self._reason_llm_chain = _reasoning_and_tool_calling_chat | _reason_llm

        # regenerating llm chooser
        _is_need_to_remake_template = PromptTemplate.from_template(
            """Here is user's feedback based on your metadata filling:
{user_feedback}. 

Based on that, please classify: does user want some changes or does he like generation result?"""
        )

        _llm = init_chat_model(model, model_provider=provider, temperature=temperature)

        self._decide_regenerate = (
            _is_need_to_remake_template | _llm.with_structured_output(IsNeedToRefine)
        )

        # adding data chooser
        _is_need_to_add_template = PromptTemplate.from_template(
            """Here is user's main task:
{users_task}

Based on that, please find out which data user wants to add to dataset; it could be string or list of strings, which lead(s) to folder or file.
Also take in mind: user may mention a lot of files, where some of them can be unrelevant for adding (like some of them have additional info). 
You shouldn't choose them for adding: choose only the data for dataset!
For that, your answer is splitted on two parts: thinking, where are you reflex, and final answer, where you povide path or list of paths for dataset."""
        )

        self._adding_data_chain = (
            _is_need_to_add_template | _llm.with_structured_output(AddingData)
        )

        # defining auto mode
        self._is_auto = is_auto

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
        workflow = StateGraph(AddDataWorkflowState)

        # define the nodes
        workflow.add_node("init_state", self.__init_state)  # init state
        workflow.add_node("get_dataset", self.__get_dataset)  # get dataset destination
        workflow.add_node("reasoning", self.__reasoning)  # get dataset destination
        workflow.add_node("tools", self.__tools_calling)
        workflow.add_node("validaite", self.__validaite)
        workflow.add_node("add_data", self.__add_data)

        # Build graph
        workflow.add_edge(START, "init_state")
        workflow.add_edge("init_state", "get_dataset")

        workflow.add_conditional_edges(
            "get_dataset",
            lambda state: "END" if state["choosen_dataset"] == None else "reasoning",
            {"END": END, "reasoning": "reasoning"},
        )
        workflow.add_conditional_edges(
            "reasoning", self.__should_continue, ["tools", "validaite"]
        )
        workflow.add_edge("tools", "reasoning")

        workflow.add_conditional_edges(
            "validaite",
            self.__is_need_to_reason,
            {"refactor": "reasoning", "add": "add_data", "deny": END},
        )
        workflow.add_edge("add_data", END)

        return workflow

    def get_workflow(self):
        return self._workflow

    #####
    ### Workflow methods block
    #####

    def __init_state(self, state: AddDataWorkflowState) -> AddDataWorkflowState:
        state["messages"] = []
        state["choosen_dataset"] = None
        state["origin_dataset_meta_schema"] = None
        state["currently_filled_schema"] = {}
        state["data_to_add"] = None
        state["user_feedback"] = None
        return state

    def __get_dataset(self, state: AddDataWorkflowState) -> AddDataWorkflowState:
        dataset_name = self.__dataset_selection_rag.retrieve(state["users_task"])
        state["choosen_dataset"] = dataset_name

        if dataset_name != None:
            state["origin_dataset_meta_schema"] = self.__datalake_inst[
                dataset_name
            ].get_metadata_schema_rich_info()

            state["messages"] += [
                (
                    "user",
                    state["users_task"]
                    + "\n\n"
                    + "Here what metadata fields you must to fill. "
                    + "It goes with field names, thier types and examples. "
                    + "Please, don't use examples as a field values, they are given for deonstration, not filling values:"
                    + "".join(
                        [
                            f"\n - \"{k}\": {item['descr']}, type: {item['type']};"
                            for k, item in state["origin_dataset_meta_schema"].items()
                        ]
                    ),
                )
            ]

        return state

    def __reasoning(self, state: AddDataWorkflowState) -> AddDataWorkflowState:
        response = invoke(
            self._reason_llm_chain,
            {"tools_names": str(self.__tools_names), "messages": state["messages"]},
        )
        state["messages"] += [response]
        return state

    def __tools_calling(self, state: AddDataWorkflowState) -> AddDataWorkflowState:
        new_state = self.__tool_node.invoke(state)

        if isinstance(new_state, List) == True and isinstance(new_state[0], Command):
            new_comm = new_state[0]
            state["messages"] = new_comm.update["messages"]
            state["currently_filled_schema"] = new_comm.update[
                "currently_filled_schema"
            ]
        else:
            state["messages"] += new_state["messages"]

        return state

    def __validaite(self, state: AddDataWorkflowState) -> AddDataWorkflowState:
        # just continue execution
        feedback = ""
        if self._is_auto == True:
            feedback = "I think it's alright. You can add the data and finish the job."
        else:
            total_new_vals = state["currently_filled_schema"]
            feedback = interrupt(
                "I filled your data with next values:"
                + "".join([f"\n - {k}: {str(v)}" for k, v in total_new_vals.items()])
                + "\n\nAre everything alright? "
                + "Say, should I continue generation with some info, changing maybe something, "
                + "or should I complete the session with adding data or denying whole session?"
            )

        state["generation_user_feedback"] = feedback
        return state

    def __add_data(self, state: AddDataWorkflowState) -> AddDataWorkflowState:
        data_to_add = invoke(
            self._adding_data_chain, {"users_task": state["users_task"]}
        ).data_to_add

        dataset_name = state["choosen_dataset"]
        datas_metadata = state["currently_filled_schema"]
        self.__datalake_inst[dataset_name].add_data(
            datas_metadata, data_to_add, allow_none_values=True
        )

        return state

    def __should_continue(self, state: AddDataWorkflowState) -> str:
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools"
        return "validaite"

    def __is_need_to_reason(self, state: AddDataWorkflowState) -> str:
        decision = invoke(
            self._decide_regenerate,
            {"user_feedback": state["generation_user_feedback"]},
        )

        if decision.need_regenerate == True:
            return "refactor"
        elif decision.need_to_add == True:
            return "add"
        else:
            return "deny"

    #####
    ### Additional tools block
    #####

    def ask_user(self, question: str, state: Annotated[dict, InjectedState]) -> str:
        """
        Function for asking user for advices

        Args:
            question (str): question which you should ask to user

        Returns:
            str - User's answer
        """

        answer = ""
        if self._is_auto == True:
            answer = "I can't help with your question. Just use only what you have."
        else:
            human_answer = interrupt(question)
            answer = str(human_answer)

        msgs = state["messages"] + [("user", answer)]
        return Command({"messages": msgs})

    def fill_values(
        self,
        new_metadata_values: Dict[str, str],
        state: Annotated[dict, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId],
    ):
        """
        Function for filling values for new data's metadata.

        Args:
            new_metadata_values (Dict[str, str]): some fields of metadata schema with values (converted in string). Structure that argument something like that: {'metadata_field_1':'value_1', 'metadata_field_2':'value_2', ..., 'metadata_field_n':'value_n'}

        Returns:
            str - Log about remaining data and filling values
        """

        old_values = state["currently_filled_schema"]
        full_meta = state["origin_dataset_meta_schema"]

        tool_log = ""
        for new_key, new_value in new_metadata_values.items():
            if new_key in old_values.keys():
                tool_log += f'- ADDING "{new_key}" KEY STATUS: Can\' fill this key and value, because it was already saved!\n'
            elif new_key not in full_meta.keys():
                tool_log += f"- ADDING \"{new_key}\" KEY STATUS: Can' fill this value, because it never was in origin dataset's metadata schema!\n"
            else:
                old_values.update({new_key: new_value})
                tool_log += (
                    f'- ADDING "{new_key}" KEY STATUS: filling went succesful!\n'
                )

        remained_fields = list(set(full_meta.keys()) - set(old_values.keys()))
        tool_msg = "Adding complete. Here is a log:\n" + tool_log

        if len(remained_fields) == 0:
            tool_msg += "\nAll fields are filled! You can finish your job."
        else:
            tool_msg += "\nCurrently remained fields to fill:" + "".join(
                [f'\n - "{f}";' for f in remained_fields]
            )

        msgs = state["messages"] + [
            ToolMessage(content=tool_msg, tool_call_id=tool_call_id)
        ]

        return Command(update={"currently_filled_schema": old_values, "messages": msgs})
