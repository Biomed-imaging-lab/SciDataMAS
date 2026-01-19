from typing import Any, List, Dict
import streamlit as st
from threading import Thread
from copy import deepcopy
from time import sleep

from mas_exec.mas_exec import MASExec, ExecStatus


class StreamlitGUI:
    __mas: MASExec = None
    __mas_thread: Thread = None

    __last_user_task: str = None

    __md_datatable = None
    __DATA_WIDGET_KEY: str = "data_edit_table"
    __DATASET_NAME_KEY: str = "dataset_name"
    __DATASET_DESCR_KEY: str = "dataset_descr"

    def __init__(self, mas: MASExec):
        self.__mas = mas
        if "messages" not in st.session_state:
            st.session_state["messages"] = []

    def __parse_create_md_dict_to_streamlit_dict(self, md_dict: Dict) -> Dict:
        streamlit_dict = {
            "will_use": [],
            "field_name": [],
            "field_descr": [],
            "field_type": [],
        }

        for md_k, md_v in md_dict.items():
            streamlit_dict["will_use"].append(True)
            streamlit_dict["field_name"].append(md_k)
            streamlit_dict["field_descr"].append(md_v["descr"])
            streamlit_dict["field_type"].append(md_v["type"])
        return streamlit_dict

    def __parse_streamlit_dict_to_create_md_dict(self, md_dict: Dict) -> Dict:
        new_dict = {}
        dict_len = len(md_dict["will_use"])

        for i in range(dict_len):
            if md_dict["will_use"][i] == True:
                new_dict.update(
                    {
                        md_dict["field_name"][i]: {
                            "descr": md_dict["field_descr"][i],
                            "type": md_dict["field_type"][i],
                        }
                    }
                )
        return new_dict

    def __parse_add_filling_md_to_streamlit_dict(
        self, curr_filled: Dict, need_to_fill: Dict
    ) -> Dict:
        dict_to_show = {"md_field": [], "filled_value": []}
        required_fields = list(set(need_to_fill.keys()) - set(curr_filled.keys()))

        for cur_k, cur_v in curr_filled.items():
            dict_to_show["md_field"].append(cur_k)
            dict_to_show["filled_value"].append(str(cur_v))

        for r_f in required_fields:
            dict_to_show["md_field"].append(r_f)
            dict_to_show["filled_value"].append(None)

        return dict_to_show

    def __parse_streamlit_dict_to_add_filling_md(self, streamlit_dict: Dict) -> Dict:
        curr_filled = {}
        len_filled = len(streamlit_dict["md_field"])

        for i in range(len_filled):
            field_name = streamlit_dict["md_field"][i]
            field_val = streamlit_dict["filled_value"][i]

            curr_filled.update({field_name: field_val})
        return curr_filled

    def _display_messages(self):
        messages = deepcopy(self.__mas.messages)

        # making ad-hoc message, because it doens't in mas list yet.
        if self.__last_user_task != None:
            messages += [
                ("user", self.__last_user_task),
                ("assistant", "Performing your task..."),
            ]

        # displaying messages
        st.session_state["messages"] = messages

        for message in messages:
            with st.chat_message(message[0]):
                st.markdown(message[1])

        # displaying additional fields because of mas status 'create_await_table_val' - only if user doesn't provide feedback!
        if (
            self.__mas.status == ExecStatus.create_await_table_val
            and self.__last_user_task == None
        ):
            current_generation = self.__mas.current_state["generation"]
            name = current_generation.short_name
            descr = current_generation.description
            schema = current_generation.schema
            st_schema = self.__parse_create_md_dict_to_streamlit_dict(schema)

            st.text_input(
                label="New dataset name", value=name, key=self.__DATASET_NAME_KEY
            )
            st.text_input(
                label="New dataset description",
                value=descr,
                key=self.__DATASET_DESCR_KEY,
            )
            self.__md_datatable = st.data_editor(st_schema, key=self.__DATA_WIDGET_KEY)

        # displaying additional fields because of mas status 'add_await_table_val' - only if user doesn't provide feedback!
        if (
            self.__mas.status == ExecStatus.add_await_table_val
            and self.__last_user_task == None
        ):
            current_filled = self.__mas.current_state["currently_filled_schema"]
            requiered_md = self.__mas.current_state["origin_dataset_meta_schema"]

            vis_dict = self.__parse_add_filling_md_to_streamlit_dict(
                current_filled, requiered_md
            )

            self.__md_datatable = st.data_editor(vis_dict, key=self.__DATA_WIDGET_KEY)

    def _invoke_agent(self):
        if self.__last_user_task == None:
            return

        new_query = self.__last_user_task
        self.__last_user_task = None

        recieved_dataset_name = (
            st.session_state[self.__DATASET_NAME_KEY]
            if self.__DATASET_NAME_KEY in st.session_state.keys()
            else None
        )

        recieved_dataset_descr = (
            st.session_state[self.__DATASET_DESCR_KEY]
            if self.__DATASET_DESCR_KEY in st.session_state.keys()
            else None
        )

        if self.__mas.status == ExecStatus.idle:
            self.__mas_thread = Thread(target=self.__mas.run_task, args=(new_query,))
        elif self.__mas.status == ExecStatus.add_await_human_hint:
            self.__mas_thread = Thread(
                target=self.__mas.add_human_hint, args=(new_query,)
            )
        elif self.__mas.status == ExecStatus.add_await_table_val:
            md_schema = self.__parse_streamlit_dict_to_add_filling_md(
                self.__md_datatable
            )

            self.__mas_thread = Thread(
                target=self.__mas.validate_add_table,
                args=(
                    md_schema,
                    new_query,
                ),
            )
        elif self.__mas.status == ExecStatus.create_await_table_val:
            md_schema = self.__parse_streamlit_dict_to_create_md_dict(
                self.__md_datatable
            )

            self.__mas_thread = Thread(
                target=self.__mas.validate_create_md_table,
                args=(
                    recieved_dataset_name,
                    recieved_dataset_descr,
                    md_schema,
                    new_query,
                ),
            )
        else:
            raise RuntimeError("Unexpected behaviour")

        self.__mas_thread.start()
        return

    def _handle_user_input(self):
        if prompt := st.chat_input("Input your query here..."):
            self.__last_user_task = prompt
            st.rerun()

    def _wait_answer(self):
        if self.__mas_thread != None:
            self.__mas_thread.join()
            self.__mas_thread = None
            st.rerun()
        return

    def run(self):
        st.title("SciDataMAS")
        st.caption(
            "This is not the final version of the agent - the design and interface are being refined."
        )

        self._display_messages()

        self._invoke_agent()

        self._handle_user_input()

        self._wait_answer()

        if not st.session_state.messages:
            st.info("Here will be your task messages!")
