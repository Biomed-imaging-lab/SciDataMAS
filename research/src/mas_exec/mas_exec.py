from copy import deepcopy
from enum import IntEnum
from typing import Any, Dict, List

import yaml
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from app_model import AppModel
from mas_exec.scidatamas.add_data_workflow import (
    AddDataToDatasetFlow,
    AddDataWorkflowState,
)
from mas_exec.scidatamas.data_retrieval_workflow import (
    DataRetrievingFlow,
    RetrievingDatalakeDataState,
)
from mas_exec.scidatamas.dataset_creating_workflow import (
    MDGenerationFlow,
    MDGenerationState,
)
from mas_exec.scidatamas.orchestrator import OrchestratorAgent, OrchestratorState
from mas_exec.scidatamas.finalize_chain import FinalizeChain


class ExecStatus(IntEnum):
    idle = 0
    running = 1
    add_await_table_val = 2
    add_await_human_hint = 3
    create_await_table_val = 4


class MASExec:
    ### vars
    __status: int = ExecStatus.idle
    __memory_saver: MemorySaver = None
    __config: Dict = {"configurable": {"thread_id": 0}}

    __add_agent: AddDataToDatasetFlow = None
    __create_md_agent: MDGenerationFlow = None
    __get_data_agent: DataRetrievingFlow = None
    __orch_agent: OrchestratorAgent = None

    __add_wf: AddDataToDatasetFlow = None
    __create_md_wf: MDGenerationFlow = None
    __get_data_wf: DataRetrievingFlow = None
    __orch_wf: OrchestratorAgent = None
    __finalizer: FinalizeChain = None

    __messages: List[Any] = []

    # last result for complete WF adding! It's updating only when MASExec goes to 'idle' status!
    __last_result: Dict = None
    # regularly updates - after all invokes
    __current_state: Dict = None

    ### consts
    __MODEL_PROVIDER_FIELD: str = "model_provider"
    __MODEL_NAME_FIELD: str = "model_name"
    __CREATE_SP_FIELD: str = "create_data_sp"
    __ADD_SP_FIELD: str = "add_data_sp"
    __GET_SP_FIELD: str = "get_data_sp"
    __ORCH_SP_FIELD: str = "orchestrator_sp"
    __SP_FIELD: str = "system_prompt"

    def __read_sp(self, sp_path: str) -> str:
        with open(sp_path) as stream:
            sp = yaml.safe_load(stream)[MASExec.__SP_FIELD]
        return sp

    def __init__(self, config: Dict[str, Any], app_model: AppModel):
        # 0 - check conf
        assert MASExec.__MODEL_PROVIDER_FIELD in config.keys()
        assert MASExec.__MODEL_NAME_FIELD in config.keys()
        assert MASExec.__CREATE_SP_FIELD in config.keys()
        assert MASExec.__ADD_SP_FIELD in config.keys()
        assert MASExec.__GET_SP_FIELD in config.keys()
        assert MASExec.__ORCH_SP_FIELD in config.keys()

        # 1 - read fields for wf
        model_name = config[MASExec.__MODEL_NAME_FIELD]
        model_provider = config[MASExec.__MODEL_PROVIDER_FIELD]
        add_sp_path = config[MASExec.__ADD_SP_FIELD]
        create_sp_path = config[MASExec.__CREATE_SP_FIELD]
        get_sp_path = config[MASExec.__GET_SP_FIELD]
        orch_sp_path = config[MASExec.__ORCH_SP_FIELD]

        add_sp = self.__read_sp(add_sp_path)
        create_sp = self.__read_sp(create_sp_path)
        get_sp = self.__read_sp(get_sp_path)
        orch_sp = self.__read_sp(orch_sp_path)

        # 2 - init wfs
        self.__add_agent = AddDataToDatasetFlow(
            system_prompt=add_sp,
            datalake=app_model.datalake,
            model=model_name,
            provider=model_provider,
            is_auto=False,
        )
        self.__add_wf = self.__add_agent.get_workflow()

        self.__create_md_agent = MDGenerationFlow(
            datalake=app_model.datalake,
            system_prompt=create_sp,
            model=model_name,
            provider=model_provider,
            is_auto=False,
        )
        self.__create_md_wf = self.__create_md_agent.get_workflow()

        self.__get_data_agent = DataRetrievingFlow(
            system_prompt=get_sp,
            datalake=app_model.datalake,
            model=model_name,
            provider=model_provider,
        )
        self.__get_data_wf = self.__get_data_agent.get_workflow()

        self.__orch_agent = OrchestratorAgent(
            system_prompt=orch_sp,
            model=model_name,
            provider=model_provider,
        )
        self.__orch_wf = self.__orch_agent.get_workflow()

        # 3 - compile wfs
        self.__memory_saver = MemorySaver()
        self.__orch_wf = self.__orch_wf.compile(checkpointer=self.__memory_saver)
        self.__add_wf = self.__add_wf.compile(checkpointer=self.__memory_saver)
        self.__get_data_wf = self.__get_data_wf.compile(
            checkpointer=self.__memory_saver
        )
        self.__create_md_wf = self.__create_md_wf.compile(
            checkpointer=self.__memory_saver
        )
        self.__finalizer = FinalizeChain(model=model_name, provider=model_provider)
        return

    def __proceed_orch_exec(self, res: Dict, query: str):
        assert self.__status == ExecStatus.running

        choosen_wf = res["choosen_wf"]
        match choosen_wf:
            case "add_data":
                add_state = AddDataWorkflowState()
                add_state["users_task"] = query
                res = self.__add_wf.invoke(add_state, config=self.__config)
                self.__update_status(res)

            case "get_data":
                get_state = RetrievingDatalakeDataState()
                get_state["users_task"] = query
                res = self.__get_data_wf.invoke(get_state, config=self.__config)
                self.__update_status(res)

            case "create_md":
                create_state = MDGenerationState()
                create_state["users_task"] = query
                res = self.__create_md_wf.invoke(create_state, config=self.__config)
                self.__update_status(res)

            case _:
                # TODO: its necessary to provide some text, finalyzing MAS working
                raise ValueError("The query isn't relevant to MAS functionality")
        return

    def run_task(self, query: str) -> None:
        assert self.__status == ExecStatus.idle
        self.__config["configurable"]["thread_id"] += 1
        self.__messages.append(("user", query))

        self.__status = ExecStatus.running
        orch_state = OrchestratorState()
        orch_state["users_task"] = query
        orch_state["messages"] = [("user", query)]
        res = self.__orch_wf.invoke(orch_state, config=self.__config)

        self.__proceed_orch_exec(res, query)
        return

    def __update_status(self, result):
        # some workflow ends without interrupting -> goes to its 'END' -> Save result and leave
        self.__current_state = result

        if "__interrupt__" not in result.keys():
            self.__last_result = result
            self.__status = ExecStatus.idle
            final_msg = self.__finalizer.call(self.__last_result['messages'])
            self.__messages.append(('assistant', final_msg))
            return

        inter_str = result["__interrupt__"][0].value
        inter_str_type, inter_info = inter_str.split(":", 1)

        match inter_str_type:
            case "create_valid":
                self.__messages.append(('assistant', inter_info))
                self.__status = ExecStatus.create_await_table_val
            case "await_table_validation":
                self.__messages.append(('assistant', inter_info))
                self.__status = ExecStatus.add_await_table_val
            case "await_add_info":
                self.__messages.append(('assistant', inter_info))
                self.__status = ExecStatus.add_await_human_hint
            case _:
                raise RuntimeError(f"Unknown type of interrupting: '{inter_str_type}'")
        return

    def validate_add_table(
        self, valid_dict: Dict[str, Any] = None, users_comment: str = ""
    ) -> ExecStatus:
        assert self.__status == ExecStatus.add_await_table_val

        self.__messages.append(('user', users_comment))
        if valid_dict == None:
            valid_dict = self.__current_state["currently_filled_schema"]

        resume_dict = {
            "currently_filled_schema": valid_dict,
            "generation_user_feedback": users_comment,
        }
        self.__status = ExecStatus.running
        result = self.__add_wf.invoke(Command(resume=resume_dict), config=self.__config)
        self.__update_status(result)
        return self.__status

    def add_human_hint(self, users_comment: str = "") -> ExecStatus:
        assert self.__status == ExecStatus.add_await_human_hint
        
        self.__messages.append(('user', users_comment))
        resume_dict = {"user_answer": users_comment}
        self.__status = ExecStatus.running
        result = self.__add_wf.invoke(Command(resume=resume_dict), config=self.__config)
        self.__update_status(result)
        return self.__status

    def validate_create_md_table(
        self,
        dataset_name: str,
        dataset_decr: str,
        md_dict: Dict[str, Any],
        users_comment: str = "",
    ) -> ExecStatus:
        assert self.__status == ExecStatus.create_await_table_val
        
        self.__messages.append(('user', users_comment))
        resume_dict = {
            "generation_user_feedback": users_comment,
            "short_name": dataset_name,
            "description": dataset_decr,
            "md_schema": md_dict,
        }
        self.__status = ExecStatus.running
        result = self.__create_md_wf.invoke(
            Command(resume=resume_dict), config=self.__config
        )
        self.__update_status(result)
        return self.__status

    @property
    def current_state(self):
        return deepcopy(self.__current_state)

    @property
    def last_result(self):
        return deepcopy(self.__last_result)

    @property
    def status(self):
        return self.__status

    @property
    def messages(self):
        return self.__messages
